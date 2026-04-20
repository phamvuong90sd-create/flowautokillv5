#!/usr/bin/env python3
import json
import os
import platform
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from urllib import request, error

APP_NAME = "Flow Auto Pro Portable"
WS = Path(os.environ.get("FLOW_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))
SCRIPTS = WS / "scripts"
SERVICE_PY = WS / "apps" / "flow_auto_v2" / "core" / "service.py"
PYTHON = str(WS / ".venv-flow" / "bin" / "python") if (WS / ".venv-flow" / "bin" / "python").exists() else "python3"
API = "http://127.0.0.1:18777"
LICENSE_FILE = WS / "keys" / "license-online.json"


def run_cmd(cmd, timeout=180):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def ensure_service_running():
    try:
        with request.urlopen(API + "/health", timeout=1.5) as r:
            if r.status == 200:
                return True
    except Exception:
        pass

    if SERVICE_PY.exists():
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if platform.system().lower() != "windows":
            kwargs["start_new_session"] = True
        subprocess.Popen([PYTHON, str(SERVICE_PY)], **kwargs)

    for _ in range(15):
        try:
            with request.urlopen(API + "/health", timeout=1.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
    return False


def api_get(path):
    with request.urlopen(API + path, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def api_post(path, data):
    body = json.dumps(data).encode("utf-8")
    req = request.Request(API + path, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def license_check():
    script = SCRIPTS / "flow_license_online_check.py"
    if script.exists():
        code, out, err = run_cmd([PYTHON, str(script), "--check", "--json"], timeout=60)
        raw = out or err
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                if obj.get("ok") is True:
                    return True, obj
                if obj.get("data", {}).get("valid") is True:
                    return True, obj
            return False, obj
        except Exception:
            return False, {"ok": False, "raw": raw}
    return LICENSE_FILE.exists(), {"ok": LICENSE_FILE.exists()}


def machine_id():
    script_bin = SCRIPTS / "bin" / "flow_license_verify"
    if script_bin.exists() and os.access(script_bin, os.X_OK):
        code, out, _ = run_cmd([str(script_bin), "--machine-id"], timeout=20)
        if code == 0 and out.strip():
            return out.strip()
    return platform.node().lower().strip() or "unknown"


def activate_with_key(key: str):
    script = SCRIPTS / "flow_license_online_check.py"
    if not script.exists():
        return False, "Thiếu script flow_license_online_check.py"

    mid = machine_id()
    api_base = os.environ.get("PRESET_LICENSE_API_BASE", "https://server-auto-tool.vercel.app/api/license")
    c1, o1, e1 = run_cmd([PYTHON, str(script), "--setup", "--api-base", api_base, "--license-key", key, "--machine-id", mid], timeout=60)
    if c1 != 0:
        return False, e1 or o1 or "setup failed"
    c2, o2, e2 = run_cmd([PYTHON, str(script), "--activate"], timeout=90)
    if c2 != 0:
        return False, e2 or o2 or "activate failed"
    return True, o2 or "activated"


class ActivationDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Kích hoạt ứng dụng")
        self.geometry("520x180")
        self.resizable(False, False)
        self.result = False

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Nhập LICENSE_KEY để kích hoạt online:").pack(anchor="w")
        self.key_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.key_var, width=70).pack(fill="x", pady=8)

        self.status = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.status, foreground="#cc5500").pack(anchor="w", pady=2)

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=10)
        ttk.Button(btns, text="Kích hoạt", command=self.do_activate).pack(side="left")
        ttk.Button(btns, text="Thoát", command=self.destroy).pack(side="right")

    def do_activate(self):
        key = self.key_var.get().strip()
        if not key:
            self.status.set("LICENSE_KEY không được trống")
            return
        ok, msg = activate_with_key(key)
        if ok:
            self.result = True
            messagebox.showinfo("Thành công", "Kích hoạt thành công")
            self.destroy()
        else:
            self.status.set(str(msg)[:180])


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("980x620")

        self.prompts_var = tk.StringVar(value=str(WS / "flow-auto/current-text-prompt.txt"))
        self.limit_var = tk.StringVar(value="20")
        self.start_var = tk.StringVar(value="1")

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

        self.out = tk.Text(frm, height=24)
        self.out.grid(row=3, column=0, columnspan=7, sticky="nsew", pady=10)
        frm.rowconfigure(3, weight=1)
        for i in range(7):
            frm.columnconfigure(i, weight=1)

        ttk.Button(frm, text="▶ Bắt đầu", command=lambda: self.call_post("/api/start", {
            "prompts_path": self.prompts_var.get().strip(),
            "limit": int(self.limit_var.get().strip() or "20"),
            "start_from": int(self.start_var.get().strip() or "1"),
        })).grid(row=2, column=0, sticky="we")
        ttk.Button(frm, text="⏹ Dừng", command=lambda: self.call_post("/api/stop", {})).grid(row=2, column=1, sticky="we", padx=4)
        ttk.Button(frm, text="⚡ Chạy nhanh", command=lambda: self.call_post("/api/run_quick_start", {
            "prompts_path": self.prompts_var.get().strip()
        })).grid(row=2, column=2, sticky="we")
        ttk.Button(frm, text="📊 Trạng thái", command=lambda: self.call_get("/api/status")).grid(row=2, column=3, sticky="we", padx=4)
        ttk.Button(frm, text="🔐 License", command=lambda: self.call_get("/api/license/check")).grid(row=2, column=4, sticky="we")
        ttk.Button(frm, text="🤖 OpenClaw", command=lambda: self.call_get("/api/openclaw/status")).grid(row=2, column=5, sticky="we", padx=4)
        ttk.Button(frm, text="🧹 Cache", command=lambda: self.call_post("/api/clear_browser_cache", {})).grid(row=2, column=6, sticky="we")

        ttk.Button(frm, text="🔎 Google login", command=lambda: self.call_post("/api/google_login_auto_check", {})).grid(row=4, column=0, columnspan=2, sticky="we")
        ttk.Button(frm, text="📥 Tải video xong", command=lambda: self.call_post("/api/download_all_completed", {})).grid(row=4, column=2, columnspan=2, sticky="we", padx=4)
        ttk.Button(frm, text="♻ Sửa Chrome", command=lambda: self.call_post("/api/repair_chrome_reinstall", {})).grid(row=4, column=4, columnspan=2, sticky="we")

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
