#!/usr/bin/env python3
import json
import os
import platform
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from urllib import request, error
import ssl
import uuid
import socket
import time
from datetime import datetime

APP_NAME = "Flow Auto Pro Portable v4.1"
APP_VERSION = os.environ.get("FLOW_APP_VERSION", "3.4.5")
WS = Path(os.environ.get("FLOW_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))
SCRIPTS = WS / "scripts"
APPS_CORE = WS / "apps" / "flow_auto_v2" / "core"
API = "http://127.0.0.1:18777"
LICENSE_FILE = WS / "keys" / "license-online.json"
APP_LOCK_PORT = int(os.environ.get("FLOW_APP_LOCK_PORT", "18779"))


def acquire_single_instance_lock():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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


def python_bin() -> str:
    # Linux/macOS venv
    p1 = WS / ".venv-flow" / "bin" / "python"
    if p1.exists():
        return str(p1)
    # Windows venv
    p2 = WS / ".venv-flow" / "Scripts" / "python.exe"
    if p2.exists():
        return str(p2)
    # Fallback to current interpreter if available (works for PyInstaller env)
    exe = getattr(__import__('sys'), 'executable', '') or ''
    if exe:
        return exe
    return "python3"


def resource_path(rel: str) -> Path:
    base = Path(getattr(__import__('sys'), '_MEIPASS', Path(__file__).resolve().parent))
    return (base / rel).resolve()


def run_cmd(cmd, timeout=180):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def ensure_workspace_layout():
    (WS / "scripts").mkdir(parents=True, exist_ok=True)
    (WS / "apps" / "flow_auto_v2" / "core").mkdir(parents=True, exist_ok=True)
    (WS / "flow-auto" / "job-state").mkdir(parents=True, exist_ok=True)
    (WS / "flow-auto" / "debug").mkdir(parents=True, exist_ok=True)
    (WS / "flow-auto" / "exports").mkdir(parents=True, exist_ok=True)


def bootstrap_payload():
    ensure_workspace_layout()
    payload_scripts = resource_path("payload/scripts")
    payload_core = resource_path("payload/core")

    if payload_scripts.exists():
        for f in payload_scripts.glob("*"):
            if f.is_file():
                dst = SCRIPTS / f.name
                shutil.copy2(f, dst)
                try:
                    dst.chmod(0o755)
                except Exception:
                    pass

    if payload_core.exists():
        for f in payload_core.glob("*.py"):
            dst = APPS_CORE / f.name
            shutil.copy2(f, dst)


def ensure_service_running():
    try:
        with request.urlopen(API + "/health", timeout=1.5) as r:
            if r.status == 200:
                return True
    except Exception:
        pass

    service_py = APPS_CORE / "service.py"
    if service_py.exists():
        py = python_bin()
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if platform.system().lower() == "windows":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        started = False
        for cmd in ([py, str(service_py)], ["py", "-3", str(service_py)], ["python", str(service_py)], ["python3", str(service_py)]):
            try:
                subprocess.Popen(cmd, **kwargs)
                started = True
                break
            except Exception:
                continue

        if not started:
            return False

    for _ in range(30):
        try:
            with request.urlopen(API + "/health", timeout=1.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.6)
    return False


def ensure_openclaw_gateway():
    # cố gắng giao tiếp OpenClaw để service nền sẵn sàng
    try:
        c1, o1, e1 = run_cmd(["openclaw", "gateway", "status"], timeout=20)
        status_text = f"{o1}\n{e1}".lower()
        need_start = (c1 != 0) or ("stopped" in status_text) or ("not running" in status_text)
        if need_start:
            run_cmd(["openclaw", "gateway", "start"], timeout=40)
            time.sleep(1.5)
        return True
    except Exception:
        return False


def api_get(path):
    with request.urlopen(API + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def api_post(path, data):
    body = json.dumps(data).encode("utf-8")
    req = request.Request(API + path, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=240) as r:
        return json.loads(r.read().decode("utf-8"))


def load_license_cfg():
    try:
        if LICENSE_FILE.exists():
            return json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_license_cfg(cfg: dict):
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_base(base: str) -> str:
    b = (base or "").strip().rstrip("/")
    if b.endswith("/activate") or b.endswith("/verify"):
        b = b.rsplit("/", 1)[0]
    return b


def _http_open(req, timeout=15, context=None):
    with request.urlopen(req, timeout=timeout, context=context) as r:
        body = r.read().decode("utf-8")
        return r.status, (json.loads(body) if body else {})


def post_json(url: str, payload: dict, timeout: int = 15):
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # try normal TLS first
    try:
        return _http_open(req, timeout=timeout)
    except error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {"reason": f"http_{e.code}"}
        # 429: retry once with backoff
        if e.code == 429:
            time.sleep(2.0)
            try:
                return _http_open(req, timeout=timeout)
            except Exception:
                pass
        return e.code, data
    except Exception as e:
        primary_err = e

    # fallback unverified TLS (for bundled cert issues)
    try:
        insecure = ssl._create_unverified_context()
        return _http_open(req, timeout=timeout, context=insecure)
    except error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {"reason": f"http_{e.code}"}
        return e.code, data
    except Exception as e2:
        raise RuntimeError(f"request_failed: {e2} | primary: {primary_err}")


def machine_id():
    # 1) preferred verifier when available
    script = SCRIPTS / "bin" / "flow_license_verify"
    if script.exists() and os.access(script, os.X_OK):
        try:
            code, out, _ = run_cmd([str(script), "--machine-id"], timeout=20)
            if code == 0 and out.strip():
                return out.strip().lower()
        except Exception:
            pass

    # 2) Windows-compatible machine id (match installer/get_machine_id.cmd)
    if platform.system().lower() == "windows":
        ps = (
            "$x=''; "
            "try{$x=(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography' -Name MachineGuid -ErrorAction Stop).MachineGuid}catch{}; "
            "if([string]::IsNullOrWhiteSpace($x)){try{$x=(Get-CimInstance Win32_ComputerSystemProduct -ErrorAction SilentlyContinue).UUID}catch{}}; "
            "if([string]::IsNullOrWhiteSpace($x)){$x=$env:COMPUTERNAME}; "
            "$x.ToString().Trim().ToLower()"
        )
        try:
            code, out, _ = run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=25)
            if code == 0 and out.strip():
                return out.strip().lower()
        except Exception:
            pass

    # 3) generic fallback
    return platform.node().lower().strip() or "unknown"


def license_check():
    cfg = load_license_cfg()
    if not cfg.get("license_key") or not cfg.get("api_base"):
        return False, {"ok": False, "reason": "missing_setup"}

    payload = {
        "license_key": cfg.get("license_key", "").strip(),
        "machine_id": cfg.get("machine_id", machine_id()),
        "app_version": APP_VERSION,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nonce": uuid.uuid4().hex,
        "signed_token": cfg.get("signed_token", ""),
    }

    try:
        code, data = post_json(f"{normalize_base(cfg.get('api_base',''))}/verify", payload, timeout=12)
        ok = (code == 200 and bool(data.get("valid", False)))
        if ok:
            for k in ("signed_token", "expires_at", "grace_until", "next_check_at"):
                if data.get(k):
                    cfg[k] = data[k]
            save_license_cfg(cfg)
            return True, {"ok": True, "reason": "verified", "data": data}
        return False, {"ok": False, "reason": data.get("reason", f"http_{code}"), "data": data}
    except Exception:
        # offline fallback: if already has token+expiry, allow app open
        if cfg.get("signed_token") and (cfg.get("expires_at") or cfg.get("grace_until")):
            return True, {"ok": True, "reason": "offline_cached"}
        return False, {"ok": False, "reason": "network_error"}


def activate_with_key(key: str):
    key = (key or "").strip()
    if not key:
        return False, "LICENSE_KEY không được trống"

    api_base = normalize_base(os.environ.get("PRESET_LICENSE_API_BASE", "https://server-auto-tool.vercel.app/api/license"))
    mid = machine_id()
    payload = {
        "license_key": key,
        "machine_id": mid,
        "app_version": APP_VERSION,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nonce": uuid.uuid4().hex,
    }

    try:
        code, data = post_json(f"{api_base}/activate", payload, timeout=20)
    except Exception as e:
        return False, f"Lỗi mạng: {e}"

    if code != 200 or not bool(data.get("valid", True)):
        reason = str(data.get("reason", f"http_{code}"))
        if code == 429:
            return False, "Server quá tải (429). Đợi 1-2 phút rồi thử lại."
        if code == 403:
            return False, f"Key bị từ chối (403): {reason}. Machine-ID hiện tại: {mid}"
        return False, reason

    cfg = load_license_cfg()
    cfg.update({
        "api_base": api_base,
        "license_key": key,
        "machine_id": mid,
        "signed_token": data.get("signed_token", cfg.get("signed_token", "")),
        "expires_at": data.get("expires_at", cfg.get("expires_at", "")),
        "grace_until": data.get("grace_until", cfg.get("grace_until", "")),
        "next_check_at": data.get("next_check_at", cfg.get("next_check_at", "")),
        "last_verified_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    save_license_cfg(cfg)
    return True, "Kích hoạt thành công"


class ActivationDialog(tk.Toplevel):
    def clipboard_copy(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text or "")
            self.status.set("Đã copy Machine-ID")
        except Exception:
            pass

    def __init__(self, master):
        super().__init__(master)
        self.title("Kích hoạt ứng dụng")
        self.geometry("640x260")
        self.resizable(False, False)
        self.result = False

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        self.mid_var = tk.StringVar(value=machine_id())
        ttk.Label(frm, text="Machine-ID (dùng để cấp key):").pack(anchor="w")
        mid_row = ttk.Frame(frm)
        mid_row.pack(fill="x", pady=(2, 6))
        mid_entry = ttk.Entry(mid_row, textvariable=self.mid_var, width=64)
        mid_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(mid_row, text="Copy", command=lambda: self.clipboard_copy(self.mid_var.get())).pack(side="left", padx=(6, 0))

        ttk.Label(frm, text="Nhập LICENSE_KEY để kích hoạt online:").pack(anchor="w")
        self.key_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.key_var, width=76).pack(fill="x", pady=8)
        self.status = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.status, foreground="#cc5500").pack(anchor="w", pady=2)
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=10)
        self.btn_activate = ttk.Button(btns, text="Kích hoạt", command=self.do_activate)
        self.btn_activate.pack(side="left")
        ttk.Button(btns, text="Thoát", command=self.destroy).pack(side="right")

    def do_activate(self):
        key = self.key_var.get().strip()
        if not key:
            self.status.set("LICENSE_KEY không được trống")
            return

        self.btn_activate.configure(state="disabled")
        self.status.set("Đang kích hoạt...")
        self.update_idletasks()

        try:
            ok, msg = activate_with_key(key)
        except Exception as e:
            ok, msg = False, f"Lỗi không xác định: {e}"

        self.btn_activate.configure(state="normal")
        if ok:
            self.result = True
            self.status.set("Kích hoạt thành công")
            messagebox.showinfo("Thành công", "Kích hoạt thành công")
            self.destroy()
        else:
            self.status.set(str(msg)[:220])
            messagebox.showerror("Kích hoạt thất bại", str(msg)[:400])


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} — UI v5")
        self.root.geometry("1180x760")
        self.prompts_var = tk.StringVar(value=str(WS / "flow-auto/current-text-prompt.txt"))
        self.limit_var = tk.StringVar(value="20")
        self.start_var = tk.StringVar(value="1")
        self.input_video_dir_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.output_video_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self._style()
        self.build_ui()
        self.log({"ok": True, "app": APP_NAME, "ui": "v5", "workspace": str(WS)})

    def _style(self):
        s = ttk.Style(self.root)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("TButton", padding=8)
        s.configure("Card.TLabelframe", padding=10)
        s.configure("Card.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        s.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))

    def _btn(self, parent, text, cmd, r, c, cs=1):
        b = ttk.Button(parent, text=text, command=cmd)
        b.grid(row=r, column=c, columnspan=cs, sticky="nsew", padx=4, pady=4)
        return b

    def build_ui(self):
        wrap = ttk.Frame(self.root, padding=12)
        wrap.pack(fill="both", expand=True)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(3, weight=1)

        ttk.Label(wrap, text="FLOW AUTO PRO — DESKTOP CONTROL V5", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))

        top = ttk.LabelFrame(wrap, text="Thiết lập chạy", style="Card.TLabelframe")
        top.grid(row=1, column=0, sticky="nsew")
        for i in range(8):
            top.columnconfigure(i, weight=1)

        ttk.Label(top, text="File prompt").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.prompts_var).grid(row=0, column=1, columnspan=6, sticky="we", padx=4)
        self._btn(top, "📁 Chọn file", self.pick_prompt_file, 0, 7)

        ttk.Label(top, text="Số prompt").grid(row=1, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.limit_var, width=10).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(top, text="Bắt đầu từ").grid(row=1, column=2, sticky="e")
        ttk.Entry(top, textvariable=self.start_var, width=10).grid(row=1, column=3, sticky="w", padx=4)

        ttk.Label(top, text="Video nguồn").grid(row=2, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.input_video_dir_var).grid(row=2, column=1, columnspan=3, sticky="we", padx=4)
        ttk.Label(top, text="File xuất").grid(row=2, column=4, sticky="e")
        ttk.Entry(top, textvariable=self.output_video_var).grid(row=2, column=5, columnspan=3, sticky="we", padx=4)

        mid = ttk.Frame(wrap)
        mid.grid(row=2, column=0, sticky="nsew", pady=8)
        for i in range(3):
            mid.columnconfigure(i, weight=1)

        ops = ttk.LabelFrame(mid, text="Vận hành", style="Card.TLabelframe")
        ops.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        for i in range(2):
            ops.columnconfigure(i, weight=1)
        self._btn(ops, "▶ Bắt đầu", lambda: self.call_post("/api/start", {
            "prompts_path": self.prompts_var.get().strip(),
            "limit": int(self.limit_var.get().strip() or "20"),
            "start_from": int(self.start_var.get().strip() or "1"),
        }), 0, 0)
        self._btn(ops, "⏹ Dừng", lambda: self.call_post("/api/stop", {}), 0, 1)
        self._btn(ops, "⚡ Chạy nhanh", lambda: self.call_post("/api/run_quick_start", {"prompts_path": self.prompts_var.get().strip()}), 1, 0)
        self._btn(ops, "📊 Trạng thái", lambda: self.call_get("/api/status"), 1, 1)

        tools = ttk.LabelFrame(mid, text="Tính năng", style="Card.TLabelframe")
        tools.grid(row=0, column=1, sticky="nsew", padx=6)
        for i in range(2):
            tools.columnconfigure(i, weight=1)
        self._btn(tools, "📥 Tải video xong", lambda: self.call_post("/api/download_all_completed", {}), 0, 0)
        self._btn(tools, "🎬 Hậu kỳ", lambda: self.call_post("/api/postprocess_videos", {
            "input_dir": self.input_video_dir_var.get().strip(),
            "output_file": self.output_video_var.get().strip(),
        }), 0, 1)
        self._btn(tools, "📂 Mở video xuất", lambda: self.call_post("/api/open_exports", {"path": self.output_video_var.get().strip()}), 1, 0)
        self._btn(tools, "🔐 License", lambda: self.call_get("/api/license/check"), 1, 1)

        sysg = ttk.LabelFrame(mid, text="Hệ thống", style="Card.TLabelframe")
        sysg.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        for i in range(2):
            sysg.columnconfigure(i, weight=1)
        self._btn(sysg, "🤖 OpenClaw", lambda: self.call_get("/api/openclaw/status"), 0, 0)
        self._btn(sysg, "🧹 Cache", lambda: self.call_post("/api/clear_browser_cache", {}), 0, 1)
        self._btn(sysg, "🔎 Google", lambda: self.call_post("/api/google_login_auto_check", {}), 1, 0)
        self._btn(sysg, "♻ Sửa Chrome", lambda: self.call_post("/api/repair_chrome_reinstall", {}), 1, 1)

        log_card = ttk.LabelFrame(wrap, text="Realtime log", style="Card.TLabelframe")
        log_card.grid(row=3, column=0, sticky="nsew", pady=(2, 0))
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(0, weight=1)
        self.out = tk.Text(log_card, height=20, bg="#0f172a", fg="#e2e8f0", insertbackground="#e2e8f0")
        self.out.grid(row=0, column=0, sticky="nsew")

        status = ttk.Frame(wrap)
        status.grid(row=4, column=0, sticky="we", pady=(8, 0))
        ttk.Label(status, text="Trạng thái:").pack(side="left")
        ttk.Label(status, textvariable=self.status_var).pack(side="left", padx=(6, 0))

    def pick_prompt_file(self):
        init_dir = str(Path(self.prompts_var.get()).parent) if self.prompts_var.get().strip() else str(WS / "flow-auto")
        path = filedialog.askopenfilename(
            title="Chọn file text kịch bản",
            initialdir=init_dir,
            filetypes=[("Text files", "*.txt *.md"), ("All files", "*.*")],
        )
        if path:
            self.prompts_var.set(path)
            self.status_var.set("Đã chọn file kịch bản")

    def log(self, obj):
        self.out.insert("end", json.dumps(obj, ensure_ascii=False, indent=2) + "\n\n")
        self.out.see("end")

    def call_get(self, path):
        self.status_var.set(f"Đang gọi {path} ...")
        def _run():
            try:
                self.log(api_get(path))
                self.status_var.set("Sẵn sàng")
            except Exception as e:
                self.log({"ok": False, "error": str(e)})
                self.status_var.set("Có lỗi, xem log")
        threading.Thread(target=_run, daemon=True).start()

    def call_post(self, path, payload):
        self.status_var.set(f"Đang xử lý {path} ...")
        def _run():
            try:
                self.log(api_post(path, payload))
                self.status_var.set("Sẵn sàng")
            except Exception as e:
                self.log({"ok": False, "error": str(e)})
                self.status_var.set("Có lỗi, xem log")
        threading.Thread(target=_run, daemon=True).start()


def main():
    lock = acquire_single_instance_lock()
    if lock is None:
        temp = tk.Tk()
        temp.withdraw()
        messagebox.showwarning("Đã chạy", "Flow Auto đã mở sẵn. Vui lòng đóng bản cũ trước khi mở bản mới.")
        temp.destroy()
        return

    bootstrap_payload()
    root = tk.Tk()
    root.withdraw()

    ok, _ = license_check()
    if not ok:
        dlg = ActivationDialog(root)
        dlg.grab_set()
        root.wait_window(dlg)
        if not dlg.result:
            return

    # Sau kích hoạt: giao tiếp OpenClaw trước, rồi mới dựng Flow service
    gateway_ok = ensure_openclaw_gateway()
    service_ok = ensure_service_running()

    root.deiconify()
    app = App(root)

    if not service_ok:
        messagebox.showwarning(
            "Cảnh báo",
            "Kích hoạt đã thành công nhưng Flow service chưa khởi động được.\n"
            "Bạn vẫn có thể vào menu, rồi bấm 📊 Trạng thái / 🤖 OpenClaw để kiểm tra."
        )
        app.log({
            "ok": False,
            "warning": "service_not_running",
            "openclaw_gateway": gateway_ok,
            "hint": "Kích hoạt OK. Hãy kiểm tra service/OpenClaw rồi thử lại."
        })

    root.mainloop()


if __name__ == "__main__":
    main()
