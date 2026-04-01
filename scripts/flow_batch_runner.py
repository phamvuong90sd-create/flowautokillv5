import argparse
import json
import random
import re
import time
from datetime import datetime
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


def human_type_text(page, text: str, min_delay_ms: int = 35, max_delay_ms: int = 95):
    """
    Type text with human-like rhythm to reduce anti-bot flakiness.
    """
    min_d = max(0, int(min_delay_ms))
    max_d = max(min_d, int(max_delay_ms))

    words = text.split(" ")
    for i, w in enumerate(words):
        page.keyboard.type(w, delay=random.randint(min_d, max_d))

        # put spaces between words naturally
        if i < len(words) - 1:
            page.keyboard.type(" ", delay=random.randint(min_d, max_d))

        # occasional micro-pause like human thinking rhythm
        if i > 0 and i % random.randint(7, 14) == 0:
            time.sleep(random.uniform(0.10, 0.45))


def paste_text_like_human(page, text: str, wait_sec: float = 5.0):
    """
    Hybrid input flow to reduce Create errors:
    - type first character manually
    - copy remaining text to clipboard
    - wait, then Ctrl+V to paste remainder

    Falls back safely when clipboard API is blocked.
    """
    if not text:
        return

    # 1) Type first character like a real user
    first = text[0]
    rest = text[1:]
    page.keyboard.type(first, delay=random.randint(45, 120))

    # nothing else to paste
    if not rest:
        time.sleep(random.uniform(0.15, 0.4))
        return

    # 2) Copy remaining text into clipboard
    copied = False
    try:
        page.evaluate("(t) => navigator.clipboard.writeText(t)", rest)
        copied = True
    except Exception:
        copied = False

    # 3) Wait then paste the remaining part
    time.sleep(max(0.2, float(wait_sec)))

    if copied:
        page.keyboard.press("Control+V")
    else:
        page.keyboard.insert_text(rest)

    time.sleep(random.uniform(0.2, 0.5))


def prompt_box_text(box) -> str:
    try:
        return (box.inner_text(timeout=1200) or "").strip()
    except Exception:
        return ""


def place_mouse_at_prompt_end(page, box) -> None:
    """
    Move mouse to the visual end of prompt box and place caret at end,
    then keep cursor there before clicking Create.
    """
    try:
        rect = box.evaluate(
            """
            el => {
              const r = el.getBoundingClientRect();
              return {x:r.x, y:r.y, w:r.width, h:r.height};
            }
            """
        )
        if rect and rect.get("w", 0) > 0 and rect.get("h", 0) > 0:
            x = int(rect["x"] + rect["w"] - 14)
            y = int(rect["y"] + rect["h"] - 12)
            page.mouse.move(x, y, steps=10)
            page.mouse.click(x, y)
    except Exception:
        pass

    # Ensure caret is at text end (contenteditable/textarea safe)
    try:
        page.keyboard.press("End")
        page.keyboard.press("ArrowRight")
    except Exception:
        pass


def ensure_prompt_present(page, box, prompt_text: str, input_method: str, paste_wait_sec: float) -> None:
    """
    Guard against Flow error 'Prompt must be provided'.
    Re-apply input up to 3 times if textbox is empty.
    """
    for attempt in range(1, 4):
        current = prompt_box_text(box)
        if len(current) >= 8:
            return

        try:
            box.click(timeout=2500)
        except Exception:
            pass

        if input_method == "paste":
            paste_text_like_human(page, prompt_text, wait_sec=max(1.0, paste_wait_sec))
        else:
            human_type_text(page, prompt_text)

        time.sleep(0.35)

    raise RuntimeError("Prompt must be provided (textbox empty after retries)")


def save_state(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def capture_debug_screenshot(page, tag: str = "flow"):
    try:
        out_dir = Path.home() / ".openclaw" / "workspace" / "flow-auto" / "debug"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = out_dir / f"{tag}-{ts}.png"
        page.screenshot(path=str(out), full_page=False)
        print(f"[flow-debug] screenshot: {out}")
    except Exception:
        pass


def lock_window_geometry(page, width: int = 1280, height: int = 800, left: int = 20, top: int = 20, state: str = "normal"):
    """
    Force a stable Chrome window state/size to reduce Flow UI flakiness.
    Works with Playwright over CDP.
    """
    try:
        session = page.context.new_cdp_session(page)
        info = session.send("Browser.getWindowForTarget")
        window_id = info.get("windowId")
        if window_id:
            s = (state or "maximized").strip().lower()
            if s == "maximized":
                bounds = {"windowState": "maximized"}
            else:
                bounds = {
                    "left": int(left),
                    "top": int(top),
                    "width": int(width),
                    "height": int(height),
                    "windowState": "normal",
                }

            session.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": bounds,
                },
            )
            time.sleep(0.25)
    except Exception:
        # best-effort only
        pass


def find_project_page(browser):
    for context in browser.contexts:
        for page in context.pages:
            if "labs.google/fx/tools/flow/project/" in (page.url or ""):
                return page
    return None


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


def ensure_project_page(browser, page):
    # capture current screen for troubleshooting
    capture_debug_screenshot(page, "before-new-project")

    # already on project page
    if "labs.google/fx/tools/flow/project/" in (page.url or ""):
        return page

    # try click "New project" / "Create project"
    clicked = False
    try:
        candidates = page.locator("button,[role='button'],a").filter(
            has_text=re.compile(r"(New\s*project|Create\s*project|Start\s*project)", re.I)
        )
        count = candidates.count()
        for i in range(count):
            c = candidates.nth(i)
            if c.is_visible():
                try:
                    c.click(timeout=3000)
                except Exception:
                    c.click(timeout=3000, force=True)
                clicked = True
                print("[flow-debug] clicked New project")
                break
    except Exception:
        pass

    if clicked:
        try:
            page.wait_for_timeout(700)
            capture_debug_screenshot(page, "after-new-project-click")
        except Exception:
            pass

    # wait for project page to appear (same tab or new tab)
    deadline = time.time() + 25
    while time.time() < deadline:
        p = find_project_page(browser)
        if p:
            capture_debug_screenshot(p, "project-ready")
            return p

        # fallback: if textbox already exists on this page, proceed
        try:
            boxes = page.locator('div[role="textbox"][contenteditable="true"]')
            if boxes.count() > 0:
                capture_debug_screenshot(page, "textbox-ready")
                return page
        except Exception:
            pass

        time.sleep(0.5)

    raise RuntimeError("Không mở được trang Flow project (chưa vào được New project)")


def open_flow_page_fallback(browser, flow_url: str, login_first: bool = True, login_url: str = "https://accounts.google.com"):
    # Try open/recover a Flow tab automatically when project tab is missing
    contexts = browser.contexts
    if not contexts:
        raise RuntimeError("Không có browser context để mở Google Flow")

    context = contexts[0]
    page = context.new_page()

    if login_first:
        # Open Google account page first so profile can auto-restore login session
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1200)
        except Exception:
            pass

    page.goto(flow_url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    return page


def ensure_flow_page(browser, flow_url: str, login_first: bool = True, login_url: str = "https://accounts.google.com"):
    page = find_flow_page(browser)
    if page:
        return page

    # No existing Flow tab -> auto open fallback URL
    page = open_flow_page_fallback(browser, flow_url, login_first=login_first, login_url=login_url)
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
    low = txt.lower()
    return ("oops, something went wrong" in low) or ("prompt must be provided" in low)


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


def detect_generation_mode(page) -> str:
    """
    Best-effort mode detection on Flow UI.
    Returns: 'video' | 'image' | 'unknown'
    """
    # 1) Strong signal: selected tab inside model menu/panel
    try:
        selected_video_tab = page.locator("[role='tab'][aria-selected='true']").filter(
            has_text=re.compile(r"\bvideo\b", re.I)
        )
        if selected_video_tab.count() > 0:
            return "video"

        selected_image_tab = page.locator("[role='tab'][aria-selected='true']").filter(
            has_text=re.compile(r"\bimage\b", re.I)
        )
        if selected_image_tab.count() > 0:
            return "image"
    except Exception:
        pass

    # 2) Body text fallback
    try:
        txt = page.locator("body").inner_text(timeout=2500).lower()
    except Exception:
        return "unknown"

    # Prefer explicit video signals before nano label to avoid false image lock
    if re.search(r"veo\s*3", txt) or re.search(r"\bvideo\b", txt) or re.search(r"videocam", txt):
        return "video"
    if re.search(r"nano\s*banana", txt):
        return "image"
    return "unknown"


def ensure_video_mode(page):
    """
    Ensure generation mode is video (Veo/Video tab), not Nano Banana image mode.
    Hard-fix sequence when Nano Banana appears:
      1) Open model menu
      2) Click Video tab in that menu
      3) If possible choose Veo model
    """

    def safe_click(locator) -> bool:
        try:
            if locator.count() > 0 and locator.first.is_visible():
                try:
                    locator.first.click(timeout=2200)
                except Exception:
                    locator.first.click(timeout=2200, force=True)
                time.sleep(0.35)
                return True
        except Exception:
            pass
        return False

    def click_text(pattern: str) -> bool:
        loc = page.locator("button,[role='button'],[role='tab'],[role='option'],[role='menuitem'],a,div,span").filter(
            has_text=re.compile(pattern, re.I)
        )
        return safe_click(loc)

    if detect_generation_mode(page) == "video":
        return

    for _ in range(10):
        mode = detect_generation_mode(page)
        if mode == "video":
            return

        # 1) If currently Nano Banana (image), open its menu first
        if mode == "image":
            click_text(r"nano\s*banana")
            time.sleep(0.2)

            # 2) Hard switch tab inside popup/menu: 'videocam Video'
            video_tab = page.locator("[role='tab']").filter(has_text=re.compile(r"\bvideo\b", re.I))
            if safe_click(video_tab):
                time.sleep(0.4)
                if detect_generation_mode(page) == "video":
                    return

            # 3) Optional: choose Veo model if shown
            click_text(r"veo\s*3")
            time.sleep(0.4)
            if detect_generation_mode(page) == "video":
                return

        # General fallbacks
        click_text(r"\bvideo\b")
        time.sleep(0.3)
        if detect_generation_mode(page) == "video":
            return

        click_text(r"(veo\s*3|text\s*to\s*video|video\s*model)")
        time.sleep(0.4)
        if detect_generation_mode(page) == "video":
            return

        dismiss_overlays(page)
        time.sleep(0.2)

    mode = detect_generation_mode(page)
    if mode == "image":
        raise RuntimeError("Đang ở Nano Banana (tạo ảnh). Cần chuyển sang Veo 3/Video trước khi chạy prompt")
    raise RuntimeError("Không thể xác nhận/đổi sang tab Video trong Flow")


def ensure_aspect_ratio_compatible(page, ratio: str):
    if ratio not in {"16:9", "9:16"}:
        return

    mode = detect_generation_mode(page)
    if mode == "image":
        raise RuntimeError("Đang ở Nano Banana (tạo ảnh). Hãy chuyển sang Veo 3 (tạo video) trước khi chỉnh 16:9 / 9:16")


def is_ratio_selected(page, ratio: str) -> bool:
    try:
        selector = page.locator("button,[role='button'],[role='tab'],[role='option']").filter(
            has_text=re.compile(rf"(^|\s){re.escape(ratio)}($|\s)|crop_{ratio.replace(':', '_')}", re.I)
        )
        c = selector.count()
        for i in range(c):
            el = selector.nth(i)
            if not el.is_visible():
                continue
            try:
                aria_selected = (el.get_attribute("aria-selected") or "").lower()
                aria_pressed = (el.get_attribute("aria-pressed") or "").lower()
                cls = (el.get_attribute("class") or "").lower()
                if aria_selected == "true" or aria_pressed == "true":
                    return True
                if any(k in cls for k in ["selected", "active", "checked"]):
                    return True
            except Exception:
                pass

        # fallback text-based hint
        snap = (page.locator("body").inner_text(timeout=1800) or "")
        return (ratio in snap) or (f"crop_{ratio.replace(':', '_')}" in snap)
    except Exception:
        return False


def set_aspect_ratio(page, ratio: str):
    if ratio not in {"16:9", "9:16"}:
        return

    # Try up to 4 rounds: click -> screenshot -> verify -> retry if needed
    for attempt in range(1, 5):
        try:
            capture_debug_screenshot(page, f"ratio-before-{ratio.replace(':','_')}-a{attempt}")

            settings_btn = page.locator("button,[role='button']").filter(
                has_text=re.compile(r"(crop_16_9|crop_9_16|16:9|9:16|\bVideo\b)", re.I)
            ).first
            if settings_btn.count() > 0 and settings_btn.is_visible():
                try:
                    settings_btn.click(timeout=2500)
                except Exception:
                    settings_btn.click(timeout=2500, force=True)
                time.sleep(0.35)

            target = page.locator("button,[role='menuitem'],[role='option'],[role='tab']").filter(
                has_text=re.compile(rf"(^|\s){re.escape(ratio)}($|\s)|crop_{ratio.replace(':', '_')}", re.I)
            )
            if target.count() > 0:
                try:
                    target.first.click(timeout=2500)
                except Exception:
                    target.first.click(timeout=2500, force=True)
                time.sleep(0.4)

            capture_debug_screenshot(page, f"ratio-after-{ratio.replace(':','_')}-a{attempt}")

            if is_ratio_selected(page, ratio):
                page.keyboard.press("Escape")
                time.sleep(0.2)
                return

        except Exception:
            pass

        time.sleep(0.45)

    raise RuntimeError(f"Không gạt được tỉ lệ {ratio} trên UI Flow (đã retry + check ảnh)")


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


def auto_download_completed_outputs(page, max_items: int = 3) -> int:
    """
    Best-effort auto download after full run.
    Returns number of successful download clicks triggered.
    """
    triggered = 0
    capture_debug_screenshot(page, "download-before")

    # 1) Direct visible Download buttons
    try:
        direct = page.locator("button,[role='button'],a,[role='menuitem']").filter(
            has_text=re.compile(r"\bDownload\b", re.I)
        )
        c = direct.count()
        for i in range(c):
            if triggered >= max_items:
                break
            b = direct.nth(i)
            if not b.is_visible():
                continue
            try:
                b.click(timeout=2000)
            except Exception:
                b.click(timeout=2000, force=True)
            triggered += 1
            time.sleep(0.4)
    except Exception:
        pass

    # 2) If no direct download, open menu then click Download
    if triggered == 0:
        try:
            menus = page.locator("button,[role='button']").filter(
                has_text=re.compile(r"(more_vert|more options|⋮)", re.I)
            )
            mcount = menus.count()
            for i in range(mcount):
                if triggered >= max_items:
                    break
                m = menus.nth(i)
                if not m.is_visible():
                    continue
                try:
                    m.click(timeout=1800)
                except Exception:
                    m.click(timeout=1800, force=True)
                time.sleep(0.3)

                dl = page.locator("button,[role='menuitem'],[role='option'],a").filter(
                    has_text=re.compile(r"\bDownload\b", re.I)
                )
                if dl.count() > 0 and dl.first.is_visible():
                    try:
                        dl.first.click(timeout=1800)
                    except Exception:
                        dl.first.click(timeout=1800, force=True)
                    triggered += 1
                    time.sleep(0.4)

                dismiss_overlays(page)
        except Exception:
            pass

    capture_debug_screenshot(page, "download-after")
    return triggered


def create_once(page, args, prompt_text: str | None = None, image_path: Path | None = None, create_delay_boost_sec: float = 0.0):
    page.bring_to_front()
    ensure_video_mode(page)

    box = None

    if args.input_mode == "text":
        if prompt_text is None:
            raise RuntimeError("Thiếu prompt_text")
        box = find_input_box(page)
        box.click(timeout=5000)

        # Robust clear: Ctrl+A may fail on some contenteditable variants
        try:
            box.evaluate(
                """
                el => {
                  el.focus();
                  if ('value' in el) el.value = '';
                  el.textContent = '';
                  el.innerHTML = '';
                  const sel = window.getSelection && window.getSelection();
                  if (sel && sel.removeAllRanges) sel.removeAllRanges();
                }
                """
            )
        except Exception:
            pass

        # Fallback key-based clear
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.press("Delete")

        # Sanity check: if still has large residual text, clear again
        try:
            current = (box.inner_text(timeout=1000) or "").strip()
            if len(current) > 20:
                box.evaluate("el => { el.textContent = ''; el.innerHTML = ''; }")
        except Exception:
            pass

        # Human-like pacing before input (simulate user focusing field)
        time.sleep(random.uniform(args.pre_paste_min, args.pre_paste_max))

        # micro cursor movement & focus nudge like a real user
        try:
            box.hover(timeout=1200)
            page.mouse.move(120 + random.randint(0, 180), 220 + random.randint(0, 220), steps=8)
            box.click(timeout=2000)
        except Exception:
            pass

        if args.input_method == "paste":
            # Clipboard-like flow: click field -> wait ~5s -> paste remainder
            paste_text_like_human(page, prompt_text, wait_sec=args.paste_wait_sec)
        else:
            human_type_text(
                page,
                prompt_text,
                min_delay_ms=args.type_delay_min_ms,
                max_delay_ms=args.type_delay_max_ms,
            )
            # Small pause after typing to mimic human verify/readback
            time.sleep(random.uniform(args.post_type_min_sec, args.post_type_max_sec))

        # Occasionally move cursor naturally
        try:
            page.keyboard.press("ArrowLeft")
            page.keyboard.press("ArrowRight")
        except Exception:
            pass

        # Final settle before any further UI actions
        time.sleep(random.uniform(0.15, 0.45))

        # Ensure prompt actually exists in textbox before Create
        ensure_prompt_present(page, box, prompt_text, args.input_method, args.paste_wait_sec)

        # Stabilize contenteditable for Flow parser before clicking Create
        page.keyboard.press("End")
        page.keyboard.press("Space")
        page.keyboard.press("Backspace")
        time.sleep(random.uniform(0.10, 0.25))

    elif args.input_mode == "image":
        if image_path is None:
            raise RuntimeError("Thiếu image_path")
        upload_image(page, image_path)

    ensure_aspect_ratio_compatible(page, args.aspect_ratio)
    set_aspect_ratio(page, args.aspect_ratio)
    dismiss_overlays(page)

    # Do not click Create too quickly: wait with human-like jitter
    time.sleep(args.before_create_sec + create_delay_boost_sec + random.uniform(args.create_jitter_min_sec, args.create_jitter_max_sec))

    # Requirement: keep mouse/caret at end of prompt before Create
    if box is not None:
        place_mouse_at_prompt_end(page, box)

    # Additional hold before Create to simulate real user confirmation
    time.sleep(max(0.0, args.pre_create_hold_sec))
    btn = find_create_button(page)

    # tiny hover/read delay like a real user
    try:
        btn.hover(timeout=1500)
    except Exception:
        pass
    time.sleep(random.uniform(0.20, 0.65))

    try:
        btn.click(timeout=5000, delay=random.randint(40, 120))
    except Exception:
        dismiss_overlays(page)
        time.sleep(random.uniform(0.25, 0.60))
        btn.click(timeout=5000, force=True)

    time.sleep(2.2)
    if has_failure(page):
        # Root-cause helper for "Prompt must be provided"
        detail = ""
        if box is not None:
            try:
                current_after = prompt_box_text(box)
                detail = f" | prompt_len_after_click={len(current_after)}"
            except Exception:
                pass
        raise RuntimeError("Flow báo lỗi sau khi bấm Create" + detail)


def run_text_mode(args, page):
    prompts = load_prompts(args.prompts)

    def with_prompt_variant(base_prompt: str, variant_idx: int) -> str:
        if variant_idx == 1:
            return base_prompt
        if variant_idx == 2:
            return base_prompt.rstrip() + "."
        if variant_idx == 3:
            return base_prompt.rstrip() + " cinematic"
        return base_prompt
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
                prompt_variant = with_prompt_variant(prompt, attempt)
                delay_boost = 0.0 if attempt == 1 else min(2.5, 0.9 * (attempt - 1))
                create_once(page, args, prompt_text=prompt_variant, create_delay_boost_sec=delay_boost)
                ok = True
                break
            except (PWTimeout, Exception) as e:
                print(f"[flow-text] prompt #{prompt_no} attempt {attempt} lỗi: {e}")
                if attempt <= args.max_retries:
                    # hard-recovery: refresh project page before next attempt
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=45000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except Exception:
                            pass
                        page.bring_to_front()
                    except Exception:
                        pass
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
    try:
        downloaded = auto_download_completed_outputs(page)
        print(f"[flow-text] auto-download triggered: {downloaded}")
    except Exception as e:
        print(f"[flow-text] auto-download error: {e}")


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
        page = ensure_flow_page(
            browser,
            args.flow_url,
            login_first=args.google_login_first,
            login_url=args.google_login_url,
        )
        if not page:
            raise RuntimeError("Không thể mở hoặc tìm thấy tab Google Flow")

        page = ensure_project_page(browser, page)
        page.bring_to_front()

        # Lock window geometry to stable layout before interactions
        lock_window_geometry(
            page,
            width=args.window_width,
            height=args.window_height,
            left=args.window_x,
            top=args.window_y,
            state=args.window_state,
        )

        # Final pre-start verification snapshot
        capture_debug_screenshot(page, "pre-start-check")

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
    ap.add_argument("--google-login-first", action="store_true", default=True, help="Open Google account page first before Flow")
    ap.add_argument("--google-login-url", default="https://accounts.google.com", help="Google login page URL")
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--pre-paste-min", type=float, default=1.0)
    ap.add_argument("--pre-paste-max", type=float, default=1.0)
    ap.add_argument("--input-method", choices=["paste", "type"], default="paste")
    ap.add_argument("--paste-wait-sec", type=float, default=5.0)
    ap.add_argument("--type-delay-min-ms", type=int, default=35)
    ap.add_argument("--type-delay-max-ms", type=int, default=95)
    ap.add_argument("--post-type-min-sec", type=float, default=0.8)
    ap.add_argument("--post-type-max-sec", type=float, default=1.8)
    ap.add_argument("--before-create-sec", type=float, default=3.6)
    ap.add_argument("--create-jitter-min-sec", type=float, default=0.6)
    ap.add_argument("--create-jitter-max-sec", type=float, default=1.8)
    ap.add_argument("--pre-create-hold-sec", type=float, default=5.0)
    ap.add_argument("--between-prompts-sec", type=float, default=10.0)
    ap.add_argument("--window-state", choices=["maximized", "normal"], default="normal")
    ap.add_argument("--window-width", type=int, default=1280)
    ap.add_argument("--window-height", type=int, default=800)
    ap.add_argument("--window-x", type=int, default=20)
    ap.add_argument("--window-y", type=int, default=20)
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
