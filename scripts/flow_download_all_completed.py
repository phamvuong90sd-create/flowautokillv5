#!/usr/bin/env python3
import argparse
import re
import time

from playwright.sync_api import sync_playwright


def find_flow_page(browser):
    for ctx in browser.contexts:
        for page in ctx.pages:
            url = page.url or ""
            if re.search(r"labs\.google/fx(?:/[a-z]{2})?/tools/flow", url):
                return page
    return None


def click_first(locator):
    if locator.count() <= 0:
        return False
    try:
        locator.first.click(timeout=3000)
    except Exception:
        locator.first.click(timeout=3000, force=True)
    return True


def open_tile_menu(tile):
    # Ưu tiên nút 3 chấm trong tile hiện tại
    try:
        more = tile.locator("button,[role='button']").filter(
            has_text=re.compile(r"more_vert|more options|more", re.I)
        )
        if click_first(more):
            return True
    except Exception:
        pass

    # fallback toàn trang
    more = tile.page.locator("button,[role='button']").filter(
        has_text=re.compile(r"more_vert|more options|more", re.I)
    )
    return click_first(more)


def click_download_and_quality(page, quality="720p"):
    # click Download trong menu
    dl = page.locator("button,[role='menuitem'],[role='option'],div").filter(
        has_text=re.compile(r"\bdownload\b|tải\s*xuống", re.I)
    )
    if not click_first(dl):
        return False

    time.sleep(0.35)

    # chọn chất lượng nếu panel xuất hiện
    q = page.locator("button,[role='menuitem'],[role='option'],div").filter(
        has_text=re.compile(rf"\b{re.escape(quality)}\b", re.I)
    )
    if q.count() > 0:
        click_first(q)

    return True


def tile_signature(tile):
    try:
        txt = (tile.inner_text(timeout=1000) or "").strip().replace("\n", " ")
        return txt[:180]
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", default="http://127.0.0.1:18800")
    ap.add_argument("--max-items", type=int, default=100)
    ap.add_argument("--quality", default="720p")
    ap.add_argument("--max-scrolls", type=int, default=40)
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        page = find_flow_page(browser)
        if not page:
            raise SystemExit("ERR: không tìm thấy tab Flow")

        page.bring_to_front()
        time.sleep(0.5)

        # nếu có nút View videos thì vào trước
        vv = page.locator("button,[role='button']").filter(has_text=re.compile(r"view videos|xem video", re.I))
        if vv.count() > 0:
            click_first(vv)
            time.sleep(0.8)

        downloaded = 0
        seen = set()

        for _ in range(args.max_scrolls):
            # tìm tile đã hoàn thành
            tiles = page.locator("article,div[role='button'],div").filter(
                has_text=re.compile(r"completed|download|đã\s*hoàn\s*thành|tải\s*xuống", re.I)
            )
            count = tiles.count()

            for i in range(count):
                if downloaded >= args.max_items:
                    break
                tile = tiles.nth(i)
                try:
                    if not tile.is_visible():
                        continue
                except Exception:
                    continue

                sig = tile_signature(tile)
                if not sig or sig in seen:
                    continue

                try:
                    tile.hover(timeout=2000)
                except Exception:
                    pass

                ok = False
                if open_tile_menu(tile):
                    time.sleep(0.3)
                    ok = click_download_and_quality(page, args.quality)

                seen.add(sig)
                if ok:
                    downloaded += 1
                    print(f"download_ok: {downloaded} :: {sig[:80]}")
                else:
                    print(f"download_skip: {sig[:80]}")

                time.sleep(0.4)

            if downloaded >= args.max_items:
                break

            # kéo xuống để tìm video completed tiếp theo
            page.mouse.wheel(0, 2200)
            time.sleep(1.0)

        print(f"downloaded={downloaded} scanned={len(seen)}")


if __name__ == "__main__":
    main()
