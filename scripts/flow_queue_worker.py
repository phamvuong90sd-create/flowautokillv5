#!/usr/bin/env python3
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Tuple
from urllib.parse import urlparse

HOME = Path.home()
WORKSPACE = Path(os.environ.get("FLOW_WORKSPACE", str(HOME / ".openclaw" / "workspace")))
INBOUND_DIR = Path(os.environ.get("FLOW_INBOUND_DIR", str(HOME / ".openclaw" / "media" / "inbound")))
QUEUE_DIR = Path(os.environ.get("FLOW_QUEUE_DIR", str(WORKSPACE / "flow-auto")))
RUNNER = Path(os.environ.get("FLOW_RUNNER", str(WORKSPACE / "scripts" / "flow_batch_runner.py")))
VENV_PY = Path(os.environ.get("FLOW_PY", str(WORKSPACE / ".venv-flow" / "bin" / "python")))
POLL_SEC = int(os.environ.get("FLOW_POLL_SEC", "8"))
NOTIFY_CMD = os.environ.get("FLOW_NOTIFY_CMD", "")
LICENSE_CHECK_CMD = os.environ.get("FLOW_LICENSE_CHECK_CMD", "")
LICENSE_POLL_SEC = int(os.environ.get("FLOW_LICENSE_POLL_SEC", "300"))
LICENSE_FAIL_ACTION = os.environ.get("FLOW_LICENSE_FAIL_ACTION", "exit").strip().lower()

PROCESSING = QUEUE_DIR / "processing"
DONE = QUEUE_DIR / "done"
FAILED = QUEUE_DIR / "failed"
STATE = QUEUE_DIR / "worker-state.json"
JOB_STATE = QUEUE_DIR / "job-state"
FLOW_STATE_FILE = WORKSPACE / ".flow_state.json"
DEFAULT_ASPECT_RATIO = os.environ.get("FLOW_DEFAULT_ASPECT_RATIO", "16:9").strip()
DEFAULT_PROMPT_DELAY_SEC = int(os.environ.get("FLOW_PROMPT_DELAY_SEC", "10"))
ALLOWED_PROMPT_DELAYS = {9, 15, 30, 45}


def ensure_dirs():
    for d in [QUEUE_DIR, PROCESSING, DONE, FAILED, JOB_STATE]:
        d.mkdir(parents=True, exist_ok=True)


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            return {"seen": []}
    return {"seen": []}


def save_state(st):
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() == ".txt"


def discover_new_files(st):
    seen = set(st.get("seen", []))
    items = []
    for p in sorted(INBOUND_DIR.glob("*.txt"), key=lambda x: x.stat().st_mtime):
        key = str(p.resolve()) + f":{int(p.stat().st_mtime)}:{p.stat().st_size}"
        if key not in seen:
            items.append((p, key))
    return items


def notify(event: str, filename: str, rc: int = 0, progress: str = ""):
    if not NOTIFY_CMD:
        return
    env = os.environ.copy()
    env["FLOW_EVENT"] = event
    env["FLOW_FILE"] = filename
    env["FLOW_RC"] = str(rc)
    if progress:
        env["FLOW_PROGRESS"] = progress
    try:
        subprocess.run(shlex.split(NOTIFY_CMD), env=env, check=False)
    except Exception as e:
        print(f"[worker] notify error: {e}", flush=True)


def is_cdp_alive(cdp_url: str) -> bool:
    try:
        u = urlparse(cdp_url)
        host = u.hostname or "127.0.0.1"
        port = u.port or 18800
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except Exception:
        return False


def ensure_browser_ready(cdp_url: str) -> bool:
    if is_cdp_alive(cdp_url):
        return True

    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        print("[worker] browser not found on PATH", flush=True)
        return False

    u = urlparse(cdp_url)
    host = u.hostname or "127.0.0.1"
    port = u.port or 18800

    user_data = os.environ.get("FLOW_CHROME_USER_DATA", str(HOME / ".config" / "google-chrome-flow"))
    start_url = os.environ.get("FLOW_START_URL", "https://labs.google/fx/tools/flow")
    # Lock browser window to stable geometry for Flow automation
    window_w = int(os.environ.get("FLOW_WINDOW_WIDTH", "800"))
    window_h = int(os.environ.get("FLOW_WINDOW_HEIGHT", "600"))
    window_x = int(os.environ.get("FLOW_WINDOW_X", "0"))
    window_y = int(os.environ.get("FLOW_WINDOW_Y", "0"))

    cmd = [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        f"--window-size={window_w},{window_h}",
        f"--window-position={window_x},{window_y}",
        "--force-device-scale-factor=1",
        start_url,
    ]

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[worker] failed to launch browser: {e}", flush=True)
        return False

    for _ in range(20):
        if is_cdp_alive(cdp_url):
            print(f"[worker] browser auto-opened and CDP ready on {host}:{port}", flush=True)
            return True
        time.sleep(0.5)

    print(f"[worker] CDP still unavailable after auto-open on {host}:{port}", flush=True)
    return False


def load_flow_state() -> dict:
    try:
        if FLOW_STATE_FILE.exists():
            return json.loads(FLOW_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def get_default_aspect_ratio(st: dict) -> str:
    ratio = DEFAULT_ASPECT_RATIO if DEFAULT_ASPECT_RATIO in {"16:9", "9:16"} else "16:9"
    r = str(st.get("default_aspect_ratio", "")).strip()
    if r in {"16:9", "9:16"}:
        ratio = r
    return ratio


def get_prompt_delay_sec(st: dict) -> int:
    delay = DEFAULT_PROMPT_DELAY_SEC if DEFAULT_PROMPT_DELAY_SEC in ALLOWED_PROMPT_DELAYS else 10
    try:
        d = int(st.get("prompt_delay_sec", delay))
        if d in ALLOWED_PROMPT_DELAYS:
            delay = d
    except Exception:
        pass
    return delay


def run_job(txt_file: Path):
    cdp_url = os.environ.get("FLOW_CDP", "http://127.0.0.1:18800")
    if not ensure_browser_ready(cdp_url):
        class Result:
            def __init__(self, returncode):
                self.returncode = returncode
        return Result(97)

    job_name = txt_file.stem
    job_state = JOB_STATE / f"{job_name}.json"
    flow_state = load_flow_state()
    aspect_ratio = get_default_aspect_ratio(flow_state)
    prompt_delay = get_prompt_delay_sec(flow_state)

    cmd = [
        str(VENV_PY),
        str(RUNNER),
        "--prompts", str(txt_file),
        "--state", str(job_state),
        "--start-from", "1",
        "--cdp", cdp_url,
        "--aspect-ratio", aspect_ratio,
        "--between-prompts-sec", str(prompt_delay),
    ]
    print(f"[worker] run: {' '.join(cmd)}", flush=True)

    proc = subprocess.Popen(cmd, text=True)
    last_notified_done = -1

    while True:
        rc = proc.poll()
        if job_state.exists():
            try:
                st = json.loads(job_state.read_text(encoding="utf-8"))
                done = int(st.get("done", 0))
                total = int(st.get("total", 0))
                if total > 0 and done != last_notified_done and done > 0 and done % 10 == 0:
                    notify("progress", txt_file.name, 0, progress=f"{done}/{total}")
                    last_notified_done = done
            except Exception:
                pass

        if rc is not None:
            class Result:
                def __init__(self, returncode):
                    self.returncode = returncode
            return Result(rc)

        time.sleep(2)


def move_safe(src: Path, dst_dir: Path):
    dst = dst_dir / src.name
    if dst.exists():
        ts = int(time.time())
        dst = dst_dir / f"{src.stem}-{ts}{src.suffix}"
    src.rename(dst)
    return dst


def check_license() -> Tuple[bool, str]:
    if not LICENSE_CHECK_CMD:
        return True, "license_check_disabled"
    try:
        proc = subprocess.run(
            shlex.split(LICENSE_CHECK_CMD),
            check=False,
            capture_output=True,
            text=True,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode == 0:
            return True, out or "ok"
        reason = out or err or f"rc={proc.returncode}"
        return False, reason
    except Exception as e:
        return False, str(e)


def main():
    ensure_dirs()
    st = load_state()
    st.setdefault("seen", [])

    last_license_check = 0
    print("[worker] started", flush=True)
    while True:
        try:
            now_ts = int(time.time())
            if now_ts - last_license_check >= LICENSE_POLL_SEC:
                ok, reason = check_license()
                last_license_check = now_ts
                if not ok:
                    print(f"[worker] license blocked: {reason}", flush=True)
                    if LICENSE_FAIL_ACTION == "exit":
                        print("[worker] license fail action=exit -> stopping worker", flush=True)
                        sys.exit(12)
                    time.sleep(POLL_SEC)
                    continue

            new_files = discover_new_files(st)
            if not new_files:
                time.sleep(POLL_SEC)
                continue

            for f, key in new_files:
                if not is_text_file(f):
                    st["seen"].append(key)
                    save_state(st)
                    continue

                processing_file = move_safe(f, PROCESSING)
                rc = run_job(processing_file).returncode

                if rc == 0:
                    move_safe(processing_file, DONE)
                    print(f"[worker] done: {processing_file.name}", flush=True)
                    notify("done", processing_file.name, rc)
                else:
                    move_safe(processing_file, FAILED)
                    print(f"[worker] failed: {processing_file.name}", flush=True)
                    notify("failed", processing_file.name, rc)

                st["seen"].append(key)
                st["last_file"] = processing_file.name
                st["last_rc"] = rc
                st["updated_at"] = int(time.time())
                save_state(st)

        except Exception as e:
            print(f"[worker] error: {e}", flush=True)
            time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
