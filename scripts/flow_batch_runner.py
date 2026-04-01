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


def is_flow_url(url: str) -> bool:
    return "labs.google/fx/tools/flow" in (url or "")


def find_flow_page(browser):
    project = None
    flow = None
    for context in browser.contexts:
        for page in context.pages:
            url = page.url or ""
            if "labs.google/fx/tools/flow/project/" in url:
                project = page
                break
            if is_flow_url(url) and flow is None:
                flow = page
        if project:
            break
    return project or flow


def close_extra_flow_tabs(browser, keep_page):
    if not keep_page:
        return
    for context in browser.contexts:
        for page in list(context.pages):
            if page == keep_page:
                continue
            if is_flow_url(page.url or ""):
                try:
                    page.close()
                except Exception:
                    pass


def ensure_project_page(page):
    url = page.url or ""
    if "labs.google/fx/tools/flow/project/" in url:
        return page

    try:
        new_project_btn = page.locator("button,[role='button'],a,[role='link']").filter(
            has_text=re.compile(r"new\s*project", re.I)
        )
        if new_project_btn.count() > 0:
            try:
                new_project_btn.first.click(timeout=5000)
            except Exception:
                new_project_btn.first.click(timeout=5000, force=True)
            time.sleep(2.0)
    except Exception:
        pass

    return page


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
    body = page.locator("body")
    txt = (body.inner_text(timeout=2500) or "").lower()
    return (
        "oops, something went wrong" in txt
        or "prompt must be provided" in txt
        or "đã xảy ra lỗi" in txt
    )


def set_aspect_ratio(page, ratio: str):
    if ratio not in {"16:9", "9:16"}:
        return

    try:
        ratio_btn = page.locator("button,[role='button'],[role='tab'],[role='option']").filter(
            has_text=re.compile(r"(16:9|9:16|crop_16_9|crop_9_16)", re.I)
        )
        if ratio_btn.count() > 0:
            try:
                ratio_btn.first.click(timeout=3000)
            except Exception:
                ratio_btn.first.click(timeout=3000, force=True)
            time.sleep(0.35)

        target = page.locator("button,[role='button'],[role='tab'],[role='menuitem'],[role='option']").filter(
            has_text=re.compile(rf"(^|\s){re.escape(ratio)}($|\s)|crop_{ratio.replace(':','_')}", re.I)
        )
        if target.count() > 0:
            try:
                target.first.click(timeout=3000)
            except Exception:
                target.first.click(timeout=3000, force=True)
            time.sleep(0.35)
    except Exception:
        pass


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
            raise RuntimeError("Không tìm thấy tab Flow đang mở")

        page = ensure_project_page(page)
        page.bring_to_front()
        close_extra_flow_tabs(browser, page)

        for idx in range(done, total):
            prompt = prompts[idx]
            prompt_no = idx + 1
            ok = False

            for attempt in range(1, args.max_retries + 2):
                try:
                    page.bring_to_front()

                    # Theo yêu cầu: chọn tỉ lệ trước rồi mới nhập prompt
                    set_aspect_ratio(page, args.aspect_ratio)

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
    ap.add_argument("--aspect-ratio", default="9:16")
    ap.add_argument("--flow-url", default="https://labs.google/fx/tools/flow")
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--pre-paste-min", type=float, default=0.5)
    ap.add_argument("--pre-paste-max", type=float, default=1.5)
    ap.add_argument("--before-create-sec", type=float, default=3.0)
    ap.add_argument("--between-prompts-sec", type=float, default=10.0)
    ap.add_argument("--start-from", type=int, default=None, help="1-based prompt index")

    args, _unknown = ap.parse_known_args()
    run(args)


if __name__ == "__main__":
    main()
