#!/usr/bin/env python3
import argparse
import json
import os
import socket
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error, request

HOME = Path.home()
WORKSPACE = Path(os.environ.get("FLOW_WORKSPACE", str(HOME / ".openclaw" / "workspace")))
CONFIG_FILE = Path(os.environ.get("FLOW_LICENSE_ONLINE_CONFIG", str(WORKSPACE / "keys" / "license-online.json")))
APP_VERSION = os.environ.get("FLOW_APP_VERSION", "3.2.0")
TIMEOUT_SEC = int(os.environ.get("FLOW_LICENSE_TIMEOUT_SEC", "10"))
DEFAULT_GRACE_DAYS = int(os.environ.get("FLOW_LICENSE_GRACE_DAYS", "5"))
STRICT_ONLINE = os.environ.get("FLOW_LICENSE_STRICT_ONLINE", "1").strip() == "1"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    # Server expects strict UTC Z format
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    s = (s or "").strip()
    if not s:
        raise ValueError("empty timestamp")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def read_machine_id() -> str:
    # Linux
    p = Path("/etc/machine-id")
    if p.exists():
        try:
            return p.read_text(encoding="utf-8").strip().lower()
        except Exception:
            pass

    # Windows fallback: MachineGuid
    if os.name == "nt":
        try:
            import winreg  # type: ignore

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            val, _ = winreg.QueryValueEx(key, "MachineGuid")
            if val:
                return str(val).strip().lower()
        except Exception:
            pass

    return socket.gethostname().strip().lower()


def load_cfg() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cfg(cfg: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_base(base: str) -> str:
    b = (base or "").strip().rstrip("/")
    if not b:
        return b
    if b.endswith("/activate") or b.endswith("/verify"):
        b = b.rsplit("/", 1)[0]
    return b


def post_json(url: str, payload: dict, timeout: int = TIMEOUT_SEC) -> tuple[int, dict]:
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {"raw": body}
            return resp.getcode(), data
    except error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            data = json.loads(body) if body else {}
        except Exception:
            data = {"reason": f"http_{e.code}"}
        return e.code, data


def build_payload(cfg: dict, include_token: bool = False) -> dict:
    payload = {
        "license_key": cfg.get("license_key", "").strip(),
        "machine_id": cfg.get("machine_id", read_machine_id()),
        "app_version": APP_VERSION,
        "nonce": uuid.uuid4().hex,
        "timestamp": iso_now(),
    }
    if include_token:
        token = cfg.get("signed_token", "")
        if token:
            payload["signed_token"] = token
    return payload


def update_from_response(cfg: dict, data: dict) -> None:
    if isinstance(data, dict):
        for k in ("signed_token", "expires_at", "grace_until", "next_check_at"):
            v = data.get(k)
            if v:
                cfg[k] = v
    cfg["last_verified_at"] = iso_now()


def cache_still_valid(cfg: dict) -> tuple[bool, str]:
    grace_until = cfg.get("grace_until", "")
    expires_at = cfg.get("expires_at", "")
    grace_days = int(cfg.get("grace_days", DEFAULT_GRACE_DAYS))

    try:
        if grace_until:
            return (now_utc() <= parse_iso(grace_until), "cache_grace_until")
        if expires_at:
            exp = parse_iso(expires_at) + timedelta(days=grace_days)
            return (now_utc() <= exp, "cache_exp_plus_grace")
    except Exception:
        return (False, "cache_bad_time")

    return (False, "cache_missing_time")


def activate(cfg: dict) -> tuple[bool, str, dict]:
    base = normalize_base(cfg.get("api_base", ""))
    if not base:
        return False, "missing_api_base", {}
    if not cfg.get("license_key"):
        return False, "missing_license_key", {}

    cfg["machine_id"] = cfg.get("machine_id") or read_machine_id()
    payload = build_payload(cfg, include_token=False)
    code, data = post_json(f"{base}/activate", payload)
    if code == 200 and bool(data.get("valid", True)):
        update_from_response(cfg, data)
        cfg.setdefault("grace_days", DEFAULT_GRACE_DAYS)
        save_cfg(cfg)
        return True, "ok", data
    reason = data.get("reason") if isinstance(data, dict) else f"http_{code}"
    return False, str(reason or f"http_{code}"), data


def verify(cfg: dict) -> tuple[bool, str, dict]:
    base = normalize_base(cfg.get("api_base", ""))
    if not base:
        return False, "missing_api_base", {}
    if not cfg.get("license_key"):
        return False, "missing_license_key", {}

    cfg["machine_id"] = cfg.get("machine_id") or read_machine_id()
    payload = build_payload(cfg, include_token=True)

    try:
        code, data = post_json(f"{base}/verify", payload)
    except Exception as e:
        if STRICT_ONLINE:
            return False, f"network_error_strict:{e}", {}
        ok, why = cache_still_valid(cfg)
        if ok:
            return True, f"fallback_{why}:{e}", cfg
        return False, f"network_error:{e}", {}

    if code == 200 and bool(data.get("valid", False)):
        update_from_response(cfg, data)
        save_cfg(cfg)
        return True, "ok", data

    reason = data.get("reason") if isinstance(data, dict) else f"http_{code}"
    if str(reason) in {"revoked", "machine_mismatch", "invalid", "expired"}:
        return False, str(reason), data

    if STRICT_ONLINE:
        return False, str(reason or f"http_{code}"), data

    ok, why = cache_still_valid(cfg)
    if ok:
        return True, f"fallback_{why}:{reason}", cfg
    return False, str(reason or f"http_{code}"), data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--activate", action="store_true", help="activate once using configured API/key")
    ap.add_argument("--check", action="store_true", help="verify license (default)")
    ap.add_argument("--setup", action="store_true", help="write/overwrite config values")
    ap.add_argument("--api-base", default="", help="base url like https://xxx.vercel.app/api/license")
    ap.add_argument("--license-key", default="", help="customer license key")
    ap.add_argument("--machine-id", default="", help="override machine id")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = load_cfg()

    if args.setup:
        if args.api_base:
            cfg["api_base"] = normalize_base(args.api_base)
        if args.license_key:
            cfg["license_key"] = args.license_key.strip()
        if args.machine_id:
            cfg["machine_id"] = args.machine_id.strip()
        cfg.setdefault("grace_days", DEFAULT_GRACE_DAYS)
        save_cfg(cfg)

    # setup-only mode: just save config and exit success
    if args.setup and not args.activate and not args.check:
        out = {
            "ok": True,
            "reason": "setup_saved",
            "config": {
                "api_base": cfg.get("api_base", ""),
                "machine_id": cfg.get("machine_id", ""),
                "license_key_tail": (cfg.get("license_key", "")[-6:] if cfg.get("license_key") else ""),
            },
            "data": {},
        }
        if args.json:
            print(json.dumps(out, ensure_ascii=False))
        else:
            print("ok=True reason=setup_saved")
        return 0

    action_activate = args.activate
    if not args.activate and not args.check and not args.setup:
        # default action for worker checks
        action_activate = False

    if action_activate:
        ok, reason, data = activate(cfg)
    else:
        ok, reason, data = verify(cfg)

    out = {
        "ok": ok,
        "reason": reason,
        "config": {
            "api_base": cfg.get("api_base", ""),
            "machine_id": cfg.get("machine_id", ""),
            "license_key_tail": (cfg.get("license_key", "")[-6:] if cfg.get("license_key") else ""),
        },
        "data": data,
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"ok={ok} reason={reason}")

    return 0 if ok else 12


if __name__ == "__main__":
    sys.exit(main())
