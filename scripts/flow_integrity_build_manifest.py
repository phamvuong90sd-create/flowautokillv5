#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path

DEFAULT_FILES = [
    "scripts/flow_batch_runner.py",
    "scripts/flow_queue_worker.py",
    "scripts/flow_license_online_check.py",
    "scripts/flow_google_login_auto_check.py",
    "scripts/flow_chrome_repair_reinstall.sh",
    "scripts/flow-auto-service-install.sh",
]


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
    ap.add_argument("--version", default="3.2.0")
    ap.add_argument("--extra", action="append", default=[])
    args = ap.parse_args()

    ws = Path(args.workspace)
    manifest_path = ws / args.manifest
    files = DEFAULT_FILES + args.extra

    out_files = []
    for rel in files:
        p = ws / rel
        if not p.exists():
            continue
        out_files.append({
            "path": rel,
            "sha256": sha256_file(p),
            "size": p.stat().st_size,
        })

    manifest = {
        "product": "flow-auto-pro",
        "version": args.version,
        "files": out_files,
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(manifest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
