import argparse
import json
import random
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROMPT_INPUT_RULE_VERSION = "v1.1.2"


def load_prompts(path: Path):
    text = path.read_text(encoding="utf-8")
    return [p.strip().replace("\n", " ") for p in text.split("\n\n") if p.strip()]


def normalize_prompt_tail(prompt: str) -> str:
    """
    Chuẩn hóa cuối prompt: kết thúc đúng một dấu chấm + một dấu cách (". ").
    """
    p = (prompt or "").rstrip()
    if not p:
        return ". "

    while p and p[-1] in ".!?;:،。！？ ":
        p = p[:-1]

    return p + ". "


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

    # Mặc định luôn vào /tools/flow
    if "labs.google/fx/tools/flow" not in url:
        try:
            page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.0)
        except Exception:
            pass

    # Sau khi vào /tools/flow thì bấm New project (EN/VI)
    try:
        new_btn = page.locator("button,[role='button'],a,[role='link']").filter(
            has_text=re.compile(r"new\s*project|dự\s*án\s*mới|tạo\s*dự\s*án", re.I)
        )
        if new_btn.count() > 0:
            try:
                new_btn.first.click(timeout=5000)
            except Exception:
                new_btn.first.click(timeout=5000, force=True)
            time.sleep(1.8)
    except Exception:
        pass

    return page


def capture_startup_screenshot(page):
    try:
        out_dir = Path.home() / ".openclaw" / "workspace" / "flow-auto" / "debug"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"startup-flow-{int(time.time())}.png"
        page.screenshot(path=str(out), full_page=True)
        print(f"[flow] startup screenshot: {out}")
    except Exception as e:
        print(f"[flow] cảnh báo: không chụp được ảnh startup: {e}")


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
    deadline = time.time() + 25
    retried_new_project = False
    while time.time() < deadline:
        boxes = page.locator('div[role="textbox"][contenteditable="true"]')
        count = boxes.count()
        for i in range(count - 1, -1, -1):
            b = boxes.nth(i)
            if b.is_visible():
                return b

        if not retried_new_project:
            _try_click_new_project(page)
            retried_new_project = True

        time.sleep(0.5)

    raise RuntimeError("Could not find prompt input box")


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
    # Prompt input rule v1.1.2:
    # - Exactly one clear pass: Ctrl+A -> Delete
    # - No multi-pass clear
    # - No JS clear fallback
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


def type_prompt_text(box, text: str, delay_ms: float = 35.0):
    """
    Nhập prompt bằng thao tác gõ phím (thay vì insert_text).
    """
    d = max(0.0, float(delay_ms))
    try:
        box.click(timeout=3000)
    except Exception:
        pass

    try:
        box.type(text, delay=d)
    except Exception:
        # fallback để không làm fail job nếu UI chặn type
        box.page.keyboard.insert_text(text)


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


def click_model_button_next_to_create(page):
    """
    Click nút chọn model nằm cạnh nút Create/Tạo đúng 1 lần.
    Best-effort: nếu không tìm được thì bỏ qua để không làm dừng batch.
    """
    try:
        create_btn = find_create_button(page)

        # Ưu tiên nút ngay trước Create trong cùng hàng/parent
        sibling_selectors = [
            "xpath=preceding-sibling::button[1]",
            "xpath=preceding-sibling::*[@role='button'][1]",
        ]
        for sel in sibling_selectors:
            try:
                sib = create_btn.locator(sel)
                if sib.count() > 0 and sib.first.is_visible() and sib.first.is_enabled():
                    sib.first.click(timeout=3000)
                    time.sleep(0.2)
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                    return True
            except Exception:
                continue

        # Fallback: button gần Create có aria-haspopup='menu' (thường là model selector)
        try:
            candidates = page.locator("button[aria-haspopup='menu']")
            n = candidates.count()
            for i in range(n - 1, -1, -1):
                b = candidates.nth(i)
                if b.is_visible() and b.is_enabled():
                    try:
                        b.click(timeout=2000)
                        time.sleep(0.2)
                        try:
                            page.keyboard.press("Escape")
                        except Exception:
                            pass
                        return True
                    except Exception:
                        continue
        except Exception:
            pass
    except Exception:
        pass

    return False


def has_failure(page):
    # Conservative check: only treat explicit global Oops banner as failure.
    # Per-item "Failed/Retry" cards may exist from older jobs and should not stop the loop.
    body = page.locator("body")
    txt = body.inner_text(timeout=2000)
    return "Oops, something went wrong" in txt


def wait_until_video_ready_for_next_prompt(page, timeout_sec=900, poll_sec=3):
    """
    Wait until Flow finishes current generation and UI is ready for next prompt.

    Heuristic:
    - Preferred: after click Create/Tạo, button goes disabled then enabled again.
    - Fallback: some UI states keep Create visible+enabled almost all the time; if it stays
      enabled long enough with no global error, treat as ready to avoid getting stuck.
    """
    deadline = time.time() + timeout_sec
    saw_disabled = False
    first_enabled_ts = None

    while time.time() < deadline:
        try:
            btn = find_create_button(page)
            enabled = btn.is_enabled()
        except Exception:
            enabled = False

        if not enabled:
            saw_disabled = True
            first_enabled_ts = None
        else:
            # Normal path: saw disabled then enabled again
            if saw_disabled:
                return True

            # Fallback path: never observed disabled; avoid hang forever
            if first_enabled_ts is None:
                first_enabled_ts = time.time()
            elif time.time() - first_enabled_ts >= 12:
                return True

        if has_failure(page):
            raise RuntimeError("Flow báo lỗi trong lúc chờ hoàn thành video")

        time.sleep(poll_sec)

    return False


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
        capture_startup_screenshot(page)

        needs_clear_before_insert = True
        model_selected_once = False

        for idx in range(done, total):
            prompt = prompts[idx]
            prompt_no = idx + 1
            ok = False
            prompt_to_send = normalize_prompt_tail(prompt)

            for attempt in range(1, args.max_retries + 2):
                try:
                    page.bring_to_front()
                    box = find_input_box(page)

                    if needs_clear_before_insert:
                        clear_prompt_box(page, box)
                        needs_clear_before_insert = False

                    time.sleep(random.uniform(args.pre_paste_min, args.pre_paste_max))
                    type_prompt_text(box, prompt_to_send, delay_ms=args.typing_delay_ms)

                    # Chỉ chọn model 1 lần ở prompt đầu tiên (giảm rủi ro bị anti-bot)
                    if not model_selected_once:
                        model_clicked = click_model_button_next_to_create(page)
                        if model_clicked:
                            model_selected_once = True
                            print(f"[flow] prompt #{prompt_no}: clicked model selector once (first time only)")
                        else:
                            print(f"[flow] prompt #{prompt_no}: model selector not found, continue")

                    # Chờ theo cấu hình rồi mới bấm Create
                    time.sleep(args.before_create_sec)
                    btn = find_create_button(page)
                    btn.click(timeout=5000)

                    time.sleep(2)
                    if has_failure(page):
                        raise RuntimeError("Flow báo lỗi sau khi bấm Create")

                    # Chờ video hoàn thành rồi mới chuyển prompt tiếp theo
                    ready = wait_until_video_ready_for_next_prompt(
                        page,
                        timeout_sec=args.complete_timeout_sec,
                        poll_sec=args.complete_poll_sec,
                    )
                    if not ready:
                        raise RuntimeError("Timeout chờ video hoàn thành để chạy prompt tiếp theo")

                    ok = True
                    break
                except (PWTimeout, Exception) as e:
                    needs_clear_before_insert = True
                    print(f"[flow] prompt #{prompt_no} attempt {attempt} error: {e}")
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
                    print(f"[flow] clear sau thành công prompt #{prompt_no} lỗi: {e}")
                    needs_clear_before_insert = True

            if not ok:
                print(f"[flow] prompt #{prompt_no} failed after retries, skipping")
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

        print("[flow] all prompts finished")


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
    ap.add_argument("--typing-delay-ms", type=float, default=35.0,
                    help="Độ trễ mỗi ký tự khi gõ prompt")
    ap.add_argument("--before-create-sec", type=float, default=3.0)
    ap.add_argument("--between-prompts-sec", type=float, default=10.0)
    ap.add_argument("--complete-timeout-sec", type=float, default=900.0,
                    help="Timeout chờ 1 video hoàn thành trước khi chạy prompt tiếp theo")
    ap.add_argument("--complete-poll-sec", type=float, default=3.0,
                    help="Chu kỳ kiểm tra trạng thái hoàn thành video")
    ap.add_argument("--aspect-ratio", default="9:16", help="Tỉ lệ video: 16:9 | 9:16")
    ap.add_argument("--start-from", type=int, default=None, help="1-based prompt index")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
