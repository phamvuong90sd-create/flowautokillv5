#!/usr/bin/env python3
import argparse
import base64
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
WORKSPACE = Path(os.environ.get("FLOW_WORKSPACE", str(HOME / ".openclaw" / "workspace")))
LICENSE_FILE = Path(os.environ.get("FLOW_LICENSE_FILE", str(WORKSPACE / "license.json")))
PUBLIC_KEY = Path(os.environ.get("FLOW_AUTHOR_PUBLIC_KEY", str(WORKSPACE / "scripts" / "flow_author_public.pem")))
PRODUCT = os.environ.get("FLOW_PRODUCT", "flow-auto")
ENFORCE = os.environ.get("FLOW_LICENSE_ENFORCE", "0") == "1"
GRACE_DAYS = int(os.environ.get("FLOW_LICENSE_GRACE_DAYS", "3"))
AUTHOR_CODE = os.environ.get("FLOW_AUTHOR_CODE", "").strip()


def now_utc():
    return datetime.now(timezone.utc)


def parse_iso(s: str):
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def read_machine_id() -> str:
    p = Path("/etc/machine-id")
    if p.exists():
        try:
            return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return socket.gethostname()


def b64u_decode(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


def b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")


def load_cached() -> dict:
    if not LICENSE_FILE.exists():
        return {}
    try:
        return json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cached(data: dict):
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def verify_sig(payload_b64: str, sig_b64: str) -> bool:
    if not PUBLIC_KEY.exists():
        return False
    try:
        payload = payload_b64.encode("utf-8")
        sig = b64u_decode(sig_b64)
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f_payload:
            f_payload.write(payload)
            payload_path = f_payload.name
        with tempfile.NamedTemporaryFile(delete=False) as f_sig:
            f_sig.write(sig)
            sig_path = f_sig.name

        cmd = [
            "openssl", "dgst", "-sha256", "-verify", str(PUBLIC_KEY), "-signature", sig_path, payload_path
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode == 0 and "Verified OK" in (proc.stdout + proc.stderr)
    except Exception:
        return False


def validate_code(code: str):
    if not code:
        return False, "no_author_code", {}
    parts = code.split(".")
    if len(parts) != 2:
        return False, "bad_format", {}
    payload_b64, sig_b64 = parts

    if not verify_sig(payload_b64, sig_b64):
        return False, "bad_signature", {}

    try:
        payload = json.loads(b64u_decode(payload_b64).decode("utf-8"))
    except Exception:
        return False, "bad_payload", {}

    if payload.get("product") != PRODUCT:
        return False, "product_mismatch", {}

    mid = payload.get("machine_id", "")
    if mid and mid != read_machine_id():
        return False, "machine_mismatch", {}

    exp = payload.get("expires_at", "")
    if not exp:
        return False, "missing_expiry", {}
    try:
        exp_dt = parse_iso(exp)
    except Exception:
        return False, "bad_expiry", {}

    grace = int(payload.get("grace_days", GRACE_DAYS))
    if now_utc() > (exp_dt + timedelta(days=grace)):
        return False, "expired", {}

    cache = {
        "valid": True,
        "mode": "author-rsa",
        "product": PRODUCT,
        "machine_id": read_machine_id(),
        "expires_at": exp,
        "grace_days": grace,
        "plan": payload.get("plan", "monthly"),
        "last_verified_at": now_utc().isoformat(),
        "author_code": code,
    }
    save_cached(cache)
    return True, "ok", cache


def check_cached():
    c = load_cached()
    if not c:
        return False, "no_cached", {}
    exp = c.get("expires_at", "")
    if not exp:
        return False, "bad_cached", c
    try:
        exp_dt = parse_iso(exp)
        grace = int(c.get("grace_days", GRACE_DAYS))
        if now_utc() > (exp_dt + timedelta(days=grace)):
            return False, "cached_expired", c
    except Exception:
        return False, "bad_cached", c
    return True, "ok_cached", c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine-id", action="store_true")
    ap.add_argument("--activate", type=str, default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.machine_id:
        print(read_machine_id())
        return

    if args.activate:
        c = load_cached()
        c["author_code"] = args.activate.strip()
        save_cached(c)
        print("ok=1 activated=1")
        return

    if not ENFORCE:
        out = {"ok": True, "reason": "enforce_off"}
        print(json.dumps(out, ensure_ascii=False) if args.json else "ok=True reason=enforce_off")
        return

    code = AUTHOR_CODE or load_cached().get("author_code", "")
    ok, reason, data = validate_code(code)
    if not ok:
        c_ok, c_reason, c_data = check_cached()
        if c_ok:
            ok, reason, data = True, f"fallback_{c_reason}", c_data

    out = {"ok": ok, "reason": reason, "mode": "author-rsa", "license_file": str(LICENSE_FILE)}
    if data:
        out["data"] = data

    print(json.dumps(out, ensure_ascii=False) if args.json else f"ok={ok} reason={reason}")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
