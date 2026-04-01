#!/usr/bin/env python3
import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Repack prompt txt into clean UTF-8/LF format")
    ap.add_argument("--input", required=True, help="source .txt file")
    ap.add_argument("--output", required=True, help="output .txt file")
    ap.add_argument("--min-len", type=int, default=8, help="minimum prompt length")
    args = ap.parse_args()

    src = Path(args.input)
    dst = Path(args.output)

    text = src.read_text(encoding="utf-8", errors="ignore")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    prompts = [p.strip() for p in text.split("\n\n") if p.strip()]
    prompts = [p for p in prompts if len(p) >= args.min_len]

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n\n".join(prompts) + "\n", encoding="utf-8")

    print(f"input={src}")
    print(f"output={dst}")
    print(f"prompts={len(prompts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
