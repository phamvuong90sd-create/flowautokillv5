#!/usr/bin/env python3
import json
import os
import platform
import signal
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

WS = Path(os.environ.get("FLOW_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))
FLOW_DIR = WS / "flow-auto"
SCRIPTS_DIR = WS / "scripts"
VENV_PY = WS / ".venv-flow" / "bin" / "python"
VENV_PY_WIN = WS / ".venv-flow" / "Scripts" / "python.exe"
PID_FILE = FLOW_DIR / "job-state" / "bridge-runner.pid"
STATUS_FILE = FLOW_DIR / "job-state" / "bridge-status.json"
CDP_LAUNCH_FILE = FLOW_DIR / "job-state" / "cdp-last-launch.json"


def _json_write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _json_read(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _cmd(cmd, timeout=120):
    kwargs = {"capture_output": True, "text": True, "timeout": timeout}
    if platform.system().lower() == "windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    p = subprocess.run(cmd, **kwargs)
    return {
        "ok": p.returncode == 0,
        "code": p.returncode,
        "stdout": (p.stdout or "").strip(),
        "stderr": (p.stderr or "").strip(),
        "cmd": cmd,
    }


def _python_bin():
    if VENV_PY.exists():
        return str(VENV_PY)
    if VENV_PY_WIN.exists():
        return str(VENV_PY_WIN)
    return "python3"


def _cdp_ready() -> bool:
    try:
        with urlopen("http://127.0.0.1:18800/json/version", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_cdp():
    if _cdp_ready():
        return {"ok": True, "reason": "already_ready"}

    # tránh mở quá nhiều cửa sổ Flow khi bấm nút liên tục
    last = _json_read(CDP_LAUNCH_FILE)
    now = int(time.time())
    if int(last.get("ts", 0)) and (now - int(last.get("ts", 0)) < 15):
        for _ in range(15):
            if _cdp_ready():
                return {"ok": True, "reason": "warmup_wait"}
            time.sleep(1)
        return {"ok": False, "reason": "cdp_not_ready_recent_launch"}

    os_name = platform.system().lower()
    launched = False

    candidates = []
    if os_name == "linux":
        for exe in ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]:
            candidates.append([
                exe,
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=18800",
                f"--user-data-dir={Path.home() / '.config/google-chrome-flow'}",
                "https://labs.google/fx/tools/flow",
            ])
    elif os_name == "darwin":
        candidates.append([
            "open",
            "-a",
            "Google Chrome",
            "--args",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=18800",
            f"--user-data-dir={Path.home() / '.config/google-chrome-flow'}",
            "https://labs.google/fx/tools/flow",
        ])
    else:  # windows
        candidates.append([
            "cmd",
            "/c",
            "start",
            "",
            "chrome",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=18800",
            "https://labs.google/fx/tools/flow",
        ])

    for cmd in candidates:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _json_write(CDP_LAUNCH_FILE, {"ts": now, "cmd": cmd})
            launched = True
            break
        except Exception:
            continue

    for _ in range(25):
        if _cdp_ready():
            return {"ok": True, "reason": "launched", "launched": launched}
        time.sleep(1)

    return {"ok": False, "reason": "cdp_not_ready"}


def build_first_n(prompts_path: Path, n: int) -> Path:
    text = prompts_path.read_text(encoding="utf-8", errors="ignore")
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    out = FLOW_DIR / f"current-text-prompt-first{n}-bridge.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n\n".join(blocks[:n]) + "\n", encoding="utf-8")
    return out


def start_run(prompts_path: str, limit: int = 20, start_from: int = 1):
    # tránh start trùng nhiều lần
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            if _is_running(old_pid):
                st = _json_read(STATUS_FILE)
                st.update({"ok": True, "running": True, "pid": old_pid, "reason": "already_running"})
                return st
        except Exception:
            pass

    src = Path(prompts_path)
    if not src.exists():
        raise FileNotFoundError(f"prompts file not found: {src}")

    cdp = ensure_cdp()
    if not cdp.get("ok"):
        raise RuntimeError("Không mở được CDP/Chrome Flow")

    use_file = build_first_n(src, limit) if limit > 0 else src
    state = FLOW_DIR / "job-state" / "bridge-runner.json"
    log = FLOW_DIR / "debug" / "bridge-runner.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        _python_bin(),
        str(SCRIPTS_DIR / "flow_batch_runner.py"),
        "--prompts",
        str(use_file),
        "--state",
        str(state),
        "--start-from",
        str(start_from),
    ]

    stdout_f = open(log, "a", encoding="utf-8")
    if platform.system().lower() == "windows":
        p = subprocess.Popen(cmd, stdout=stdout_f, stderr=subprocess.STDOUT)
    else:
        p = subprocess.Popen(cmd, stdout=stdout_f, stderr=subprocess.STDOUT, preexec_fn=os.setsid)

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(p.pid), encoding="utf-8")

    _json_write(
        STATUS_FILE,
        {
            "ok": True,
            "running": True,
            "pid": p.pid,
            "prompts": str(use_file),
            "state": str(state),
            "log": str(log),
            "ts": int(time.time()),
        },
    )
    return _json_read(STATUS_FILE)


def stop_run():
    if not PID_FILE.exists():
        return {"ok": True, "running": False, "reason": "no_pid"}

    pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    try:
        if platform.system().lower() == "windows":
            os.kill(pid, signal.SIGTERM)
        else:
            os.killpg(pid, signal.SIGTERM)
    except Exception:
        pass

    PID_FILE.unlink(missing_ok=True)
    st = _json_read(STATUS_FILE)
    st.update({"running": False, "stopped_at": int(time.time())})
    _json_write(STATUS_FILE, st)
    return {"ok": True, "running": False, "pid": pid}


def status():
    st = _json_read(STATUS_FILE)
    pid = None
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            pid = None
    running = bool(pid and _is_running(pid))
    st.update({"running": running, "pid": pid})
    return st


def check_license():
    return _cmd([_python_bin(), str(SCRIPTS_DIR / "flow_license_online_check.py"), "--check", "--json"])


def _machine_id():
    verify = SCRIPTS_DIR / "bin" / "flow_license_verify"
    if verify.exists():
        r = _cmd([str(verify), "--machine-id"], timeout=30)
        if r.get("ok") and r.get("stdout"):
            return r["stdout"].strip()

    # fallback cross-platform
    if platform.system().lower() == "darwin":
        r = _cmd(["bash", "-lc", "ioreg -rd1 -c IOPlatformExpertDevice | awk -F\" '/IOPlatformUUID/{print $4}' | tr '[:upper:]' '[:lower:]'"], timeout=30)
        if r.get("ok") and r.get("stdout"):
            return r["stdout"].strip()

    return platform.node().lower().strip() or "unknown"


def activate_license_key(license_key: str, api_base: str = ""):
    key = (license_key or "").strip()
    if not key:
        return {"ok": False, "error": "license_key_empty"}

    checker = SCRIPTS_DIR / "flow_license_online_check.py"
    if not checker.exists():
        return {"ok": False, "error": "flow_license_online_check.py not found"}

    base = (api_base or "").strip() or os.environ.get("PRESET_LICENSE_API_BASE", "https://server-auto-tool.vercel.app/api/license")
    mid = _machine_id()

    setup = _cmd([_python_bin(), str(checker), "--setup", "--api-base", base, "--license-key", key, "--machine-id", mid], timeout=120)
    if not setup.get("ok"):
        return {"ok": False, "stage": "setup", **setup}

    activate = _cmd([_python_bin(), str(checker), "--activate"], timeout=180)
    if not activate.get("ok"):
        return {"ok": False, "stage": "activate", **activate}

    return {"ok": True, "stage": "done", "machine_id": mid, "api_base": base, "stdout": activate.get("stdout", "")}


def activate_app(author_code: str = ""):
    if author_code:
        if platform.system().lower() == "windows":
            # fallback online activate on Windows mode
            return _cmd([_python_bin(), str(SCRIPTS_DIR / "flow_license_online_check.py"), "--activate"])
        sh = SCRIPTS_DIR / "flow_author_activate.sh"
        return _cmd(["bash", str(sh), author_code])

    return _cmd([_python_bin(), str(SCRIPTS_DIR / "flow_license_online_check.py"), "--activate"])


def openclaw_status():
    return _cmd(["openclaw", "status"])


def run_quick_start(prompts_path: str):
    return start_run(prompts_path=prompts_path, limit=10, start_from=1)


def clear_browser_cache():
    os_name = platform.system().lower()
    removed = []
    if os_name == "linux":
        targets = [
            Path.home() / ".config/google-chrome-flow/Default/Cache",
            Path.home() / ".config/google-chrome-flow/Default/Code Cache",
        ]
        for t in targets:
            if t.exists():
                subprocess.run(["rm", "-rf", str(t)])
                removed.append(str(t))
    return {"ok": True, "removed": removed}


def google_login_auto_check():
    return _cmd([_python_bin(), str(SCRIPTS_DIR / "flow_google_login_auto_check.py")], timeout=180)


def download_all_completed():
    return _cmd([_python_bin(), str(SCRIPTS_DIR / "flow_download_all_completed.py")], timeout=600)


def repair_chrome_reinstall():
    sh = SCRIPTS_DIR / "flow_chrome_repair_reinstall.sh"
    if platform.system().lower() == "windows":
        return {"ok": False, "error": "repair_chrome_reinstall.sh currently linux/mac only"}
    return _cmd(["bash", str(sh)], timeout=1200)


def postprocess_videos(input_dir: str = "", output_file: str = ""):
    script = SCRIPTS_DIR / "flow_postprocess_videos.py"
    if not script.exists():
        return {"ok": False, "error": "flow_postprocess_videos.py not found"}

    cmd = [_python_bin(), str(script)]
    if input_dir:
        cmd += ["--input-dir", input_dir]
    if output_file:
        cmd += ["--output", output_file]

    return _cmd(cmd, timeout=2400)


def open_exports(path: str = ""):
    script = SCRIPTS_DIR / "flow_export_open.py"
    if not script.exists():
        return {"ok": False, "error": "flow_export_open.py not found"}

    cmd = [_python_bin(), str(script)]
    if path:
        cmd.append(path)
    return _cmd(cmd, timeout=120)


class H(BaseHTTPRequestHandler):
    def _send(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self._send(200, {"ok": True, "service": "flow_auto_v2", "ts": int(time.time())})
        if path == "/api/status":
            return self._send(200, status())
        if path == "/api/license/check":
            return self._send(200, check_license())
        if path == "/api/openclaw/status":
            return self._send(200, openclaw_status())
        return self._send(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            data = {}

        if path == "/api/start":
            try:
                prompts = data.get("prompts_path") or str(FLOW_DIR / "current-text-prompt.txt")
                limit = int(data.get("limit", 20))
                start_from = int(data.get("start_from", 1))
                return self._send(200, start_run(prompts, limit, start_from))
            except Exception as e:
                return self._send(500, {"ok": False, "error": str(e)})

        if path == "/api/stop":
            return self._send(200, stop_run())

        if path == "/api/activate":
            # Ưu tiên kích hoạt bằng LICENSE_KEY từ GUI
            license_key = str(data.get("license_key", "")).strip()
            api_base = str(data.get("api_base", "")).strip()
            if license_key:
                return self._send(200, activate_license_key(license_key, api_base))

            # fallback flow cũ (author code / activate existing setup)
            code = str(data.get("author_code", "")).strip()
            return self._send(200, activate_app(code))

        if path == "/api/run_quick_start":
            prompts = data.get("prompts_path") or str(FLOW_DIR / "current-text-prompt.txt")
            try:
                return self._send(200, run_quick_start(prompts))
            except Exception as e:
                return self._send(500, {"ok": False, "error": str(e)})

        if path == "/api/clear_browser_cache":
            return self._send(200, clear_browser_cache())

        if path == "/api/google_login_auto_check":
            return self._send(200, google_login_auto_check())

        if path == "/api/download_all_completed":
            return self._send(200, download_all_completed())

        if path == "/api/repair_chrome_reinstall":
            return self._send(200, repair_chrome_reinstall())

        if path == "/api/postprocess_videos":
            input_dir = str(data.get("input_dir", "")).strip()
            output_file = str(data.get("output_file", "")).strip()
            return self._send(200, postprocess_videos(input_dir, output_file))

        if path == "/api/open_exports":
            p = str(data.get("path", "")).strip()
            return self._send(200, open_exports(p))

        return self._send(404, {"ok": False, "error": "not_found"})


if __name__ == "__main__":
    host = os.environ.get("FLOW_V2_HOST", "127.0.0.1")
    port = int(os.environ.get("FLOW_V2_PORT", "18777"))
    print(f"[flow_auto_v2] listening on http://{host}:{port}")
    ThreadingHTTPServer((host, port), H).serve_forever()
