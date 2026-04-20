#!/usr/bin/env python3
import json
import tkinter as tk
from tkinter import ttk, messagebox
from urllib import request, error

BASE = "http://127.0.0.1:18777"
DEFAULT_PROMPTS = str((__import__('pathlib').Path.home() / '.openclaw/workspace/flow-auto/current-text-prompt.txt'))


def api_get(path):
    with request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def api_post(path, data):
    body = json.dumps(data).encode("utf-8")
    req = request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except error.URLError:
        messagebox.showerror("Lỗi kết nối", "Không kết nối được Flow Auto Service (127.0.0.1:18777).\nHãy chạy server mode trước.")
        return {"ok": False, "error": "service_unreachable"}
    except Exception as e:
        messagebox.showerror("Lỗi", str(e))
        return {"ok": False, "error": str(e)}


root = tk.Tk()
root.title("Flow Auto Pro GUI (Việt hóa)")
root.geometry("980x620")

frm = ttk.Frame(root, padding=12)
frm.pack(fill="both", expand=True)

prompts_var = tk.StringVar(value=DEFAULT_PROMPTS)
limit_var = tk.StringVar(value="20")
start_from_var = tk.StringVar(value="1")
author_code_var = tk.StringVar(value="")

# Row 0
ttk.Label(frm, text="Đường dẫn file prompt").grid(row=0, column=0, sticky="w")
ttk.Entry(frm, textvariable=prompts_var, width=95).grid(row=0, column=1, columnspan=6, sticky="we", padx=6)

# Row 1
ttk.Label(frm, text="Số prompt chạy").grid(row=1, column=0, sticky="w")
ttk.Entry(frm, textvariable=limit_var, width=10).grid(row=1, column=1, sticky="w", padx=6)
ttk.Label(frm, text="Bắt đầu từ").grid(row=1, column=2, sticky="e")
ttk.Entry(frm, textvariable=start_from_var, width=10).grid(row=1, column=3, sticky="w", padx=6)

ttk.Label(frm, text="Mã kích hoạt (optional)").grid(row=1, column=4, sticky="e")
ttk.Entry(frm, textvariable=author_code_var, width=34).grid(row=1, column=5, columnspan=2, sticky="we", padx=6)

out = tk.Text(frm, height=24)
out.grid(row=3, column=0, columnspan=7, sticky="nsew", pady=10)
frm.rowconfigure(3, weight=1)
for i in range(7):
    frm.columnconfigure(i, weight=1)


def log(obj):
    out.insert("end", json.dumps(obj, ensure_ascii=False, indent=2) + "\n\n")
    out.see("end")


def on_activate():
    code = author_code_var.get().strip()
    log(safe_call(api_post, "/api/activate", {"author_code": code}))


def on_start():
    payload = {
        "prompts_path": prompts_var.get().strip(),
        "limit": int(limit_var.get().strip() or "20"),
        "start_from": int(start_from_var.get().strip() or "1"),
    }
    log(safe_call(api_post, "/api/start", payload))


def on_quick_start():
    log(safe_call(api_post, "/api/run_quick_start", {"prompts_path": prompts_var.get().strip()}))


def on_stop():
    log(safe_call(api_post, "/api/stop", {}))


def on_status():
    log(safe_call(api_get, "/api/status"))


def on_license():
    log(safe_call(api_get, "/api/license/check"))


def on_openclaw_status():
    log(safe_call(api_get, "/api/openclaw/status"))


def on_cache_clear():
    log(safe_call(api_post, "/api/clear_browser_cache", {}))


def on_google_check():
    log(safe_call(api_post, "/api/google_login_auto_check", {}))


def on_download_done():
    log(safe_call(api_post, "/api/download_all_completed", {}))


def on_repair_chrome():
    log(safe_call(api_post, "/api/repair_chrome_reinstall", {}))


# Controls
ttk.Button(frm, text="🔐 Kích hoạt ứng dụng", command=on_activate).grid(row=2, column=0, sticky="we")
ttk.Button(frm, text="⚡ Chạy nhanh", command=on_quick_start).grid(row=2, column=1, sticky="we", padx=4)
ttk.Button(frm, text="▶ Bắt đầu", command=on_start).grid(row=2, column=2, sticky="we")
ttk.Button(frm, text="⏹ Dừng", command=on_stop).grid(row=2, column=3, sticky="we", padx=4)
ttk.Button(frm, text="📊 Trạng thái", command=on_status).grid(row=2, column=4, sticky="we")
ttk.Button(frm, text="🔐 Kiểm tra license", command=on_license).grid(row=2, column=5, sticky="we", padx=4)
ttk.Button(frm, text="🤖 Trạng thái OpenClaw", command=on_openclaw_status).grid(row=2, column=6, sticky="we")

ttk.Button(frm, text="🧹 Xóa cache trình duyệt", command=on_cache_clear).grid(row=4, column=0, columnspan=2, sticky="we")
ttk.Button(frm, text="🔎 Kiểm tra đăng nhập Google", command=on_google_check).grid(row=4, column=2, columnspan=2, sticky="we", padx=4)
ttk.Button(frm, text="📥 Tải video đã xong", command=on_download_done).grid(row=4, column=4, columnspan=2, sticky="we")
ttk.Button(frm, text="♻ Sửa Chrome", command=on_repair_chrome).grid(row=4, column=6, sticky="we", padx=4)

root.mainloop()
