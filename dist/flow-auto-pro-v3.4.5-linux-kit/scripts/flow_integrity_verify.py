#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=str(Path.home() / ".openclaw" / "workspace"))
    ap.add_argument("--manifest", default="keys/flow-integrity-manifest.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ws = Path(args.workspace)
    manifest_path = ws / args.manifest

    if not manifest_path.exists():
        out = {"ok": False, "reason": "missing_manifest", "path": str(manifest_path)}
        print(json.dumps(out, ensure_ascii=False) if args.json else f"ok=False reason=missing_manifest")
        return 12

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        out = {"ok": False, "reason": "bad_manifest_json"}
        print(json.dumps(out, ensure_ascii=False) if args.json else "ok=False reason=bad_manifest_json")
        return 12

    mismatches = []
    missing = []

    for it in manifest.get("files", []):
        rel = it.get("path", "")
        expected = (it.get("sha256") or "").lower()
        if not rel or not expected:
            continue
        p = ws / rel
        if not p.exists():
            missing.append(rel)
            continue
        actual = sha256_file(p).lower()
        if actual != expected:
            mismatches.append({"path": rel, "expected": expected, "actual": actual})

    ok = (not missing) and (not mismatches)
    out = {
        "ok": ok,
        "missing": missing,
        "mismatches": mismatches,
        "checked": len(manifest.get("files", [])),
        "version": manifest.get("version"),
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        if ok:
            print("ok=True reason=integrity_ok")
        else:
            print("ok=False reason=integrity_failed")

    return 0 if ok else 12


if __name__ == "__main__":
    sys.exit(main())
