import argparse
import json
import random
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


def load_prompts(path: Path):
    text = path.read_text(encoding="utf-8")
    return [p.strip().replace("\n", " ") for p in text.split("\n\n") if p.strip()]


def load_state(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def find_flow_page(browser):
    for context in browser.contexts:
        for page in context.pages:
            if "labs.google/fx/tools/flow/project/" in page.url:
                return page
    return None


def find_input_box(page):
    boxes = page.locator('div[role="textbox"][contenteditable="true"]')
    count = boxes.count()
    for i in range(count - 1, -1, -1):
        b = boxes.nth(i)
        if b.is_visible():
            return b
    raise RuntimeError("Không tìm thấy ô nhập prompt")


def find_create_button(page):
    candidates = page.locator("button").filter(has_text=re.compile(r"Create", re.I))
    count = candidates.count()
    for i in range(count - 1, -1, -1):
        btn = candidates.nth(i)
        if btn.is_visible() and btn.is_enabled():
            return btn
    raise RuntimeError("Không tìm thấy nút Create")


def has_failure(page):
    # Conservative check: only treat explicit global Oops banner as failure.
    # Per-item "Failed/Retry" cards may exist from older jobs and should not stop the loop.
    body = page.locator("body")
    txt = body.inner_text(timeout=2000)
    return "Oops, something went wrong" in txt


def run(args):
    prompts = load_prompts(args.prompts)
    total = len(prompts)

    state = load_state(args.state)
    done = int(state.get("done", 0))
    if args.start_from is not None:
        done = max(0, args.start_from - 1)

    print(f"[flow] total prompts: {total}")
    print(f"[flow] starting from prompt #{done + 1}")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        page = find_flow_page(browser)
        if not page:
            raise RuntimeError("Không tìm thấy tab Flow project đang mở")

        page.bring_to_front()

        for idx in range(done, total):
            prompt = prompts[idx]
            prompt_no = idx + 1
            ok = False

            for attempt in range(1, args.max_retries + 2):
                try:
                    page.bring_to_front()
                    box = find_input_box(page)
                    box.click(timeout=5000)
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")

                    time.sleep(random.uniform(args.pre_paste_min, args.pre_paste_max))
                    page.keyboard.insert_text(prompt)

                    time.sleep(args.before_create_sec)
                    btn = find_create_button(page)
                    btn.click(timeout=5000)

                    time.sleep(2)
                    if has_failure(page):
                        raise RuntimeError("Flow báo lỗi sau khi bấm Create")

                    ok = True
                    break
                except (PWTimeout, Exception) as e:
                    print(f"[flow] prompt #{prompt_no} attempt {attempt} lỗi: {e}")
                    if attempt <= args.max_retries:
                        time.sleep(2)

            if not ok:
                print(f"[flow] prompt #{prompt_no} thất bại sau retry, bỏ qua và tiếp tục")
                failed = state.get("failed_prompts", []) if isinstance(state, dict) else []
                failed.append(prompt_no)
                state = {
                    "done": idx,
                    "total": total,
                    "failed_prompts": failed,
                    "last_failed": prompt_no,
                    "ts": int(time.time()),
                }
                save_state(args.state, state)
                if prompt_no < total:
                    time.sleep(args.between_prompts_sec)
                continue

            save_state(args.state, {
                "done": prompt_no,
                "total": total,
                "ts": int(time.time()),
            })

            if prompt_no % args.batch_size == 0 or prompt_no == total:
                print(f"[flow] progress: {prompt_no}/{total}")

            if prompt_no < total:
                time.sleep(args.between_prompts_sec)

        print("[flow] hoàn tất toàn bộ kịch bản")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", type=Path, required=True)
    default_state = Path.home() / ".openclaw" / "workspace" / ".flow_state.json"
    ap.add_argument("--state", type=Path, default=default_state)
    ap.add_argument("--cdp", default="http://127.0.0.1:18800")
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--pre-paste-min", type=float, default=0.5)
    ap.add_argument("--pre-paste-max", type=float, default=1.5)
    ap.add_argument("--before-create-sec", type=float, default=3.0)
    ap.add_argument("--between-prompts-sec", type=float, default=10.0)
    ap.add_argument("--start-from", type=int, default=None, help="1-based prompt index")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
