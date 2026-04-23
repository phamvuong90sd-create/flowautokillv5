#!/usr/bin/env python3
import json
import os
import platform
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from urllib import request, error
import ssl
import uuid
import time
from datetime import datetime

APP_NAME = "Flow Auto Pro Portable v4.1"
APP_VERSION = os.environ.get("FLOW_APP_VERSION", "3.4.5")
WS = Path(os.environ.get("FLOW_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))
SCRIPTS = WS / "scripts"
APPS_CORE = WS / "apps" / "flow_auto_v2" / "core"
PYTHON = str(WS / ".venv-flow" / "bin" / "python") if (WS / ".venv-flow" / "bin" / "python").exists() else "python3"
API = "http://127.0.0.1:18777"
LICENSE_FILE = WS / "keys" / "license-online.json"


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
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if platform.system().lower() != "windows":
            kwargs["start_new_session"] = True
        subprocess.Popen([PYTHON, str(service_py)], **kwargs)

    for _ in range(20):
        try:
            with request.urlopen(API + "/health", timeout=1.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
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
    def __init__(self, master):
        super().__init__(master)
        self.title("Kích hoạt ứng dụng")
        self.geometry("560x190")
        self.resizable(False, False)
        self.result = False

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
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
        self.root.title(APP_NAME)
        self.root.geometry("990x640")
        self.prompts_var = tk.StringVar(value=str(WS / "flow-auto/current-text-prompt.txt"))
        self.limit_var = tk.StringVar(value="20")
        self.start_var = tk.StringVar(value="1")
        self.input_video_dir_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.output_video_var = tk.StringVar(value="")
        self.build_ui()
        self.log({"ok": True, "app": APP_NAME, "workspace": str(WS)})

    def build_ui(self):
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="File prompt").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.prompts_var, width=95).grid(row=0, column=1, columnspan=6, sticky="we", padx=6)

        ttk.Label(frm, text="Số prompt").grid(row=1, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.limit_var, width=10).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(frm, text="Bắt đầu từ").grid(row=1, column=2, sticky="e")
        ttk.Entry(frm, textvariable=self.start_var, width=10).grid(row=1, column=3, sticky="w", padx=6)

        ttk.Label(frm, text="Video nguồn").grid(row=2, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.input_video_dir_var, width=45).grid(row=2, column=1, columnspan=3, sticky="we", padx=6)
        ttk.Label(frm, text="File xuất (optional)").grid(row=2, column=4, sticky="e")
        ttk.Entry(frm, textvariable=self.output_video_var, width=34).grid(row=2, column=5, columnspan=2, sticky="we", padx=6)

        self.out = tk.Text(frm, height=23)
        self.out.grid(row=6, column=0, columnspan=7, sticky="nsew", pady=10)
        frm.rowconfigure(6, weight=1)
        for i in range(7):
            frm.columnconfigure(i, weight=1)

        ttk.Button(frm, text="▶ Bắt đầu", command=lambda: self.call_post("/api/start", {
            "prompts_path": self.prompts_var.get().strip(),
            "limit": int(self.limit_var.get().strip() or "20"),
            "start_from": int(self.start_var.get().strip() or "1"),
        })).grid(row=3, column=0, sticky="we")
        ttk.Button(frm, text="⏹ Dừng", command=lambda: self.call_post("/api/stop", {})).grid(row=3, column=1, sticky="we", padx=4)
        ttk.Button(frm, text="⚡ Chạy nhanh", command=lambda: self.call_post("/api/run_quick_start", {
            "prompts_path": self.prompts_var.get().strip()
        })).grid(row=3, column=2, sticky="we")
        ttk.Button(frm, text="📊 Trạng thái", command=lambda: self.call_get("/api/status")).grid(row=3, column=3, sticky="we", padx=4)
        ttk.Button(frm, text="🔐 License", command=lambda: self.call_get("/api/license/check")).grid(row=3, column=4, sticky="we")
        ttk.Button(frm, text="🤖 OpenClaw", command=lambda: self.call_get("/api/openclaw/status")).grid(row=3, column=5, sticky="we", padx=4)
        ttk.Button(frm, text="📥 Tải video xong", command=lambda: self.call_post("/api/download_all_completed", {})).grid(row=3, column=6, sticky="we")

        ttk.Button(frm, text="🎬 Hậu kỳ", command=lambda: self.call_post("/api/postprocess_videos", {
            "input_dir": self.input_video_dir_var.get().strip(),
            "output_file": self.output_video_var.get().strip(),
        })).grid(row=4, column=0, columnspan=3, sticky="we")
        ttk.Button(frm, text="📂 Mở video xuất", command=lambda: self.call_post("/api/open_exports", {
            "path": self.output_video_var.get().strip()
        })).grid(row=4, column=3, columnspan=2, sticky="we", padx=4)
        ttk.Button(frm, text="🧹 Cache", command=lambda: self.call_post("/api/clear_browser_cache", {})).grid(row=4, column=5, sticky="we")
        ttk.Button(frm, text="🔎 Google", command=lambda: self.call_post("/api/google_login_auto_check", {})).grid(row=4, column=6, sticky="we", padx=4)

    def log(self, obj):
        self.out.insert("end", json.dumps(obj, ensure_ascii=False, indent=2) + "\n\n")
        self.out.see("end")

    def call_get(self, path):
        def _run():
            try:
                self.log(api_get(path))
            except Exception as e:
                self.log({"ok": False, "error": str(e)})
        threading.Thread(target=_run, daemon=True).start()

    def call_post(self, path, payload):
        def _run():
            try:
                self.log(api_post(path, payload))
            except Exception as e:
                self.log({"ok": False, "error": str(e)})
        threading.Thread(target=_run, daemon=True).start()


def main():
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

    if not ensure_service_running():
        messagebox.showerror("Lỗi", "Không mở được Flow service (127.0.0.1:18777).")
        return

    root.deiconify()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
