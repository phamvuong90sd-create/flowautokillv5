#!/usr/bin/env python3
import argparse
import platform
import subprocess
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(Path.home() / ".openclaw/workspace/flow-auto/exports"))
    args = ap.parse_args()

    p = Path(args.path).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)

    sysname = platform.system().lower()
    if sysname == "darwin":
        subprocess.run(["open", str(p)])
    elif sysname == "windows":
        subprocess.run(["explorer", str(p)])
    else:
        subprocess.run(["xdg-open", str(p)])


if __name__ == "__main__":
    main()
