#!/usr/bin/env python3
import json
import tkinter as tk
from tkinter import ttk
from urllib import request

BASE = 'http://127.0.0.1:18777'


def api_get(path):
    with request.urlopen(BASE + path, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))


def api_post(path, data):
    body = json.dumps(data).encode('utf-8')
    req = request.Request(BASE + path, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


root = tk.Tk()
root.title('Flow Auto v2 - Desktop Mode')
root.geometry('760x460')

frm = ttk.Frame(root, padding=12)
frm.pack(fill='both', expand=True)

prompts_var = tk.StringVar(value='/home/davis/.openclaw/workspace/flow-auto/current-text-prompt.txt')
limit_var = tk.StringVar(value='20')


ttk.Label(frm, text='Prompts path').grid(row=0, column=0, sticky='w')
ttk.Entry(frm, textvariable=prompts_var, width=80).grid(row=0, column=1, columnspan=4, sticky='we', padx=6)

ttk.Label(frm, text='Limit').grid(row=1, column=0, sticky='w')
ttk.Entry(frm, textvariable=limit_var, width=12).grid(row=1, column=1, sticky='w', padx=6)

out = tk.Text(frm, height=18)
out.grid(row=3, column=0, columnspan=5, sticky='nsew', pady=10)
frm.rowconfigure(3, weight=1)
frm.columnconfigure(4, weight=1)


def log(obj):
    out.insert('end', json.dumps(obj, ensure_ascii=False, indent=2) + '\n\n')
    out.see('end')


def on_start():
    log(api_post('/api/start', {'prompts_path': prompts_var.get().strip(), 'limit': int(limit_var.get().strip() or '20')}))


def on_stop():
    log(api_post('/api/stop', {}))


def on_status():
    log(api_get('/api/status'))


def on_license():
    log(api_get('/api/license/check'))


ttk.Button(frm, text='▶ Start', command=on_start).grid(row=2, column=0, sticky='w')
ttk.Button(frm, text='⏹ Stop', command=on_stop).grid(row=2, column=1, sticky='w', padx=6)
ttk.Button(frm, text='📊 Status', command=on_status).grid(row=2, column=2, sticky='w')
ttk.Button(frm, text='🔐 License', command=on_license).grid(row=2, column=3, sticky='w', padx=6)

root.mainloop()
