import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROMPT_INPUT_RULE_VERSION = "v2.0-ref-image-map"


def log_line(msg: str):
    # avoid UnicodeEncodeError on Windows cp1252 console/log sink
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            safe = msg.encode("ascii", "ignore").decode("ascii", "ignore")
            print(safe)
        except Exception:
            print("[flow] log encoding fallback")


def resolve_ref_image(refs_dir: Path | None, prompt_no: int):
    if refs_dir is None:
        return None
    exts = [".jpg", ".jpeg", ".png", ".webp"]
    for ext in exts:
        p = refs_dir / f"{prompt_no}{ext}"
        if p.exists() and p.is_file():
            return p
    return None


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
            url = page.url or ""
            # hỗ trợ cả URL locale: /fx/vi/tools/flow
            if re.search(r"labs\.google/fx(?:/[a-z]{2})?/tools/flow(?:/project)?", url):
                return page
    return None


def ensure_project_page(page):
    url = page.url or ""

    # Mặc định luôn vào /tools/flow (hỗ trợ locale /fx/vi/tools/flow)
    if not re.search(r"labs\.google/fx(?:/[a-z]{2})?/tools/flow(?:/project)?", url):
        try:
            page.goto("https://labs.google/fx/vi/tools/flow", wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.0)
        except Exception:
            pass

    # Bấm New project với nhiều fallback
    clicked = False
    selectors = [
        "button:has-text('New project')",
        "button:has-text('Dự án mới')",
        "button:has-text('Tạo dự án')",
        "a:has-text('New project')",
        "[role='button']:has-text('New project')",
        "button[id*='new' i]",
        "button[data-testid*='new' i]",
    ]
    for sel in selectors:
        if clicked:
            break
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                try:
                    loc.first.click(timeout=4000)
                except Exception:
                    loc.first.click(timeout=4000, force=True)
                time.sleep(1.2)
                clicked = True
        except Exception:
            pass

    # Fallback: thử click theo text regex tổng quát
    if not clicked:
        try:
            new_btn = page.locator("button,[role='button'],a,[role='link']").filter(
                has_text=re.compile(r"new\s*project|dự\s*án\s*mới|tạo\s*dự\s*án|new", re.I)
            )
            if new_btn.count() > 0:
                try:
                    new_btn.first.click(timeout=4000)
                except Exception:
                    new_btn.first.click(timeout=4000, force=True)
                time.sleep(1.2)
                clicked = True
        except Exception:
            pass

    # Không goto thẳng /project nữa.
    # Bắt buộc đi qua /tools/flow rồi click New project để UI đúng trạng thái.
    return page


def capture_startup_screenshot(page):
    try:
        out_dir = Path.home() / ".openclaw" / "workspace" / "flow-auto" / "debug"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"startup-flow-{int(time.time())}.png"
        page.screenshot(path=str(out), full_page=True)
        log_line(f"[flow] startup screenshot: {out}")
    except Exception as e:
        log_line(f"[flow] startup screenshot warning: {e}")


def _try_click_new_project(page):
    try:
        new_btn = page.locator("button,[role='button'],a,[role='link']").filter(
            has_text=re.compile(r"new\s*project|dự\s*án\s*mới|tạo\s*dự\s*án", re.I)
        )
        if new_btn.count() > 0:
            try:
                new_btn.first.click(timeout=3000)
            except Exception:
                new_btn.first.click(timeout=3000, force=True)
            time.sleep(1.2)
    except Exception:
        pass


def find_input_box(page):
    # Chờ editor sẵn sàng sau New project
    deadline = time.time() + 30
    retried_new_project = False
    selectors = [
        'div[role="textbox"][contenteditable="true"]',
        'div[contenteditable="true"]',
        'textarea',
        'input[type="text"]',
    ]

    while time.time() < deadline:
        for sel in selectors:
            try:
                boxes = page.locator(sel)
                count = boxes.count()
                for i in range(count - 1, -1, -1):
                    b = boxes.nth(i)
                    if b.is_visible():
                        return b
            except Exception:
                pass

        if not retried_new_project:
            _try_click_new_project(page)
            retried_new_project = True

        time.sleep(0.5)

    raise RuntimeError("Không tìm thấy ô nhập prompt")


def apply_aspect_ratio(page, ratio: str):
    ratio = (ratio or "").strip()
    # Chỉ hỗ trợ 2 mode chính
    if ratio not in {"16:9", "9:16"}:
        return

    # 1) Ưu tiên tab tỉ lệ trong panel (UI Flow mới)
    try:
        if ratio == "9:16":
            portrait = page.locator("button[id*='trigger-PORTRAIT'],button").filter(
                has_text=re.compile(r"9:16|crop_9_16", re.I)
            )
            if portrait.count() > 0:
                try:
                    portrait.first.click(timeout=3000)
                except Exception:
                    portrait.first.click(timeout=3000, force=True)
                time.sleep(0.35)
                return
        elif ratio == "16:9":
            landscape = page.locator("button[id*='trigger-LANDSCAPE'],button").filter(
                has_text=re.compile(r"16:9|crop_16_9", re.I)
            )
            if landscape.count() > 0:
                try:
                    landscape.first.click(timeout=3000)
                except Exception:
                    landscape.first.click(timeout=3000, force=True)
                time.sleep(0.35)
                return
    except Exception:
        pass

    # 2) Mở chip Video+ratio (button menu thứ 6) rồi chọn lại tab
    try:
        ratio_chip = page.locator("button[aria-haspopup='menu']").nth(5)
        try:
            ratio_chip.click(timeout=3000)
        except Exception:
            ratio_chip.click(timeout=3000, force=True)
        time.sleep(0.25)

        target = None
        if ratio == "9:16":
            target = page.locator("button[id*='trigger-PORTRAIT'],button").filter(has_text=re.compile(r"9:16|crop_9_16", re.I))
        elif ratio == "16:9":
            target = page.locator("button[id*='trigger-LANDSCAPE'],button").filter(has_text=re.compile(r"16:9|crop_16_9", re.I))

        if target and target.count() > 0:
            try:
                target.first.click(timeout=3000)
            except Exception:
                target.first.click(timeout=3000, force=True)
            time.sleep(0.35)
            return
    except Exception:
        pass

    # 3) Fallback cũ: dò theo text/icon
    try:
        ratio_btn = page.locator("button,[role='button'],[role='tab'],[role='option'],[role='menuitem']").filter(
            has_text=re.compile(rf"(^|\s){re.escape(ratio)}($|\s)|crop_{ratio.replace(':','_')}", re.I)
        )
        if ratio_btn.count() > 0:
            try:
                ratio_btn.first.click(timeout=3000)
            except Exception:
                ratio_btn.first.click(timeout=3000, force=True)
            time.sleep(0.35)
    except Exception:
        pass


def get_box_text(box):
    try:
        return (box.inner_text(timeout=1200) or "").strip()
    except Exception:
        return ""


def clear_prompt_box(page, box):
    # Prompt input rule v1.0.2:
    # - Exactly one clear pass: Ctrl+A -> Delete
    # - No multi-pass clear
    # - No JS fallback clear
    try:
        box.click(timeout=3000)
    except Exception:
        pass
    try:
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
    except Exception:
        pass
    time.sleep(0.12)


def _open_plus_menu(page, prompt_box=None):
    # Ưu tiên click đúng dấu cộng nằm cạnh ô prompt (tránh click nhầm dấu cộng khu khác)
    try:
        ok = page.evaluate(
            """
            () => {
              const visible = (el) => {
                if (!el) return false;
                const st = getComputedStyle(el);
                if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 8 && r.height > 8;
              };

              const boxes = Array.from(document.querySelectorAll('div[role="textbox"][contenteditable="true"], div[contenteditable="true"], textarea, input[type="text"]'))
                .filter(visible);
              if (!boxes.length) return false;

              const box = boxes[boxes.length - 1];
              const br = box.getBoundingClientRect();

              const btns = Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible);
              let best = null;
              let bestScore = 1e9;

              for (const b of btns) {
                const txt = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase();
                const isPlus = txt.includes('+') || txt.includes('add') || txt.includes('thêm') || txt.includes('upload');
                if (!isPlus) continue;

                const r = b.getBoundingClientRect();
                // bắt buộc ở bên trái ô prompt và gần theo trục dọc
                if (r.right > br.left + 40) continue;
                const dy = Math.abs((r.top + r.height / 2) - (br.top + br.height / 2));
                const dx = Math.abs(br.left - r.right);
                const score = dx + dy * 2;
                if (score < bestScore) {
                  bestScore = score;
                  best = b;
                }
              }

              if (!best) return false;
              best.click();
              return true;
            }
            """
        )
        if ok:
            time.sleep(0.4)
            return True
    except Exception:
        pass

    plus_selectors = [
        "button[aria-label*='Add' i]",
        "button[aria-label*='Thêm' i]",
        "button:has-text('add')",
        "button:has-text('+')",
        "[role='button'][aria-label*='add' i]",
    ]
    for sel in plus_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                try:
                    loc.first.click(timeout=2500)
                except Exception:
                    loc.first.click(timeout=2500, force=True)
                time.sleep(0.35)
                return True
        except Exception:
            pass

    return False


def _choose_uploaded_image_from_menu(page, image_path: Path):
    # Chọn đúng ảnh theo số thứ tự vừa upload (vd: 12.jpg -> chọn item có "12")
    stem = image_path.stem.strip()
    m = re.search(r"(\d+)", stem)
    number = m.group(1) if m else stem
    idx = int(number) if str(number).isdigit() else None

    targets = [image_path.name, stem, number]
    selectors = [
        "button,[role='button'],[role='option'],[role='menuitem'],div,span",
    ]

    # ưu tiên match theo text
    for text in targets:
        if not text:
            continue
        try:
            pat = re.compile(rf"(^|\b){re.escape(text)}(\b|$)", re.I)
            for sel in selectors:
                loc = page.locator(sel).filter(has_text=pat)
                if loc.count() > 0 and loc.first.is_visible():
                    try:
                        loc.first.click(timeout=3500)
                    except Exception:
                        loc.first.click(timeout=3500, force=True)
                    time.sleep(0.6)
                    return True
        except Exception:
            pass

    # fallback quan trọng: chọn thumbnail theo index số ảnh
    # ví dụ file 1.jpg -> chọn thumbnail #1, 2.jpg -> thumbnail #2
    try:
        thumbs = page.locator("img, [role='option'] img, button img, [role='gridcell'] img")
        c = thumbs.count()
        if c > 0:
            pick = 0
            if idx is not None and idx > 0:
                pick = min(idx - 1, c - 1)
            t = thumbs.nth(pick)
            try:
                t.click(timeout=3500)
            except Exception:
                t.click(timeout=3500, force=True)
            time.sleep(0.6)
            return True
    except Exception:
        pass

    return False


def upload_reference_image(page, image_path: Path, prompt_box=None):
    image_path = Path(image_path)
    if not image_path.exists():
        raise RuntimeError(f"Không thấy ảnh tham chiếu: {image_path}")

    # 1) mở menu dấu cộng bên trái ô prompt
    if not _open_plus_menu(page, prompt_box=prompt_box):
        raise RuntimeError("Không mở được menu dấu cộng để tải ảnh")

    # 2) chọn item upload image
    upload_item_selectors = [
        "button:has-text('Upload image')",
        "button:has-text('Tải hình ảnh lên')",
        "button:has-text('Tải ảnh lên')",
        "[role='menuitem']:has-text('Upload image')",
        "[role='menuitem']:has-text('Tải hình ảnh lên')",
        "[role='option']:has-text('Upload image')",
    ]
    clicked_upload = False
    for sel in upload_item_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                try:
                    loc.first.click(timeout=3000)
                except Exception:
                    loc.first.click(timeout=3000, force=True)
                clicked_upload = True
                time.sleep(0.3)
                break
        except Exception:
            pass

    if not clicked_upload:
        raise RuntimeError("Không bấm được mục 'Tải hình ảnh lên'")

    # 3) upload file
    file_set = False
    try:
        fi = page.locator("input[type='file']")
        if fi.count() > 0:
            fi.first.set_input_files(str(image_path))
            file_set = True
    except Exception:
        pass

    if not file_set:
        raise RuntimeError("Không upload được ảnh tham chiếu (không tìm thấy input file)")

    # chờ upload xong theo yêu cầu mới: 30 giây
    time.sleep(30.0)

    # 4) bắt buộc mở lại dấu cộng và chọn đúng ảnh vừa upload
    opened2 = False
    for _ in range(3):
        if _open_plus_menu(page, prompt_box=prompt_box):
            opened2 = True
            break
        time.sleep(0.6)

    if not opened2:
        raise RuntimeError("cannot open plus menu second time after upload")

    if not _choose_uploaded_image_from_menu(page, image_path):
        raise RuntimeError(f"cannot pick uploaded image by number: {image_path.stem}")

    # chờ attach ảnh vào prompt box ổn định
    time.sleep(1.0)


def find_create_button(page):
    # Cách 1: ưu tiên selector ổn định (aria/id/data-testid)
    stable_selectors = [
        "button[data-testid*='create' i]",
        "button[id*='create' i]",
        "button[aria-label*='create' i]",
        "button[aria-label*='generate' i]",
        "button[aria-label*='tạo' i]",
        # UI hiện tại thường hiển thị icon text + nhãn Tạo
        "button:has-text('arrow_forward'):has-text('Tạo')",
        "button:has-text('arrow_forward'):has-text('Create')",
    ]

    for sel in stable_selectors:
        try:
            loc = page.locator(sel)
            cnt = loc.count()
            for i in range(cnt - 1, -1, -1):
                btn = loc.nth(i)
                if btn.is_visible() and btn.is_enabled():
                    return btn
        except Exception:
            continue

    raise RuntimeError("Không tìm thấy nút Create/Tạo theo selector ổn định")


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

    log_line(f"[flow] total prompts: {total}")
    log_line(f"[flow] starting from prompt #{done + 1}")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        page = find_flow_page(browser)
        if not page:
            raise RuntimeError("Không tìm thấy tab Flow đang mở")

        page = ensure_project_page(page)
        page.bring_to_front()
        capture_startup_screenshot(page)

        needs_clear_before_insert = True

        refs_dir = args.refs_dir
        for idx in range(done, total):
            prompt = prompts[idx]
            prompt_no = idx + 1
            ok = False

            for attempt in range(1, args.max_retries + 2):
                try:
                    page.bring_to_front()
                    box = find_input_box(page)

                    if needs_clear_before_insert:
                        clear_prompt_box(page, box)
                        needs_clear_before_insert = False

                    # V2.0: map ảnh tham chiếu theo số thứ tự prompt: 1.jpg|1.png -> prompt 1
                    ref_img = resolve_ref_image(refs_dir, prompt_no)
                    if ref_img is not None:
                        upload_reference_image(page, ref_img, prompt_box=box)

                    time.sleep(random.uniform(args.pre_paste_min, args.pre_paste_max))

                    # Quy trình nhập prompt mới:
                    # 1) chạm vào ô prompt
                    # 2) gõ tốc độ vừa phải
                    # 3) chờ thêm rồi bấm Create
                    try:
                        box.click(timeout=3000)
                    except Exception:
                        pass
                    page.keyboard.type(prompt, delay=args.type_delay_ms)

                    # Bỏ chọn tỉ lệ theo yêu cầu: giữ nguyên tỉ lệ hiện tại trên UI
                    time.sleep(args.before_create_sec)
                    btn = find_create_button(page)
                    btn.click(timeout=5000)

                    time.sleep(2)
                    if has_failure(page):
                        raise RuntimeError("Flow báo lỗi sau khi bấm Create")

                    ok = True
                    break
                except (PWTimeout, Exception) as e:
                    needs_clear_before_insert = True
                    log_line(f"[flow] prompt #{prompt_no} attempt {attempt} error: {e}")
                    if attempt <= args.max_retries:
                        time.sleep(2)

            # Sau khi tạo thành công: clear 1 lần để chuẩn bị prompt mới kế tiếp
            if ok and prompt_no < total:
                try:
                    page.bring_to_front()
                    next_box = find_input_box(page)
                    clear_prompt_box(page, next_box)
                    needs_clear_before_insert = False
                except Exception as e:
                    log_line(f"[flow] clear-after-success prompt #{prompt_no} error: {e}")
                    needs_clear_before_insert = True

            if not ok:
                log_line(f"[flow] prompt #{prompt_no} failed after retries, skip and continue")
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
                log_line(f"[flow] progress: {prompt_no}/{total}")

            if prompt_no < total:
                time.sleep(args.between_prompts_sec)

        log_line("[flow] done all prompts")


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
    ap.add_argument("--before-create-sec", type=float, default=5.0)
    ap.add_argument("--type-delay-ms", type=float, default=12.0, help="Độ trễ mỗi ký tự khi gõ prompt")
    ap.add_argument("--between-prompts-sec", type=float, default=10.0)
    ap.add_argument("--aspect-ratio", default="9:16", help="Tỉ lệ video: 16:9 | 9:16")
    ap.add_argument("--start-from", type=int, default=None, help="1-based prompt index")
    ap.add_argument("--refs-dir", type=Path, default=None, help="Thư mục ảnh tham chiếu (1.jpg/1.png map prompt #1)")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
