#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

WS = Path('/home/davis/.openclaw/workspace')
FLOW_DIR = WS / 'flow-auto'
SCRIPTS_DIR = WS / 'scripts'
VENV_PY = WS / '.venv-flow' / 'bin' / 'python'
PID_FILE = FLOW_DIR / 'job-state' / 'bridge-runner.pid'
STATUS_FILE = FLOW_DIR / 'job-state' / 'bridge-status.json'


def _json_write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _json_read(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def ensure_cdp():
    cmd = [
        '/usr/bin/google-chrome',
        '--remote-debugging-address=127.0.0.1',
        '--remote-debugging-port=18800',
        f'--user-data-dir={Path.home() / ".config/google-chrome-flow"}',
        'https://labs.google/fx/tools/flow'
    ]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build_first_n(prompts_path: Path, n: int) -> Path:
    text = prompts_path.read_text(encoding='utf-8', errors='ignore')
    blocks = [b.strip() for b in text.split('\n\n') if b.strip()]
    out = FLOW_DIR / f'current-text-prompt-first{n}-bridge.txt'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n\n'.join(blocks[:n]) + '\n', encoding='utf-8')
    return out


def start_run(prompts_path: str, limit: int = 20, start_from: int = 1):
    src = Path(prompts_path)
    if not src.exists():
        raise FileNotFoundError(f'prompts file not found: {src}')

    ensure_cdp()

    use_file = build_first_n(src, limit) if limit > 0 else src
    state = FLOW_DIR / 'job-state' / 'bridge-runner.json'
    log = FLOW_DIR / 'debug' / 'bridge-runner.log'
    log.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(VENV_PY),
        str(SCRIPTS_DIR / 'flow_batch_runner.py'),
        '--prompts', str(use_file),
        '--state', str(state),
        '--start-from', str(start_from),
    ]
    p = subprocess.Popen(cmd, stdout=open(log, 'a'), stderr=subprocess.STDOUT, preexec_fn=os.setsid)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(p.pid), encoding='utf-8')

    _json_write(STATUS_FILE, {
        'ok': True,
        'running': True,
        'pid': p.pid,
        'prompts': str(use_file),
        'state': str(state),
        'log': str(log),
        'ts': int(time.time())
    })
    return _json_read(STATUS_FILE)


def stop_run():
    if not PID_FILE.exists():
        return {'ok': True, 'running': False, 'reason': 'no_pid'}
    pid = int(PID_FILE.read_text(encoding='utf-8').strip())
    try:
        os.killpg(pid, signal.SIGTERM)
    except Exception:
        pass
    PID_FILE.unlink(missing_ok=True)
    st = _json_read(STATUS_FILE)
    st.update({'running': False, 'stopped_at': int(time.time())})
    _json_write(STATUS_FILE, st)
    return {'ok': True, 'running': False, 'pid': pid}


def status():
    st = _json_read(STATUS_FILE)
    pid = None
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding='utf-8').strip())
        except Exception:
            pid = None
    running = bool(pid and _is_running(pid))
    st.update({'running': running, 'pid': pid})
    return st


def check_license():
    cmd = ['python3', str(SCRIPTS_DIR / 'flow_license_online_check.py'), '--check', '--json']
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or p.stderr or '').strip()
    try:
        return json.loads(out)
    except Exception:
        return {'ok': False, 'raw': out}


class H(BaseHTTPRequestHandler):
    def _send(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            return self._send(200, {'ok': True, 'service': 'flow_auto_v2', 'ts': int(time.time())})
        if path == '/api/status':
            return self._send(200, status())
        if path == '/api/license/check':
            return self._send(200, check_license())
        return self._send(404, {'ok': False, 'error': 'not_found'})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length > 0 else b'{}'
        try:
            data = json.loads(raw.decode('utf-8') or '{}')
        except Exception:
            data = {}

        if path == '/api/start':
            try:
                prompts = data.get('prompts_path') or str(FLOW_DIR / 'current-text-prompt.txt')
                limit = int(data.get('limit', 20))
                start_from = int(data.get('start_from', 1))
                return self._send(200, start_run(prompts, limit, start_from))
            except Exception as e:
                return self._send(500, {'ok': False, 'error': str(e)})

        if path == '/api/stop':
            return self._send(200, stop_run())

        return self._send(404, {'ok': False, 'error': 'not_found'})


if __name__ == '__main__':
    host = os.environ.get('FLOW_V2_HOST', '127.0.0.1')
    port = int(os.environ.get('FLOW_V2_PORT', '18777'))
    print(f'[flow_auto_v2] listening on http://{host}:{port}')
    ThreadingHTTPServer((host, port), H).serve_forever()
