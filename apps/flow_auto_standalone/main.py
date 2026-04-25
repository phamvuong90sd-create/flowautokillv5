#!/usr/bin/env python3
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import threading
import time
import runpy
import uuid  # keep stdlib uuid bundled for embedded scripts
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime

APP_NAME = "FLOW AUTO VEO 3 BY VUONGPHAM V1.0"
APP_VERSION = "V2.0"

BASE_DIR = Path.home() / ".flow-auto-standalone"
SCRIPTS_DIR = BASE_DIR / "scripts"
FLOW_DIR = BASE_DIR / "flow-auto"
INBOUND_DIR = BASE_DIR / "inbound"
KEYS_DIR = BASE_DIR / "keys"

PID_RUN = FLOW_DIR / "job-state" / "standalone-runner.pid"
PID_WORKER = FLOW_DIR / "job-state" / "standalone-worker.pid"
STATE_FILE = FLOW_DIR / "job-state" / "standalone-runner.json"

SOURCE_ROOT = Path(__file__).resolve().parents[2]
SOURCE_SCRIPTS = SOURCE_ROOT / "scripts"

APP_LOCK_PORT = 18879
CDP_PORT = int(os.environ.get("FLOW_CDP_PORT", "18800"))
CDP_STATE = FLOW_DIR / "job-state" / "cdp-launch.json"


def resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return (base / rel).resolve()


def _bundled_playwright_node() -> str:
    if platform.system().lower() != "darwin":
        return ""

    m = (platform.machine() or "").lower()
    base = resource_path("payload/node/macos")
    pref = []
    if "arm" in m or "aarch" in m:
        pref = [base / "arm64" / "node", base / "x64" / "node"]
    else:
        pref = [base / "x64" / "node", base / "arm64" / "node"]

    for p in pref:
        try:
            if p.exists():
                try:
                    p.chmod(0o755)
                except Exception:
                    pass
                return str(p)
        except Exception:
            pass

    sys_node = shutil.which("node")
    return sys_node or ""


def env_vars() -> dict:
    e = os.environ.copy()
    e["FLOW_WORKSPACE"] = str(BASE_DIR)
    e["FLOW_INBOUND_DIR"] = str(INBOUND_DIR)
    e["FLOW_PY"] = python_bin()
    e["FLOW_RUNNER"] = str(SCRIPTS_DIR / "flow_batch_runner.py")
    if getattr(sys, "frozen", False):
        e["FLOW_RUNNER_EMBEDDED"] = "1"

    node_path = _bundled_playwright_node()
    if node_path:
        e["PLAYWRIGHT_NODEJS_PATH"] = node_path

    return e


def python_bin() -> str:
    p = BASE_DIR / ".venv-flow" / "bin" / "python"
    if p.exists():
        return str(p)
    p2 = BASE_DIR / ".venv-flow" / "Scripts" / "python.exe"
    if p2.exists():
        return str(p2)

    # onefile standalone: use self in script mode (no external python required)
    if getattr(sys, "frozen", False):
        return sys.executable

    return "python" if platform.system().lower() == "windows" else "python3"


def py_script_cmd(script_path: Path, args=None):
    args = args or []
    py = python_bin()
    if getattr(sys, "frozen", False) and os.path.abspath(py) == os.path.abspath(sys.executable):
        return [py, "--run-script", str(script_path), *args]
    return [py, str(script_path), *args]


def run_cmd(cmd, timeout=180):
    kwargs = {"capture_output": True, "text": True, "timeout": timeout, "env": env_vars()}
    if platform.system().lower() == "windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    p = subprocess.run(cmd, **kwargs)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def ensure_dirs():
    for p in [SCRIPTS_DIR, FLOW_DIR / "job-state", FLOW_DIR / "debug", FLOW_DIR / "done", FLOW_DIR / "processing", INBOUND_DIR, KEYS_DIR]:
        p.mkdir(parents=True, exist_ok=True)


def bootstrap_scripts():
    ensure_dirs()
    required = [
        "flow_batch_runner.py",
        "flow_license_online_check.py",
        "flow_download_all_completed.py",
        "flow_postprocess_videos.py",
        "flow_export_open.py",
        "flow_google_login_auto_check.py",
        "flow_chrome_repair_reinstall.sh",
        "flow_queue_worker.py",
    ]

    payload_scripts = resource_path("payload/scripts")

    for f in required:
        src = SOURCE_SCRIPTS / f
        if not src.exists():
            alt = payload_scripts / f
            if alt.exists():
                src = alt
        if src.exists():
            dst = SCRIPTS_DIR / f
            shutil.copy2(src, dst)
            try:
                dst.chmod(0o755)
            except Exception:
                pass

    src_bin = SOURCE_SCRIPTS / "bin" / "flow_license_verify"
    if not src_bin.exists():
        alt_bin = payload_scripts / "bin" / "flow_license_verify"
        if alt_bin.exists():
            src_bin = alt_bin

    if src_bin.exists():
        (SCRIPTS_DIR / "bin").mkdir(parents=True, exist_ok=True)
        dst_bin = SCRIPTS_DIR / "bin" / "flow_license_verify"
        shutil.copy2(src_bin, dst_bin)
        try:
            dst_bin.chmod(0o755)
        except Exception:
            pass


def acquire_lock():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", APP_LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        try:
            s.close()
        except Exception:
            pass
        return None


def _cdp_ready() -> bool:
    try:
        sock = socket.create_connection(("127.0.0.1", CDP_PORT), timeout=1.2)
        sock.close()
        return True
    except Exception:
        return False


def _find_browser_executable_windows():
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for p in candidates:
        if p and Path(p).exists():
            return p
    return None


def _find_browser_executable_macos():
    home = Path.home()
    candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        home / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        home / "Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for p in candidates:
        try:
            if p.exists():
                return str(p)
        except Exception:
            pass
    return ""


def ensure_cdp() -> dict:
    if _cdp_ready():
        return {"ok": True, "reason": "already_ready"}

    now = int(time.time())
    if CDP_STATE.exists():
        try:
            last = json.loads(CDP_STATE.read_text(encoding="utf-8"))
            if now - int(last.get("ts", 0)) < 20:
                for _ in range(15):
                    if _cdp_ready():
                        return {"ok": True, "reason": "warmup_wait"}
                    time.sleep(1)
        except Exception:
            pass

    os_name = platform.system().lower()
    launched = False
    launch_error = ""
    profile_dir = BASE_DIR / "chrome-cdp-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os_name == "windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            exe = _find_browser_executable_windows()
            if not exe:
                return {"ok": False, "reason": "browser_not_found"}
            cmd = [
                exe,
                f"--remote-debugging-port={CDP_PORT}",
                "--remote-debugging-address=127.0.0.1",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "https://labs.google/fx/vi/tools/flow",
            ]
            subprocess.Popen(cmd, **kwargs)
            launched = True
        elif os_name == "darwin":
            kwargs["start_new_session"] = True
            exe = _find_browser_executable_macos()
            if not exe:
                return {"ok": False, "reason": "browser_not_found"}

            # Tránh cơ chế open -a làm rơi/nuốt args CDP trên vài máy macOS
            cmd = [
                exe,
                f"--remote-debugging-port={CDP_PORT}",
                "--remote-debugging-address=127.0.0.1",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "https://labs.google/fx/vi/tools/flow",
            ]
            subprocess.Popen(cmd, **kwargs)
            launched = True
        else:
            kwargs["start_new_session"] = True
            last_err = None
            for exe in ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]:
                try:
                    cmd = [
                        exe,
                        f"--remote-debugging-port={CDP_PORT}",
                        "--remote-debugging-address=127.0.0.1",
                        f"--user-data-dir={profile_dir}",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "https://labs.google/fx/vi/tools/flow",
                    ]
                    subprocess.Popen(cmd, **kwargs)
                    launched = True
                    break
                except Exception as e:
                    last_err = e
            if not launched and last_err:
                launch_error = str(last_err)
    except Exception as e:
        launch_error = str(e)

    try:
        CDP_STATE.parent.mkdir(parents=True, exist_ok=True)
        CDP_STATE.write_text(json.dumps({"ts": now, "launched": launched, "error": launch_error}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    wait_loops = 55 if os_name == "darwin" else 35
    for _ in range(wait_loops):
        if _cdp_ready():
            return {"ok": True, "reason": "launched", "launched": launched}
        time.sleep(1)

    return {"ok": False, "reason": "cdp_not_ready", "launched": launched, "error": launch_error}


def machine_id() -> str:
    os_name = platform.system().lower()

    # Windows
    if os_name == "windows":
        ps = (
            "$x=''; "
            "try{$x=(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography' -Name MachineGuid -ErrorAction Stop).MachineGuid}catch{}; "
            "if([string]::IsNullOrWhiteSpace($x)){try{$x=(Get-CimInstance Win32_ComputerSystemProduct -ErrorAction SilentlyContinue).UUID}catch{}}; "
            "if([string]::IsNullOrWhiteSpace($x)){$x=$env:COMPUTERNAME}; $x.ToString().Trim().ToLower()"
        )
        try:
            c, o, _ = run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=20)
            if c == 0 and o:
                return o.strip().lower()
        except Exception:
            pass
        return platform.node().lower().strip() or "unknown"

    # macOS: lấy IOPlatformUUID, tránh gọi binary verifier sai kiến trúc
    if os_name == "darwin":
        try:
            c, o, _ = run_cmd([
                "ioreg", "-rd1", "-c", "IOPlatformExpertDevice"
            ], timeout=20)
            if c == 0 and o:
                for line in o.splitlines():
                    if "IOPlatformUUID" in line:
                        # ví dụ: "IOPlatformUUID" = "XXXX-..."
                        val = line.split("=", 1)[-1].strip().strip('"')
                        if val:
                            return val.lower()
        except Exception:
            pass
        return platform.node().lower().strip() or "unknown"

    # Linux: ưu tiên /etc/machine-id rồi fallback
    if os_name == "linux":
        try:
            p = Path("/etc/machine-id")
            if p.exists():
                v = p.read_text(encoding="utf-8", errors="ignore").strip()
                if v:
                    return v.lower()
        except Exception:
            pass

    # Fallback cuối cùng (không để crash)
    return platform.node().lower().strip() or "unknown"


def _parse_iso_dt(s: str):
    s = (s or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _extract_expiry(obj: dict):
    data = obj.get("data", {}) if isinstance(obj, dict) else {}
    for k in ("expires_at", "grace_until"):
        v = data.get(k)
        if v:
            return v
    return ""


def _expired_now(exp_iso: str) -> bool:
    dt = _parse_iso_dt(exp_iso)
    if not dt:
        return False
    now = datetime.utcnow().astimezone(dt.tzinfo)
    return now >= dt


def license_check():
    checker = SCRIPTS_DIR / "flow_license_online_check.py"
    if not checker.exists():
        return False, {"ok": False, "reason": "checker_missing"}
    c, o, e = run_cmd(py_script_cmd(checker, ["--check", "--json"]), timeout=90)
    raw = o or e
    try:
        obj = json.loads(raw)
    except Exception:
        obj = {"ok": False, "raw": raw}

    ok = (c == 0 and bool(obj.get("ok", False)))

    # Cưỡng chế hết hạn tại client: đúng ngày hết hạn thì bắt nhập key mới
    exp = _extract_expiry(obj)
    if exp and _expired_now(exp):
        obj["ok"] = False
        obj["reason"] = "expired_local"
        obj["expires_at"] = exp
        ok = False

    return ok, obj


def _friendly_activate_error(raw: str) -> str:
    t = (raw or "").lower()
    if any(k in t for k in ["expired", "hết hạn"]):
        return "Key đã hết hạn. Vui lòng nhập key mới."
    if any(k in t for k in ["revoked", "invalid", "machine_mismatch", "forbidden", "403"]):
        return "Kích hoạt không thành công. Key không hợp lệ hoặc đã bị thu hồi."
    if any(k in t for k in ["timeout", "network", "connection", "failed to establish", "dns"]):
        return "Kích hoạt không thành công. Vui lòng kiểm tra kết nối mạng và thử lại."
    return "Kích hoạt không thành công. Vui lòng kiểm tra key và thử lại."


def activate_key(license_key: str, api_base: str):
    checker = SCRIPTS_DIR / "flow_license_online_check.py"
    if not checker.exists():
        return False, "Kích hoạt không thành công. Thiếu thành phần license."
    mid = machine_id()
    c1, o1, e1 = run_cmd(py_script_cmd(checker, ["--setup", "--api-base", api_base, "--license-key", license_key, "--machine-id", mid]), timeout=120)
    if c1 != 0:
        return False, _friendly_activate_error(e1 or o1 or "setup failed")
    c2, o2, e2 = run_cmd(py_script_cmd(checker, ["--activate", "--json"]), timeout=180)
    if c2 != 0:
        return False, _friendly_activate_error(e2 or o2 or "activate failed")

    # parse json output to map reason without exposing server URL/details
    msg = o2 or "activated"
    try:
        obj = json.loads(msg)
        if not obj.get("ok", False):
            return False, _friendly_activate_error(str(obj.get("reason", "")))
    except Exception:
        pass

    return True, "Kích hoạt thành công"


def _is_running(pid: int) -> bool:
    if not pid:
        return False

    if platform.system().lower() == "windows":
        # os.kill(pid, 0) trên Windows có thể false-negative (PermissionError)
        c, o, _ = run_cmd(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], timeout=10)
        if c == 0 and o and "No tasks are running" not in o and "INFO:" not in o:
            return True
        return False

    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _kill_pid(pid: int):
    try:
        if platform.system().lower() == "windows":
            run_cmd(["taskkill", "/PID", str(pid), "/F"], timeout=20)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def run_status():
    pid = None
    stale_pid = None
    if PID_RUN.exists():
        try:
            pid = int(PID_RUN.read_text().strip())
        except Exception:
            pid = None
    running = bool(pid and _is_running(pid))
    if pid and not running:
        stale_pid = pid
        PID_RUN.unlink(missing_ok=True)
        pid = None
    return {"ok": True, "running": running, "pid": pid, "stale_pid": stale_pid}


def worker_status():
    pid = None
    stale_pid = None
    if PID_WORKER.exists():
        try:
            pid = int(PID_WORKER.read_text().strip())
        except Exception:
            pid = None
    running = bool(pid and _is_running(pid))
    if pid and not running:
        stale_pid = pid
        PID_WORKER.unlink(missing_ok=True)
        pid = None
    return {"ok": True, "worker_running": running, "worker_pid": pid, "stale_worker_pid": stale_pid}


def start_run(prompts_path: str, limit: int, start_from: int, refs_dir: str = "", task_mode: str = "createvideo", video_sub_mode: str = "frames", reference_mode: str = "ingredients", paired_mode: bool = True, flow_model: str = "default", flow_aspect_ratio: str = "16:9", flow_count: str = "1"):
    st = run_status()
    if st.get("running"):
        return {"ok": True, "reason": "already_running", **st}

    cdp = ensure_cdp()
    if not cdp.get("ok"):
        return {"ok": False, "error": "cdp_not_ready", "cdp": cdp}

    src = Path(prompts_path)
    if not src.exists():
        return {"ok": False, "error": f"Không thấy file: {src}"}

    use_file = src
    if limit > 0:
        txt = src.read_text(encoding="utf-8", errors="ignore")
        blocks = [b.strip() for b in txt.split("\n\n") if b.strip()]
        use_file = FLOW_DIR / f"current-text-prompt-first{limit}-standalone.txt"
        use_file.write_text("\n\n".join(blocks[:limit]) + "\n", encoding="utf-8")

    log_file = FLOW_DIR / "debug" / "standalone-runner.log"
    out = open(log_file, "a", encoding="utf-8")

    runner_args = [
        "--prompts", str(use_file),
        "--state", str(STATE_FILE),
        "--start-from", str(start_from),
        "--cdp", f"http://127.0.0.1:{CDP_PORT}",
        "--task-mode", task_mode,
        "--video-sub-mode", video_sub_mode,
        "--reference-mode", reference_mode,
        "--paired-mode" if paired_mode else "--no-paired-mode",
        "--flow-model", flow_model,
        "--flow-aspect-ratio", flow_aspect_ratio,
        "--flow-count", str(flow_count),
        "--auto-download",
        "--download-resolution", "720",
    ]
    if refs_dir and Path(refs_dir).exists():
        runner_args += ["--refs-dir", str(Path(refs_dir))]

    cmd = py_script_cmd(SCRIPTS_DIR / "flow_batch_runner.py", runner_args)

    kwargs = {"stdout": out, "stderr": subprocess.STDOUT, "env": env_vars()}
    if platform.system().lower() == "windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    p = subprocess.Popen(cmd, **kwargs)
    PID_RUN.write_text(str(p.pid), encoding="utf-8")
    return {"ok": True, "running": True, "pid": p.pid, "log": str(log_file), "prompts": str(use_file)}


def stop_run():
    if not PID_RUN.exists():
        return {"ok": True, "running": False}
    try:
        pid = int(PID_RUN.read_text().strip())
    except Exception:
        pid = None
    if pid:
        _kill_pid(pid)
    PID_RUN.unlink(missing_ok=True)
    return {"ok": True, "running": False, "pid": pid}


def start_worker():
    st = worker_status()
    if st.get("worker_running"):
        return {"ok": True, "reason": "already_running", **st}

    cmd = py_script_cmd(SCRIPTS_DIR / "flow_queue_worker.py")
    log_file = FLOW_DIR / "debug" / "standalone-worker.log"
    out = open(log_file, "a", encoding="utf-8")

    kwargs = {"stdout": out, "stderr": subprocess.STDOUT, "env": env_vars()}
    if platform.system().lower() == "windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    p = subprocess.Popen(cmd, **kwargs)
    PID_WORKER.write_text(str(p.pid), encoding="utf-8")

    # verify worker doesn't die immediately
    time.sleep(1.5)
    alive = _is_running(p.pid)
    if not alive:
        time.sleep(1.0)
        alive = _is_running(p.pid)
    if not alive:
        PID_WORKER.unlink(missing_ok=True)
        tail = ""
        try:
            tail = "\n".join((log_file.read_text(encoding="utf-8", errors="ignore").splitlines() or [])[-40:])
        except Exception:
            pass
        return {
            "ok": False,
            "worker_running": False,
            "worker_pid": None,
            "error": "worker_exited_immediately",
            "log": str(log_file),
            "log_tail": tail,
        }

    return {"ok": True, "worker_running": True, "worker_pid": p.pid, "log": str(log_file)}


def stop_worker():
    if not PID_WORKER.exists():
        return {"ok": True, "worker_running": False}
    try:
        pid = int(PID_WORKER.read_text().strip())
    except Exception:
        pid = None
    if pid:
        _kill_pid(pid)
    PID_WORKER.unlink(missing_ok=True)
    return {"ok": True, "worker_running": False, "worker_pid": pid}


def run_script(name: str, args=None, timeout=600):
    args = args or []
    script = SCRIPTS_DIR / name
    if not script.exists():
        return {"ok": False, "error": f"Thiếu script: {name}"}
    c, o, e = run_cmd(py_script_cmd(script, args), timeout=timeout)
    return {"ok": c == 0, "code": c, "stdout": o, "stderr": e}


class ActivationDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title(f"Kích hoạt {APP_NAME}")
        self.geometry("760x260")
        self.resizable(False, False)
        self.result = False

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        self.mid_var = tk.StringVar(value=machine_id())
        ttk.Label(frm, text="Machine-ID:").pack(anchor="w")
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=(2, 8))
        ttk.Entry(row, textvariable=self.mid_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Copy", command=self.copy_mid).pack(side="left", padx=6)

        ttk.Label(frm, text="LICENSE_KEY:").pack(anchor="w")
        self.key_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.key_var).pack(fill="x", pady=(2, 8))

        # API base ẩn khỏi giao diện (dùng mặc định nội bộ)
        self.api_var = tk.StringVar(value="https://server-auto-tool.vercel.app/api/license")

        self.status = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.status, foreground="#cc5500").pack(anchor="w")

        btn = ttk.Frame(frm)
        btn.pack(fill="x", pady=10)
        self.btn_act = ttk.Button(btn, text="Kích hoạt", command=self.activate)
        self.btn_act.pack(side="left")
        ttk.Button(btn, text="Thoát", command=self.destroy).pack(side="right")

    def copy_mid(self):
        self.clipboard_clear()
        self.clipboard_append(self.mid_var.get())
        self.status.set("Đã copy Machine-ID")

    def activate(self):
        key = self.key_var.get().strip()
        api = self.api_var.get().strip()
        if not key:
            self.status.set("Thiếu LICENSE_KEY")
            return
        self.btn_act.configure(state="disabled")
        self.status.set("Đang kích hoạt...")
        self.update_idletasks()
        ok, msg = activate_key(key, api)
        self.btn_act.configure(state="normal")
        if ok:
            self.result = True
            messagebox.showinfo("Thành công", "Kích hoạt thành công")
            self.destroy()
        else:
            self.status.set(str(msg)[:250])
            messagebox.showerror("Lỗi", str(msg)[:500])


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} [{APP_VERSION}]")
        self.root.geometry("1180x760")

        self.prompts_var = tk.StringVar(value="")
        self.limit_var = tk.StringVar(value="20")
        self.start_var = tk.StringVar(value="1")
        self.input_video_dir_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.output_video_var = tk.StringVar(value="")
        self.refs_dir_var = tk.StringVar(value="")
        self.task_mode_var = tk.StringVar(value="createvideo")
        self.video_sub_mode_var = tk.StringVar(value="frames")
        self.reference_mode_var = tk.StringVar(value="ingredients")
        self.paired_mode_var = tk.BooleanVar(value=True)
        self.model_var = tk.StringVar(value="default")
        self.aspect_var = tk.StringVar(value="16:9")
        self.count_var = tk.StringVar(value="1")
        self.status_var = tk.StringVar(value="Sẵn sàng")

        self._style()
        self.build_ui()
        self.log({"ok": True, "app": APP_NAME, "version": APP_VERSION, "base": str(BASE_DIR)})

    def _style(self):
        s = ttk.Style(self.root)
        try:
            s.theme_use("clam")
        except Exception:
            pass

        # Dark/web-like theme
        bg = "#0b1220"
        panel = "#111827"
        panel2 = "#1f2937"
        fg = "#e5e7eb"
        muted = "#94a3b8"
        accent = "#2563eb"
        accent_active = "#1d4ed8"

        try:
            self.root.configure(bg=bg)
        except Exception:
            pass

        def safe_configure(style_name, **kwargs):
            try:
                s.configure(style_name, **kwargs)
            except Exception:
                pass

        def safe_map(style_name, **kwargs):
            try:
                s.map(style_name, **kwargs)
            except Exception:
                pass

        safe_configure("TFrame", background=bg)
        # một số option như bordercolor/focusthickness có thể lỗi trên macOS Tk
        safe_configure("TLabelframe", background=panel, foreground=fg, relief="solid")
        safe_configure("TLabelframe.Label", background=panel, foreground=fg, font=("Arial", 10, "bold"))
        safe_configure("TLabel", background=bg, foreground=fg)
        safe_configure("TEntry", fieldbackground=panel2, foreground=fg, insertcolor=fg)
        safe_configure("TButton", padding=9, background=accent, foreground="white", borderwidth=0)
        safe_map("TButton", background=[("active", accent_active), ("pressed", accent_active)], foreground=[("disabled", muted)])

        # fallback màu nền truyền thống để tránh giao diện lỗi nếu ttk style không nhận
        try:
            self.root.option_add("*Background", bg)
            self.root.option_add("*Foreground", fg)
        except Exception:
            pass

    def _btn(self, parent, text, cmd, r, c, cs=1):
        b = ttk.Button(parent, text=text, command=cmd)
        b.grid(row=r, column=c, columnspan=cs, sticky="nsew", padx=4, pady=4)
        return b

    def build_ui(self):
        shell = ttk.Frame(self.root, padding=8)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        nb = ttk.Notebook(shell)
        nb.grid(row=0, column=0, sticky="nsew")

        tab_main = ttk.Frame(nb)
        tab_sub = ttk.Frame(nb)
        nb.add(tab_main, text="Vận hành")
        nb.add(tab_sub, text="Đăng ký sử dụng")

        wrap = ttk.Frame(tab_main, padding=12)
        wrap.pack(fill="both", expand=True)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(3, weight=1)

        ttk.Label(wrap, text="FLOW AUTO VEO 3 — V2.0", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))

        top = ttk.LabelFrame(wrap, text="Thiết lập chạy")
        top.grid(row=1, column=0, sticky="nsew")
        for i in range(8):
            top.columnconfigure(i, weight=1)

        ttk.Label(top, text="File prompt").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.prompts_var).grid(row=0, column=1, columnspan=6, sticky="we", padx=4)
        self._btn(top, "📁 Chọn file", self.pick_prompt, 0, 7)

        ttk.Label(top, text="Số prompt").grid(row=1, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.limit_var, width=10).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(top, text="Bắt đầu từ").grid(row=1, column=2, sticky="e")
        ttk.Entry(top, textvariable=self.start_var, width=10).grid(row=1, column=3, sticky="w", padx=4)

        ttk.Label(top, text="Video nguồn").grid(row=2, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.input_video_dir_var).grid(row=2, column=1, columnspan=3, sticky="we", padx=4)
        ttk.Label(top, text="File xuất").grid(row=2, column=4, sticky="e")
        ttk.Entry(top, textvariable=self.output_video_var).grid(row=2, column=5, columnspan=3, sticky="we", padx=4)

        ttk.Label(top, text="Thư mục ảnh ref").grid(row=3, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.refs_dir_var).grid(row=3, column=1, columnspan=6, sticky="we", padx=4)
        self._btn(top, "🖼 Chọn thư mục ảnh", self.pick_refs_dir, 3, 7)

        ttk.Label(top, text="Mode").grid(row=4, column=0, sticky="w")
        ttk.Combobox(top, textvariable=self.task_mode_var, values=["createvideo", "createimage"], state="readonly", width=14).grid(row=4, column=1, sticky="w", padx=4)

        ttk.Label(top, text="Sub-mode").grid(row=4, column=2, sticky="e")
        ttk.Combobox(top, textvariable=self.video_sub_mode_var, values=["frames", "ingredients"], state="readonly", width=12).grid(row=4, column=3, sticky="w", padx=4)

        ttk.Label(top, text="Model").grid(row=5, column=0, sticky="w")
        ttk.Combobox(top, textvariable=self.model_var, values=["default", "veo3_lite", "veo3_fast", "veo3_quality", "nano_banana_pro", "nano_banana2", "imagen4"], state="readonly", width=18).grid(row=5, column=1, sticky="w", padx=4)

        ttk.Label(top, text="Ref mode").grid(row=5, column=2, sticky="e")
        ttk.Combobox(top, textvariable=self.reference_mode_var, values=["ingredients", "tag"], state="readonly", width=12).grid(row=5, column=3, sticky="w", padx=4)

        ttk.Checkbutton(top, text="Paired mode (1.jpg↔prompt1, 2.jpg↔prompt2)", variable=self.paired_mode_var).grid(row=5, column=4, columnspan=4, sticky="w", padx=4)

        ttk.Label(top, text="Tỉ lệ").grid(row=4, column=4, sticky="e")
        ttk.Combobox(top, textvariable=self.aspect_var, values=["16:9", "9:16", "square", "landscape_4_3", "portrait_3_4"], state="readonly", width=14).grid(row=4, column=5, sticky="w", padx=4)

        ttk.Label(top, text="Số output").grid(row=4, column=6, sticky="e")
        ttk.Combobox(top, textvariable=self.count_var, values=["1", "2", "3", "4"], state="readonly", width=8).grid(row=4, column=7, sticky="w", padx=4)

        mid = ttk.Frame(wrap)
        mid.grid(row=2, column=0, sticky="nsew", pady=8)
        for i in range(3):
            mid.columnconfigure(i, weight=1)

        ops = ttk.LabelFrame(mid, text="Vận hành")
        ops.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        for i in range(2):
            ops.columnconfigure(i, weight=1)
        self._btn(ops, "▶ Bắt đầu", self.on_start, 0, 0)
        self._btn(ops, "⏹ Dừng", self.on_stop, 0, 1)
        self._btn(ops, "⚡ Chạy nhanh", self.on_quick, 1, 0)
        self._btn(ops, "📊 Trạng thái", self.on_status, 1, 1)

        worker = ttk.LabelFrame(mid, text="Worker")
        worker.grid(row=0, column=1, sticky="nsew", padx=6)
        for i in range(2):
            worker.columnconfigure(i, weight=1)
        self._btn(worker, "🚀 Start worker", self.on_worker_start, 0, 0)
        self._btn(worker, "🛑 Stop worker", self.on_worker_stop, 0, 1)
        self._btn(worker, "📥 Nạp file vào queue", self.on_enqueue_prompt, 1, 0, 2)
        self._btn(worker, "🧾 Worker status", self.on_worker_status, 2, 0, 2)

        tools = ttk.LabelFrame(mid, text="Tính năng")
        tools.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        for i in range(2):
            tools.columnconfigure(i, weight=1)
        self._btn(tools, "🔐 License check", self.on_license_check, 0, 0)
        self._btn(tools, "📥 Tải video xong", self.on_download_done, 0, 1)
        self._btn(tools, "🎬 Hậu kỳ", self.on_postprocess, 1, 0)
        self._btn(tools, "📂 Mở exports", self.on_open_exports, 1, 1)
        self._btn(tools, "🔎 Google check", self.on_google_check, 2, 0)
        self._btn(tools, "🧹 Xóa cache", self.on_clear_cache, 2, 1)

        logf = ttk.LabelFrame(wrap, text="Thông báo hệ thống")
        logf.grid(row=3, column=0, sticky="nsew")
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        self.out = tk.Text(logf, height=14, bg="#0f172a", fg="#e2e8f0", insertbackground="#e2e8f0")
        self.out.grid(row=0, column=0, sticky="nsew")

        st = ttk.Frame(wrap)
        st.grid(row=4, column=0, sticky="we", pady=(8, 0))
        ttk.Label(st, text="Trạng thái:").pack(side="left")
        ttk.Label(st, textvariable=self.status_var).pack(side="left", padx=(6, 0))
        ttk.Label(st, text="   |   Chỉ hiển thị thông báo thành công/thất bại", foreground="#94a3b8").pack(side="left", padx=(8,0))

        # TAB: Đăng ký sử dụng
        sub_wrap = ttk.Frame(tab_sub, padding=16)
        sub_wrap.pack(fill="both", expand=True)

        exp = "Không rõ"
        try:
            ok, r = license_check()
            exp = _extract_expiry(r) or "Chưa kích hoạt"
            if not ok and exp == "Không rõ":
                exp = "Không hợp lệ/đã hết hạn"
        except Exception:
            pass

        ttk.Label(sub_wrap, text="ĐĂNG KÝ SỬ DỤNG", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0,10))
        ttk.Label(sub_wrap, text=f"Thời hạn key hiện tại: {exp}", font=("Segoe UI", 11)).pack(anchor="w", pady=(0,10))
        ttk.Label(sub_wrap, text="Thông tin hỗ trợ cấp key: Zalo 0989139295", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0,12))
        ttk.Label(sub_wrap, text="Quét mã QR để chuyển khoản đăng ký:").pack(anchor="w")

        qr_path = resource_path("assets/subscription_qr.png")
        try:
            img = tk.PhotoImage(file=str(qr_path))
            self._qr_img = img
            ttk.Label(sub_wrap, image=img).pack(anchor="w", pady=(8, 8))
        except Exception:
            ttk.Label(sub_wrap, text=f"QR: {qr_path}").pack(anchor="w", pady=(8, 8))

    def _ui(self, fn):
        try:
            if self.root.winfo_exists():
                self.root.after(0, fn)
        except Exception:
            pass

    def _set_status(self, t):
        self._ui(lambda: self.status_var.set(t))

    def _summarize(self, obj):
        if not isinstance(obj, dict):
            return f"ℹ️ {str(obj)}"

        ok = obj.get("ok")
        if ok is True:
            if obj.get("error"):
                return f"⚠️ {obj.get('error')}"
            if obj.get("expires_at"):
                return f"✅ License hợp lệ • hết hạn: {obj.get('expires_at')}"
            if obj.get("reason"):
                return f"✅ {obj.get('reason')}"
            if obj.get("running") is True:
                return "✅ Đã bắt đầu chạy"
            if obj.get("worker_running") is True:
                return "✅ Worker đang chạy"
            if obj.get("queued_file"):
                return f"✅ Đã nạp queue: {Path(obj.get('queued_file')).name}"
            return "✅ Thành công"

        if ok is False:
            if obj.get("reason") in {"expired", "expired_local"}:
                return f"❌ License đã hết hạn • {obj.get('expires_at', '')}".strip()
            if obj.get("error"):
                return f"❌ {obj.get('error')}"
            return "❌ Thất bại"

        return "ℹ️ Đã cập nhật trạng thái"

    def log(self, obj):
        ts = datetime.now().strftime("%H:%M:%S")
        payload = f"[{ts}] {self._summarize(obj)}\n"

        def _append():
            if self.out.winfo_exists():
                self.out.insert("end", payload)
                # giữ tối đa ~200 dòng thông báo
                lines = int(float(self.out.index('end-1c').split('.')[0]))
                if lines > 220:
                    self.out.delete("1.0", f"{lines-200}.0")
                self.out.see("end")

        self._ui(_append)

    def pick_prompt(self):
        init_dir = str(Path(self.prompts_var.get()).parent) if self.prompts_var.get().strip() else str(FLOW_DIR)
        p = filedialog.askopenfilename(title="Chọn file text kịch bản", initialdir=init_dir, filetypes=[("Text", "*.txt *.md"), ("All", "*.*")])
        if p:
            self.prompts_var.set(p)

    def pick_refs_dir(self):
        init_dir = self.refs_dir_var.get().strip() or str(Path.home())
        p = filedialog.askdirectory(title="Chọn thư mục ảnh tham chiếu", initialdir=init_dir)
        if p:
            self.refs_dir_var.set(p)

    def _bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def on_start(self):
        self._set_status("Đang start...")
        def _run():
            try:
                r = start_run(
                    self.prompts_var.get().strip(),
                    int(self.limit_var.get() or "20"),
                    int(self.start_var.get() or "1"),
                    self.refs_dir_var.get().strip(),
                    self.task_mode_var.get().strip(),
                    self.video_sub_mode_var.get().strip(),
                    self.reference_mode_var.get().strip(),
                    bool(self.paired_mode_var.get()),
                    self.model_var.get().strip(),
                    self.aspect_var.get().strip(),
                    self.count_var.get().strip(),
                )
                self.log(r)
            except Exception as e:
                self.log({"ok": False, "error": str(e)})
            self._set_status("Sẵn sàng")
        self._bg(_run)

    def on_quick(self):
        self._set_status("Đang quick start...")
        def _run():
            try:
                r = start_run(
                    self.prompts_var.get().strip(),
                    10,
                    1,
                    self.refs_dir_var.get().strip(),
                    self.task_mode_var.get().strip(),
                    self.video_sub_mode_var.get().strip(),
                    self.reference_mode_var.get().strip(),
                    bool(self.paired_mode_var.get()),
                    self.model_var.get().strip(),
                    self.aspect_var.get().strip(),
                    self.count_var.get().strip(),
                )
                self.log(r)
            except Exception as e:
                self.log({"ok": False, "error": str(e)})
            self._set_status("Sẵn sàng")
        self._bg(_run)

    def on_stop(self):
        self.log(stop_run())

    def on_status(self):
        st = run_status()
        st.update(worker_status())
        self.log(st)

    def on_worker_start(self):
        self.log(start_worker())

    def on_worker_stop(self):
        self.log(stop_worker())

    def on_enqueue_prompt(self):
        src = self.prompts_var.get().strip()
        if not src:
            self.log({"ok": False, "error": "Thiếu đường dẫn file prompt"})
            return
        p = Path(src)
        if not p.exists():
            self.log({"ok": False, "error": f"Không thấy file: {p}"})
            return

        INBOUND_DIR.mkdir(parents=True, exist_ok=True)
        dst = INBOUND_DIR / p.name
        if dst.exists():
            dst = INBOUND_DIR / f"{p.stem}-{int(time.time())}{p.suffix}"
        shutil.copy2(p, dst)
        self.log({"ok": True, "queued_file": str(dst), "hint": "Worker sẽ tự quét và chạy file trong inbound"})

    def on_worker_status(self):
        self.log(worker_status())

    def on_license_check(self):
        ok, r = license_check()
        exp = _extract_expiry(r)
        reason = r.get("reason") if isinstance(r, dict) else ""
        payload = {"ok": ok, "reason": reason}
        if exp:
            payload["expires_at"] = exp
        self.log(payload)

        if exp:
            try:
                messagebox.showinfo("License", f"Ngày hết hạn: {exp}")
            except Exception:
                pass

    def on_download_done(self):
        self.log(run_script("flow_download_all_completed.py", timeout=1200))

    def on_postprocess(self):
        args = []
        if self.input_video_dir_var.get().strip():
            args += ["--input-dir", self.input_video_dir_var.get().strip()]
        if self.output_video_var.get().strip():
            args += ["--output", self.output_video_var.get().strip()]
        self.log(run_script("flow_postprocess_videos.py", args=args, timeout=2400))

    def on_open_exports(self):
        p = self.output_video_var.get().strip()
        self.log(run_script("flow_export_open.py", args=[p] if p else [], timeout=120))

    def on_google_check(self):
        self.log(run_script("flow_google_login_auto_check.py", timeout=300))

    def on_clear_cache(self):
        removed = []
        if platform.system().lower() == "linux":
            targets = [
                Path.home() / ".config/google-chrome-flow/Default/Cache",
                Path.home() / ".config/google-chrome-flow/Default/Code Cache",
            ]
            for t in targets:
                if t.exists():
                    shutil.rmtree(t, ignore_errors=True)
                    removed.append(str(t))
        self.log({"ok": True, "removed": removed})


def run_embedded_script_mode() -> bool:
    # internal mode: FlowAutoStandalone.exe --run-script <script.py> [args...]
    if len(sys.argv) >= 3 and sys.argv[1] == "--run-script":
        script = Path(sys.argv[2])
        args = sys.argv[3:]
        if not script.exists():
            print(f"script not found: {script}", file=sys.stderr)
            raise SystemExit(2)
        old_argv = sys.argv[:]
        try:
            sys.argv = [str(script), *args]
            runpy.run_path(str(script), run_name="__main__")
        finally:
            sys.argv = old_argv
        return True
    return False


def main():
    lock = acquire_lock()
    if lock is None:
        t = tk.Tk(); t.withdraw()
        messagebox.showwarning("Đã chạy", "Standalone app đã mở sẵn.")
        t.destroy()
        return

    bootstrap_scripts()

    root = tk.Tk(); root.withdraw()
    ok, _ = license_check()
    if not ok:
        dlg = ActivationDialog(root)
        dlg.grab_set()
        root.wait_window(dlg)
        if not dlg.result:
            return

    root.deiconify()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        if not run_embedded_script_mode():
            main()
    except Exception as e:
        try:
            err_log = FLOW_DIR / "debug" / "standalone-crash.log"
            err_log.parent.mkdir(parents=True, exist_ok=True)
            import traceback
            err_log.write_text(traceback.format_exc(), encoding="utf-8")
            t = tk.Tk(); t.withdraw()
            messagebox.showerror(
                "Ứng dụng gặp lỗi",
                f"Không thể khởi động ứng dụng.\n\nChi tiết: {e}\n\nLog: {err_log}",
            )
            t.destroy()
        except Exception:
            pass
        raise
