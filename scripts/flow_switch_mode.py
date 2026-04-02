#!/usr/bin/env python3
import argparse
import re
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


UI_MAP = {
    "video": "button[id*='trigger-VIDEO']",
    "thanh_phan": "button[id*='trigger-VIDEO_REFERENCES']",
    "ratio_16_9": "button[id*='trigger-LANDSCAPE']",
    "ratio_9_16": "button[id*='trigger-PORTRAIT']",
    "x1": "button[id*='trigger-1']",
}


def find_flow_page(browser):
    for ctx in browser.contexts:
        for page in ctx.pages:
            url = page.url or ""
            if re.search(r"labs\.google/fx(?:/[a-z]{2})?/tools/flow", url):
                return page
    return None


def click_first(locator, timeout=3000):
    if locator.count() <= 0:
        return False
    try:
        locator.first.click(timeout=timeout)
    except Exception:
        locator.first.click(timeout=timeout, force=True)
    return True


def ensure_project_page(page):
    url = page.url or ""
    if not re.search(r"labs\.google/fx(?:/[a-z]{2})?/tools/flow", url):
        page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)

    # New project EN/VI
    new_btn = page.locator("button,[role='button'],a,[role='link']").filter(
        has_text=re.compile(r"new\s*project|dự\s*án\s*mới|tạo\s*dự\s*án", re.I)
    )
    if new_btn.count() > 0:
        click_first(new_btn, timeout=5000)
        time.sleep(1.2)


def ensure_video_mode(page):
    # Nếu đang ở chế độ ảnh thì chuyển sang video trước
    try:
        video_tab = page.locator(UI_MAP["video"])
        if video_tab.count() > 0:
            click_first(video_tab, timeout=3000)
            time.sleep(0.35)
            return
    except Exception:
        pass


def apply_profile_defaults(page, mode="16:9"):
    # Mapping cố định: Video, Thành phần, tỉ lệ, x1
    video = page.locator(UI_MAP["video"])
    if video.count() > 0:
        click_first(video, timeout=3000)
        time.sleep(0.2)

    thanh_phan = page.locator(UI_MAP["thanh_phan"])
    if thanh_phan.count() > 0:
        click_first(thanh_phan, timeout=3000)
        time.sleep(0.2)

    target_ratio = UI_MAP["ratio_16_9"] if mode == "16:9" else UI_MAP["ratio_9_16"]
    ratio_btn = page.locator(target_ratio)
    if ratio_btn.count() > 0:
        click_first(ratio_btn, timeout=3000)
        time.sleep(0.2)

    x1 = page.locator(UI_MAP["x1"])
    if x1.count() > 0:
        click_first(x1, timeout=3000)
        time.sleep(0.2)


def detect_mode(page):
    # Ưu tiên đọc từ chip composer: "Video crop_16_9 x1" / "Video crop_9_16 x1"
    try:
        chip = page.locator("button,[role='button']").filter(has_text=re.compile(r"video\s+crop_(16_9|9_16)", re.I))
        if chip.count() > 0:
            txt = (chip.first.inner_text(timeout=600) or "").lower()
            if "16_9" in txt or "16:9" in txt:
                return "16:9"
            if "9_16" in txt or "9:16" in txt:
                return "9:16"
    except Exception:
        pass

    # fallback đọc text chip ratio
    mode_btn = page.locator("button,[role='button']").filter(
        has_text=re.compile(r"crop_9_16|crop_16_9|9:16|16:9", re.I)
    )
    if mode_btn.count() <= 0:
        return "unknown"

    txt = (mode_btn.first.inner_text(timeout=800) or "").lower()
    if "9_16" in txt or "9:16" in txt:
        return "9:16"
    if "16_9" in txt or "16:9" in txt:
        return "16:9"
    return "unknown"


def switch_mode(page, target_mode):
    # Mapping cứng theo id ổn định (Flow hiện tại)
    trigger_key = "LANDSCAPE" if target_mode == "16:9" else "PORTRAIT"

    # 1) thử bấm trực tiếp tab tỉ lệ
    direct = page.locator(f"button[id*='trigger-{trigger_key}']")
    if direct.count() > 0:
        click_first(direct, timeout=4000)
        time.sleep(0.4)
        return

    # 2) mở chip composer "Video crop_*" trước rồi bấm trigger
    chip = page.locator("button,[role='button']").filter(has_text=re.compile(r"video\s+crop_(16_9|9_16)", re.I))
    opened = False
    if chip.count() > 0:
        opened = click_first(chip, timeout=4000)

    if not opened:
        # fallback mềm nếu UI đổi chữ
        mode_btn = page.locator("button,[role='button']").filter(
            has_text=re.compile(r"crop_9_16|crop_16_9|9:16|16:9", re.I)
        )
        if mode_btn.count() > 0:
            opened = click_first(mode_btn, timeout=4000)

    if not opened:
        raise RuntimeError("Không tìm thấy nút chế độ cạnh nút Tạo")

    time.sleep(0.3)

    target = page.locator(f"button[id*='trigger-{trigger_key}']")
    if target.count() <= 0:
        raise RuntimeError(f"Không tìm thấy lựa chọn chế độ {target_mode}")

    click_first(target, timeout=4000)
    time.sleep(0.5)


def shot(page, name):
    out_dir = Path.home() / ".openclaw" / "workspace" / "flow-auto" / "debug"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{name}-{int(time.time())}.png"
    page.screenshot(path=str(p), full_page=True)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", default="http://127.0.0.1:18800")
    ap.add_argument("--mode", default="9:16", choices=["9:16", "16:9"])
    ap.add_argument("--exit-page", action="store_true", default=True, help="Đóng tab Flow sau khi đổi mode (mặc định bật)")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        page = find_flow_page(browser)
        if not page:
            raise RuntimeError("Không tìm thấy tab Flow đang mở")

        page.bring_to_front()
        ensure_project_page(page)
        ensure_video_mode(page)
        # baseline mặc định: Video + Thành phần + 16:9 + x1
        apply_profile_defaults(page, mode="16:9")

        before = detect_mode(page)
        before_shot = shot(page, "mode-before")

        if before != args.mode:
            switch_mode(page, args.mode)

        after = detect_mode(page)
        after_shot = shot(page, "mode-after")

        if args.exit_page:
            # đóng tab hiện tại
            try:
                page.close()
            except Exception:
                pass

            # thoát luôn browser debug để đúng yêu cầu "thoát trình duyệt"
            try:
                subprocess.run(["pkill", "-f", "remote-debugging-port=18800"], check=False)
            except Exception:
                pass

        print(f"mode_before={before}")
        print(f"mode_after={after}")
        print(f"screenshot_before={before_shot}")
        print(f"screenshot_after={after_shot}")
        print("mode_switch_done=1")


if __name__ == "__main__":
    main()
