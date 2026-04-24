#!/usr/bin/env python3
import argparse
import base64
import hashlib
import hmac
import json
import os
import socket
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request, error

HOME = Path.home()
WORKSPACE = Path(os.environ.get("FLOW_WORKSPACE", str(HOME / ".openclaw" / "workspace")))
LICENSE_FILE = Path(os.environ.get("FLOW_LICENSE_FILE", str(WORKSPACE / "license.json")))
PRODUCT = os.environ.get("FLOW_PRODUCT", "flow-auto")
ENFORCE = os.environ.get("FLOW_LICENSE_ENFORCE", "0").strip() == "1"
GRACE_DAYS = int(os.environ.get("FLOW_LICENSE_GRACE_DAYS", "3"))
MODE = os.environ.get("FLOW_LICENSE_MODE", "author").strip().lower()  # author|server

# server mode
LICENSE_SERVER = os.environ.get("FLOW_LICENSE_SERVER", "").strip()
LICENSE_KEY = os.environ.get("FLOW_LICENSE_KEY", "").strip()
VERIFY_TIMEOUT_SEC = int(os.environ.get("FLOW_LICENSE_TIMEOUT_SEC", "8"))

# author mode (simple offline author-code)
DEFAULT_AUTHOR_SECRET = "FLOWAUTO_AUTHOR_V1_CHANGE_ME"
AUTHOR_SECRET = os.environ.get("FLOW_AUTHOR_SECRET", "").strip() or DEFAULT_AUTHOR_SECRET
AUTHOR_CODE = os.environ.get("FLOW_AUTHOR_CODE", "").strip()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def read_machine_id() -> str:
    p = Path("/etc/machine-id")
    if p.exists():
        try:
            return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return socket.gethostname()


def parse_iso(s: str) -> datetime:
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


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


def is_expired(expires_at: str, grace_days: int) -> bool:
    exp = parse_iso(expires_at)
    return now_utc() > (exp + timedelta(days=grace_days))


def b64u_decode(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


def b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")


def verify_author_code(code: str, secret: str) -> tuple[bool, str, dict]:
    if not code:
        return False, "no_author_code", {}
    if not secret:
        return False, "no_author_secret", {}

    parts = code.split(".")
    if len(parts) != 2:
        return False, "bad_code_format", {}

    payload_b64, sig_hex = parts
    try:
        payload_raw = b64u_decode(payload_b64)
        payload = json.loads(payload_raw.decode("utf-8"))
    except Exception:
        return False, "bad_payload", {}

    calc = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, sig_hex):
        return False, "bad_signature", {}

    if payload.get("product") != PRODUCT:
        return False, "product_mismatch", {}

    machine = payload.get("machine_id", "")
    if machine and machine != read_machine_id():
        return False, "machine_mismatch", {}

    expires_at = payload.get("expires_at", "")
    if not expires_at:
        return False, "missing_expires_at", {}

    try:
        _ = parse_iso(expires_at)
    except Exception:
        return False, "bad_expires_at", {}

    grace_days = int(payload.get("grace_days", GRACE_DAYS))
    if is_expired(expires_at, grace_days):
        return False, "expired", {}

    cache = {
        "valid": True,
        "mode": "author",
        "product": PRODUCT,
        "machine_id": read_machine_id(),
        "expires_at": expires_at,
        "plan": payload.get("plan", "monthly"),
        "grace_days": grace_days,
        "last_verified_at": now_utc().isoformat(),
        "author_code_tail": code[-10:],
        "source": "author",
    }
    save_cached(cache)
    return True, "ok", cache


def verify_remote_server() -> tuple[bool, str, dict]:
    if not LICENSE_SERVER:
        return False, "no_license_server", {}
    if not LICENSE_KEY:
        return False, "no_license_key", {}

    payload = {
        "product": PRODUCT,
        "key": LICENSE_KEY,
        "machine_id": read_machine_id(),
        "ts": int(time.time()),
    }

    req = request.Request(
        LICENSE_SERVER,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=VERIFY_TIMEOUT_SEC) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
    except error.HTTPError as e:
        return False, f"http_{e.code}", {}
    except Exception as e:
        return False, f"network_error:{e}", {}

    valid = bool(data.get("valid", False))
    expires_at = data.get("expires_at", "")
    if not valid:
        return False, data.get("reason", "invalid"), data
    if not expires_at:
        return False, "missing_expires_at", data

    try:
        _ = parse_iso(expires_at)
    except Exception:
        return False, "bad_expires_at", data

    cache = {
        "valid": True,
        "mode": "server",
        "product": PRODUCT,
        "key_tail": LICENSE_KEY[-6:] if len(LICENSE_KEY) >= 6 else LICENSE_KEY,
        "machine_id": read_machine_id(),
        "expires_at": expires_at,
        "grace_days": int(data.get("grace_days", GRACE_DAYS)),
        "last_verified_at": now_utc().isoformat(),
        "source": "server",
    }
    save_cached(cache)
    return True, "ok", cache


def check_cached() -> tuple[bool, str, dict]:
    c = load_cached()
    if not c:
        return False, "no_cached_license", {}
    expires_at = c.get("expires_at", "")
    if not expires_at:
        return False, "cached_missing_expires_at", c
    grace = int(c.get("grace_days", GRACE_DAYS))
    try:
        expired = is_expired(expires_at, grace)
    except Exception:
        return False, "cached_bad_expires_at", c
    if expired:
        return False, "cached_expired", c
    return True, "ok_cached", c


def license_check() -> tuple[bool, str, dict]:
    if not ENFORCE:
        return True, "enforce_off", {}

    if MODE == "author":
        code = AUTHOR_CODE
        if not code:
            c = load_cached()
            code = c.get("author_code", "")
        ok, reason, data = verify_author_code(code, AUTHOR_SECRET)
        if ok:
            c = load_cached()
            c["author_code"] = code
            save_cached(c)
            return True, reason, data
        c_ok, c_reason, c_data = check_cached()
        if c_ok:
            return True, f"fallback_{c_reason}", c_data
        return False, f"{reason}|{c_reason}", {}

    # MODE == server
    ok, reason, data = verify_remote_server()
    if ok:
        return True, reason, data
    c_ok, c_reason, c_data = check_cached()
    if c_ok:
        return True, f"fallback_{c_reason}", c_data
    return False, f"{reason}|{c_reason}", {}


def make_author_code(secret: str, expires_at: str, machine_id: str, plan: str) -> str:
    payload = {
        "product": PRODUCT,
        "machine_id": machine_id,
        "expires_at": expires_at,
        "plan": plan,
        "issued_at": now_utc().isoformat(),
        "grace_days": GRACE_DAYS,
    }
    payload_b64 = b64u_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="print JSON result")
    ap.add_argument("--machine-id", action="store_true", help="print local machine id")
    ap.add_argument("--activate", type=str, default="", help="store author code to license file")
    ap.add_argument("--gen-author", action="store_true", help="generate author code")
    ap.add_argument("--expires-at", type=str, default="", help="ISO datetime for --gen-author")
    ap.add_argument("--plan", type=str, default="monthly", help="plan for --gen-author")
    ap.add_argument("--for-machine", type=str, default="", help="machine id for --gen-author")
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

    if args.gen_author:
        if not AUTHOR_SECRET:
            print("missing FLOW_AUTHOR_SECRET", file=sys.stderr)
            sys.exit(2)
        if not args.expires_at:
            print("missing --expires-at", file=sys.stderr)
            sys.exit(2)
        machine = args.for_machine.strip() or read_machine_id()
        code = make_author_code(AUTHOR_SECRET, args.expires_at.strip(), machine, args.plan.strip())
        print(code)
        return

    ok, reason, data = license_check()
    out = {
        "ok": ok,
        "reason": reason,
        "mode": MODE,
        "enforce": ENFORCE,
        "license_file": str(LICENSE_FILE),
    }
    if data:
        out["data"] = data

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"ok={ok} reason={reason} mode={MODE}")

    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
