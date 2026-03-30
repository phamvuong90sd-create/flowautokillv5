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
    project_page = None
    flow_page = None

    for context in browser.contexts:
        for page in context.pages:
            url = page.url or ""
            if "labs.google/fx/tools/flow/project/" in url:
                return page
            if "labs.google/fx/tools/flow" in url and flow_page is None:
                flow_page = page

    # fallback: any Flow page (non-project) is still better than failing hard
    return flow_page


def open_flow_page_fallback(browser, flow_url: str):
    # Try open/recover a Flow tab automatically when project tab is missing
    contexts = browser.contexts
    if not contexts:
        raise RuntimeError("Không có browser context để mở Google Flow")

    context = contexts[0]
    page = context.new_page()
    page.goto(flow_url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    return page


def ensure_flow_page(browser, flow_url: str):
    page = find_flow_page(browser)
    if page:
        return page

    # No existing Flow tab -> auto open fallback URL
    page = open_flow_page_fallback(browser, flow_url)
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
    txt = body.inner_text(timeout=2000)
    return "Oops, something went wrong" in txt


def natural_key(p: Path):
    parts = re.split(r"(\d+)", p.name)
    out = []
    for x in parts:
        if x.isdigit():
            out.append(int(x))
        else:
            out.append(x.lower())
    return out


def choose_images(args):
    if not args.images_dir:
        raise RuntimeError("Thiếu --images-dir cho input-mode=image")

    folder = Path(args.images_dir)
    if not folder.exists():
        raise RuntimeError(f"Không thấy thư mục ảnh: {folder}")

    images = [
        p for p in sorted(folder.glob(args.image_glob), key=natural_key)
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ]
    if not images:
        raise RuntimeError(f"Không có ảnh hợp lệ trong: {folder}")

    if args.image_single is not None:
        idx = args.image_single - 1
        if idx < 0 or idx >= len(images):
            raise RuntimeError(f"image-single ngoài phạm vi 1..{len(images)}")
        return [images[idx]]

    start = max(1, args.image_start)
    end = args.image_end if args.image_end is not None else len(images)
    end = min(end, len(images))
    if start > end:
        raise RuntimeError(f"Khoảng ảnh không hợp lệ: start={start}, end={end}")

    return images[start - 1 : end]


def set_aspect_ratio(page, ratio: str):
    # best effort: click settings button then pick ratio option if exists
    if ratio not in {"16:9", "9:16"}:
        return

    try:
        settings_btn = page.locator("button").filter(
            has_text=re.compile(r"(Video|crop_16_9|crop_9_16|16:9|9:16)", re.I)
        ).first
        if settings_btn.count() == 0:
            return
        settings_btn.click(timeout=2000)
        time.sleep(0.4)

        target = page.locator("button,[role='menuitem'],[role='option']").filter(
            has_text=re.compile(rf"({re.escape(ratio)}|crop_{ratio.replace(':', '_')})", re.I)
        )
        if target.count() > 0:
            target.first.click(timeout=2000)
        page.keyboard.press("Escape")
        time.sleep(0.3)
    except Exception:
        # ratio UI can vary, do not hard-fail whole job
        pass


def upload_image(page, image_path: Path):
    # If media dialog is already open, avoid re-clicking Add Media
    file_inputs = page.locator("input[type='file']")
    if file_inputs.count() == 0:
        add_btn = page.locator("button").filter(has_text=re.compile(r"Add Media", re.I))
        if add_btn.count() == 0:
            raise RuntimeError("Không thấy nút Add Media")
        try:
            add_btn.first.click(timeout=5000)
        except Exception:
            add_btn.first.click(timeout=5000, force=True)
        time.sleep(0.6)

    # In some UI variants upload input appears only after clicking Upload image
    file_inputs = page.locator("input[type='file']")
    if file_inputs.count() == 0:
        upload_btn = page.locator("button").filter(has_text=re.compile(r"Upload image", re.I))
        if upload_btn.count() > 0:
            try:
                upload_btn.first.click(timeout=3000)
            except Exception:
                upload_btn.first.click(timeout=3000, force=True)
            time.sleep(0.5)

    file_inputs = page.locator("input[type='file']")
    if file_inputs.count() == 0:
        raise RuntimeError("Không thấy input upload file")

    file_inputs.last.set_input_files(str(image_path.resolve()))
    time.sleep(1.0)

    # close media dialog after selecting file
    dismiss_overlays(page)
    time.sleep(0.3)


def dismiss_overlays(page):
    # best effort to close menus/dialog overlays that may intercept Create click
    try:
        for _ in range(3):
            page.keyboard.press("Escape")
            time.sleep(0.15)
    except Exception:
        pass


def create_once(page, args, prompt_text: str | None = None, image_path: Path | None = None):
    page.bring_to_front()

    if args.input_mode == "text":
        if prompt_text is None:
            raise RuntimeError("Thiếu prompt_text")
        box = find_input_box(page)
        box.click(timeout=5000)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")

        time.sleep(random.uniform(args.pre_paste_min, args.pre_paste_max))
        page.keyboard.insert_text(prompt_text)

    elif args.input_mode == "image":
        if image_path is None:
            raise RuntimeError("Thiếu image_path")
        upload_image(page, image_path)

    set_aspect_ratio(page, args.aspect_ratio)
    dismiss_overlays(page)

    time.sleep(args.before_create_sec)
    btn = find_create_button(page)
    try:
        btn.click(timeout=5000)
    except Exception:
        dismiss_overlays(page)
        btn.click(timeout=5000, force=True)

    time.sleep(2)
    if has_failure(page):
        raise RuntimeError("Flow báo lỗi sau khi bấm Create")


def run_text_mode(args, page):
    prompts = load_prompts(args.prompts)
    total = len(prompts)

    state = load_state(args.state)
    done = int(state.get("done", 0))
    if args.start_from is not None:
        done = max(0, args.start_from - 1)

    print(f"[flow-text] total prompts: {total}")
    print(f"[flow-text] starting from prompt #{done + 1}")

    for idx in range(done, total):
        prompt = prompts[idx]
        prompt_no = idx + 1
        ok = False

        for attempt in range(1, args.max_retries + 2):
            try:
                create_once(page, args, prompt_text=prompt)
                ok = True
                break
            except (PWTimeout, Exception) as e:
                print(f"[flow-text] prompt #{prompt_no} attempt {attempt} lỗi: {e}")
                if attempt <= args.max_retries:
                    time.sleep(2)

        if not ok:
            print(f"[flow-text] prompt #{prompt_no} thất bại sau retry, bỏ qua và tiếp tục")
            failed = state.get("failed_prompts", []) if isinstance(state, dict) else []
            failed.append(prompt_no)
            state = {
                "done": idx,
                "total": total,
                "failed_prompts": failed,
                "last_failed": prompt_no,
                "mode": "text",
                "ts": int(time.time()),
            }
            save_state(args.state, state)
            if prompt_no < total:
                time.sleep(args.between_prompts_sec)
            continue

        save_state(args.state, {
            "done": prompt_no,
            "total": total,
            "mode": "text",
            "ts": int(time.time()),
        })

        if prompt_no % args.batch_size == 0 or prompt_no == total:
            print(f"[flow-text] progress: {prompt_no}/{total}")

        if prompt_no < total:
            time.sleep(args.between_prompts_sec)

    print("[flow-text] hoàn tất toàn bộ kịch bản")


def run_image_mode(args, page):
    images = choose_images(args)
    total_tasks = len(images) * args.videos_per_image

    state = load_state(args.state)
    done = int(state.get("done", 0))
    if args.start_from is not None:
        done = max(0, args.start_from - 1)

    print(f"[flow-image] selected images: {len(images)}")
    print(f"[flow-image] videos/image: {args.videos_per_image}")
    print(f"[flow-image] total tasks: {total_tasks}")

    task_no = 0
    for image_idx, image_path in enumerate(images, start=1):
        for video_idx in range(1, args.videos_per_image + 1):
            task_no += 1
            if task_no <= done:
                continue

            ok = False
            for attempt in range(1, args.max_retries + 2):
                try:
                    create_once(page, args, image_path=image_path)
                    ok = True
                    break
                except (PWTimeout, Exception) as e:
                    print(
                        f"[flow-image] task #{task_no} (img {image_idx}/{len(images)}:{image_path.name}, v{video_idx}) attempt {attempt} lỗi: {e}"
                    )
                    if attempt <= args.max_retries:
                        time.sleep(2)

            if not ok:
                print(f"[flow-image] task #{task_no} thất bại sau retry, bỏ qua")
                failed = state.get("failed_tasks", []) if isinstance(state, dict) else []
                failed.append({
                    "task": task_no,
                    "image": image_path.name,
                    "video_idx": video_idx,
                })
                state = {
                    "done": task_no - 1,
                    "total": total_tasks,
                    "mode": "image",
                    "failed_tasks": failed,
                    "last_failed": task_no,
                    "ts": int(time.time()),
                }
                save_state(args.state, state)
                if task_no < total_tasks:
                    time.sleep(args.between_prompts_sec)
                continue

            save_state(args.state, {
                "done": task_no,
                "total": total_tasks,
                "mode": "image",
                "current_image": image_path.name,
                "current_video_idx": video_idx,
                "ts": int(time.time()),
            })

            if task_no % args.batch_size == 0 or task_no == total_tasks:
                print(f"[flow-image] progress: {task_no}/{total_tasks}")

            if task_no < total_tasks:
                time.sleep(args.between_prompts_sec)

    print("[flow-image] hoàn tất toàn bộ job ảnh")


def run(args):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        page = ensure_flow_page(browser, args.flow_url)
        if not page:
            raise RuntimeError("Không thể mở hoặc tìm thấy tab Google Flow")

        page.bring_to_front()
        if args.input_mode == "text":
            run_text_mode(args, page)
        else:
            run_image_mode(args, page)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-mode", choices=["text", "image"], default="text")

    # text mode args
    ap.add_argument("--prompts", type=Path, help="txt prompts (required when input-mode=text)")

    # image mode args
    ap.add_argument("--images-dir", type=Path, help="folder containing source images")
    ap.add_argument("--image-glob", default="*", help="glob pattern in images-dir")
    ap.add_argument("--image-start", type=int, default=1, help="1-based scene start")
    ap.add_argument("--image-end", type=int, default=None, help="1-based scene end")
    ap.add_argument("--image-single", type=int, default=None, help="single scene index (1-based)")
    ap.add_argument("--videos-per-image", type=int, default=1, help="number of videos per image")

    # common args
    default_state = Path.home() / ".openclaw" / "workspace" / ".flow_state.json"
    ap.add_argument("--state", type=Path, default=default_state)
    ap.add_argument("--cdp", default="http://127.0.0.1:18800")
    ap.add_argument("--flow-url", default="https://labs.google/fx/tools/flow", help="Fallback URL when project tab is missing")
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--pre-paste-min", type=float, default=0.5)
    ap.add_argument("--pre-paste-max", type=float, default=1.5)
    ap.add_argument("--before-create-sec", type=float, default=3.0)
    ap.add_argument("--between-prompts-sec", type=float, default=10.0)
    ap.add_argument("--start-from", type=int, default=None, help="1-based task index")
    ap.add_argument("--aspect-ratio", choices=["16:9", "9:16"], default="16:9")

    args = ap.parse_args()

    if args.input_mode == "text" and not args.prompts:
        raise SystemExit("--prompts là bắt buộc khi --input-mode=text")

    if args.input_mode == "image" and not args.images_dir:
        raise SystemExit("--images-dir là bắt buộc khi --input-mode=image")

    run(args)


if __name__ == "__main__":
    main()
