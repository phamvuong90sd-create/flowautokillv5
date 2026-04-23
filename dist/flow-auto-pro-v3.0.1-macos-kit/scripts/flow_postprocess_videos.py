#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def ensure_ffmpeg():
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True
    return False


def list_videos(input_dir: Path, recent_hours: int):
    now = time.time()
    max_age = recent_hours * 3600
    vids = []
    for p in sorted(input_dir.glob("*.mp4")):
        try:
            age = now - p.stat().st_mtime
            if age <= max_age:
                vids.append(p)
        except Exception:
            pass
    return vids


def duration_sec(video: Path):
    code, out, _ = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video)
    ])
    if code != 0:
        return 0.0
    try:
        return float(out.strip())
    except Exception:
        return 0.0


def trim_clip(src: Path, dst: Path, trim_start: float, trim_end: float):
    d = duration_sec(src)
    if d <= 0:
        return False, f"duration=0 {src.name}"

    keep = d - trim_start - trim_end
    if keep <= 0.1:
        return False, f"clip too short after trim: {src.name}"

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{trim_start}", "-i", str(src),
        "-t", f"{keep}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        str(dst)
    ]
    code, out, err = run(cmd)
    if code != 0:
        return False, err or out or f"trim fail: {src.name}"
    return True, "ok"


def concat_clips(clips, output_file: Path):
    list_file = output_file.parent / f"concat_{int(time.time())}.txt"
    list_file.write_text("\n".join([f"file '{c.as_posix()}'" for c in clips]) + "\n", encoding="utf-8")

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        str(output_file)
    ]
    code, out, err = run(cmd)
    try:
        list_file.unlink(missing_ok=True)
    except Exception:
        pass
    if code != 0:
        return False, err or out or "concat failed"
    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", default=str(Path.home() / "Downloads"))
    ap.add_argument("--output", default="")
    ap.add_argument("--recent-hours", type=int, default=72)
    ap.add_argument("--trim-start", type=float, default=0.0)
    ap.add_argument("--trim-end", type=float, default=0.4)
    ap.add_argument("--min-duration", type=float, default=2.0)
    args = ap.parse_args()

    if not ensure_ffmpeg():
        print("ERROR: ffmpeg/ffprobe not found", file=sys.stderr)
        sys.exit(2)

    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.exists():
        print(f"ERROR: input dir not found: {input_dir}", file=sys.stderr)
        sys.exit(3)

    videos = list_videos(input_dir, args.recent_hours)
    videos = [v for v in videos if duration_sec(v) >= args.min_duration]
    if not videos:
        print("ERROR: no recent video clips found", file=sys.stderr)
        sys.exit(4)

    export_dir = Path.home() / ".openclaw" / "workspace" / "flow-auto" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        out = export_dir / f"final_{int(time.time())}.mp4"

    tmp_dir = export_dir / f"tmp_trim_{int(time.time())}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    trimmed = []
    for i, src in enumerate(videos, start=1):
        dst = tmp_dir / f"clip_{i:04d}.mp4"
        ok, msg = trim_clip(src, dst, args.trim_start, args.trim_end)
        if ok:
            trimmed.append(dst)

    if not trimmed:
        print("ERROR: no clips after trimming", file=sys.stderr)
        sys.exit(5)

    ok, msg = concat_clips(trimmed, out)
    for p in trimmed:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    try:
        tmp_dir.rmdir()
    except Exception:
        pass

    if not ok:
        print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(6)

    print(f"OK: {out}")


if __name__ == "__main__":
    main()
