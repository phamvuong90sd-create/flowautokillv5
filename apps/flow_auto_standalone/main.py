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
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime

APP_NAME = "Flow Auto Pro Standalone"
APP_VERSION = "v3-no-openclaw"

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


def resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return (base / rel).resolve()


def env_vars() -> dict:
    e = os.environ.copy()
    e["FLOW_WORKSPACE"] = str(BASE_DIR)
    e["FLOW_INBOUND_DIR"] = str(INBOUND_DIR)
    return e


def python_bin() -> str:
    p = BASE_DIR / ".venv-flow" / "bin" / "python"
    if p.exists():
        return str(p)
    p2 = BASE_DIR / ".venv-flow" / "Scripts" / "python.exe"
    if p2.exists():
        return str(p2)
    return "python" if platform.system().lower() == "windows" else "python3"


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


def machine_id() -> str:
    verify = SCRIPTS_DIR / "bin" / "flow_license_verify"
    if verify.exists():
        c, o, _ = run_cmd([str(verify), "--machine-id"], timeout=20)
        if c == 0 and o:
            return o.strip().lower()

    if platform.system().lower() == "windows":
        ps = (
            "$x=''; "
            "try{$x=(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography' -Name MachineGuid -ErrorAction Stop).MachineGuid}catch{}; "
            "if([string]::IsNullOrWhiteSpace($x)){$x=$env:COMPUTERNAME}; $x.ToString().Trim().ToLower()"
        )
        c, o, _ = run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=20)
        if c == 0 and o:
            return o.strip().lower()

    return platform.node().lower().strip() or "unknown"


def license_check():
    checker = SCRIPTS_DIR / "flow_license_online_check.py"
    if not checker.exists():
        return False, {"ok": False, "reason": "checker_missing"}
    c, o, e = run_cmd([python_bin(), str(checker), "--check", "--json"], timeout=90)
    raw = o or e
    try:
        obj = json.loads(raw)
    except Exception:
        obj = {"ok": False, "raw": raw}
    return (c == 0 and bool(obj.get("ok", False))), obj


def activate_key(license_key: str, api_base: str):
    checker = SCRIPTS_DIR / "flow_license_online_check.py"
    if not checker.exists():
        return False, "Thiếu flow_license_online_check.py"
    mid = machine_id()
    c1, o1, e1 = run_cmd([python_bin(), str(checker), "--setup", "--api-base", api_base, "--license-key", license_key, "--machine-id", mid], timeout=120)
    if c1 != 0:
        return False, e1 or o1 or "setup failed"
    c2, o2, e2 = run_cmd([python_bin(), str(checker), "--activate", "--json"], timeout=180)
    if c2 != 0:
        return False, e2 or o2 or "activate failed"
    return True, o2 or "activated"


def _is_running(pid: int) -> bool:
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
    if PID_RUN.exists():
        try:
            pid = int(PID_RUN.read_text().strip())
        except Exception:
            pid = None
    running = bool(pid and _is_running(pid))
    return {"ok": True, "running": running, "pid": pid}


def worker_status():
    pid = None
    if PID_WORKER.exists():
        try:
            pid = int(PID_WORKER.read_text().strip())
        except Exception:
            pid = None
    running = bool(pid and _is_running(pid))
    return {"ok": True, "worker_running": running, "worker_pid": pid}


def start_run(prompts_path: str, limit: int, start_from: int):
    st = run_status()
    if st.get("running"):
        return {"ok": True, "reason": "already_running", **st}

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

    cmd = [
        python_bin(), str(SCRIPTS_DIR / "flow_batch_runner.py"),
        "--prompts", str(use_file),
        "--state", str(STATE_FILE),
        "--start-from", str(start_from),
    ]

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

    cmd = [python_bin(), str(SCRIPTS_DIR / "flow_queue_worker.py")]
    log_file = FLOW_DIR / "debug" / "standalone-worker.log"
    out = open(log_file, "a", encoding="utf-8")

    kwargs = {"stdout": out, "stderr": subprocess.STDOUT, "env": env_vars()}
    if platform.system().lower() == "windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    p = subprocess.Popen(cmd, **kwargs)
    PID_WORKER.write_text(str(p.pid), encoding="utf-8")
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
    c, o, e = run_cmd([python_bin(), str(script), *args], timeout=timeout)
    return {"ok": c == 0, "code": c, "stdout": o, "stderr": e}


class ActivationDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Kích hoạt Flow Auto Standalone")
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

        self.prompts_var = tk.StringVar(value=str(FLOW_DIR / "current-text-prompt.txt"))
        self.limit_var = tk.StringVar(value="20")
        self.start_var = tk.StringVar(value="1")
        self.input_video_dir_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.output_video_var = tk.StringVar(value="")
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

        self.root.configure(bg=bg)

        s.configure("TFrame", background=bg)
        s.configure("TLabelframe", background=panel, foreground=fg, bordercolor=panel2, relief="solid")
        s.configure("TLabelframe.Label", background=panel, foreground=fg, font=("Segoe UI", 10, "bold"))
        s.configure("TLabel", background=bg, foreground=fg)
        s.configure("TEntry", fieldbackground=panel2, foreground=fg, insertcolor=fg)
        s.configure("TButton", padding=9, background=accent, foreground="white", borderwidth=0, focusthickness=0)
        s.map("TButton", background=[("active", accent_active), ("pressed", accent_active)], foreground=[("disabled", muted)])

    def _btn(self, parent, text, cmd, r, c, cs=1):
        b = ttk.Button(parent, text=text, command=cmd)
        b.grid(row=r, column=c, columnspan=cs, sticky="nsew", padx=4, pady=4)
        return b

    def build_ui(self):
        wrap = ttk.Frame(self.root, padding=12)
        wrap.pack(fill="both", expand=True)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(3, weight=1)

        ttk.Label(wrap, text="FLOW AUTO PRO — STANDALONE (NO OPENCLAW)", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))

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
        self._btn(worker, "🧾 Worker status", self.on_worker_status, 1, 0, 2)

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

        logf = ttk.LabelFrame(wrap, text="Realtime log")
        logf.grid(row=3, column=0, sticky="nsew")
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        self.out = tk.Text(logf, height=20, bg="#0f172a", fg="#e2e8f0", insertbackground="#e2e8f0")
        self.out.grid(row=0, column=0, sticky="nsew")

        st = ttk.Frame(wrap)
        st.grid(row=4, column=0, sticky="we", pady=(8, 0))
        ttk.Label(st, text="Trạng thái:").pack(side="left")
        ttk.Label(st, textvariable=self.status_var).pack(side="left", padx=(6, 0))

    def _ui(self, fn):
        try:
            if self.root.winfo_exists():
                self.root.after(0, fn)
        except Exception:
            pass

    def _set_status(self, t):
        self._ui(lambda: self.status_var.set(t))

    def log(self, obj):
        payload = json.dumps(obj, ensure_ascii=False, indent=2) + "\n\n"
        def _append():
            if self.out.winfo_exists():
                self.out.insert("end", payload)
                self.out.see("end")
        self._ui(_append)

    def pick_prompt(self):
        init_dir = str(Path(self.prompts_var.get()).parent) if self.prompts_var.get().strip() else str(FLOW_DIR)
        p = filedialog.askopenfilename(title="Chọn file text kịch bản", initialdir=init_dir, filetypes=[("Text", "*.txt *.md"), ("All", "*.*")])
        if p:
            self.prompts_var.set(p)

    def _bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def on_start(self):
        self._set_status("Đang start...")
        def _run():
            try:
                r = start_run(self.prompts_var.get().strip(), int(self.limit_var.get() or "20"), int(self.start_var.get() or "1"))
                self.log(r)
            except Exception as e:
                self.log({"ok": False, "error": str(e)})
            self._set_status("Sẵn sàng")
        self._bg(_run)

    def on_quick(self):
        self._set_status("Đang quick start...")
        def _run():
            try:
                r = start_run(self.prompts_var.get().strip(), 10, 1)
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

    def on_worker_status(self):
        self.log(worker_status())

    def on_license_check(self):
        ok, r = license_check()
        self.log({"ok": ok, "result": r})

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
    main()
