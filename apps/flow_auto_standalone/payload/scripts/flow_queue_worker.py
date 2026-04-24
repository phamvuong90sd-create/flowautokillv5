#!/usr/bin/env python3
import json
import os
import shlex
import subprocess
import time
from pathlib import Path

HOME = Path.home()
WORKSPACE = Path(os.environ.get("FLOW_WORKSPACE", str(HOME / ".openclaw" / "workspace")))
INBOUND_DIR = Path(os.environ.get("FLOW_INBOUND_DIR", str(HOME / ".openclaw" / "media" / "inbound")))
QUEUE_DIR = Path(os.environ.get("FLOW_QUEUE_DIR", str(WORKSPACE / "flow-auto")))
RUNNER = Path(os.environ.get("FLOW_RUNNER", str(WORKSPACE / "scripts" / "flow_batch_runner.py")))
VENV_PY = Path(os.environ.get("FLOW_PY", str(WORKSPACE / ".venv-flow" / "bin" / "python")))
POLL_SEC = int(os.environ.get("FLOW_POLL_SEC", "8"))
NOTIFY_CMD = os.environ.get("FLOW_NOTIFY_CMD", "")

PROCESSING = QUEUE_DIR / "processing"
DONE = QUEUE_DIR / "done"
FAILED = QUEUE_DIR / "failed"
STATE = QUEUE_DIR / "worker-state.json"
JOB_STATE = QUEUE_DIR / "job-state"


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


def load_flow_state():
    f = WORKSPACE / ".flow_state.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def get_default_aspect_ratio(flow_state: dict) -> str:
    ratio = str(flow_state.get("default_aspect_ratio", "9:16")).strip()
    return ratio if ratio in {"16:9", "9:16", "1:1"} else "9:16"


def run_job(txt_file: Path):
    job_name = txt_file.stem
    job_state = JOB_STATE / f"{job_name}.json"
    flow_state = load_flow_state()
    aspect_ratio = get_default_aspect_ratio(flow_state)

    exe = str(VENV_PY)
    embedded = os.environ.get("FLOW_RUNNER_EMBEDDED", "0") == "1"
    if embedded:
        cmd = [
            exe,
            "--run-script",
            str(RUNNER),
            "--prompts", str(txt_file),
            "--state", str(job_state),
            "--start-from", "1",
            "--aspect-ratio", aspect_ratio,
        ]
    else:
        cmd = [
            exe,
            str(RUNNER),
            "--prompts", str(txt_file),
            "--state", str(job_state),
            "--start-from", "1",
            "--aspect-ratio", aspect_ratio,
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


def main():
    ensure_dirs()
    st = load_state()
    st.setdefault("seen", [])

    print("[worker] started", flush=True)
    while True:
        try:
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
