#!/usr/bin/env python3
import argparse
import re
import time
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


def find_flow_page(browser):
    for ctx in browser.contexts:
        for page in ctx.pages:
            if "labs.google/fx/tools/flow/project/" in (page.url or ""):
                return page
    for ctx in browser.contexts:
        for page in ctx.pages:
            if "labs.google/fx/tools/flow" in (page.url or ""):
                return page
    return None


def collect_edit_links(page):
    hrefs = page.evaluate(
        """
        () => {
          const out = [];
          for (const a of document.querySelectorAll('a[href*="/edit/"]')) {
            const href = a.getAttribute('href') || '';
            if (href) out.push(href);
          }
          return out;
        }
        """
    )
    # dedupe, keep order
    seen = set()
    uniq = []
    for h in hrefs:
        if h in seen:
            continue
        seen.add(h)
        uniq.append(h)
    return uniq


def click_download(page):
    # direct button/menu
    btn = page.locator("button,[role='button'],a,[role='menuitem']").filter(
        has_text=re.compile(r"\bDownload\b", re.I)
    )
    if btn.count() > 0:
        try:
            btn.first.click(timeout=4000)
        except Exception:
            btn.first.click(timeout=4000, force=True)
        return True

    # fallback: open More options then click Download
    more = page.locator("button,[role='button']").filter(
        has_text=re.compile(r"(more_vert|More options|More)", re.I)
    )
    if more.count() > 0:
        try:
            more.first.click(timeout=3000)
        except Exception:
            more.first.click(timeout=3000, force=True)
        time.sleep(0.3)
        menu_dl = page.locator("button,[role='menuitem'],a,[role='option']").filter(
            has_text=re.compile(r"\bDownload\b", re.I)
        )
        if menu_dl.count() > 0:
            try:
                menu_dl.first.click(timeout=3000)
            except Exception:
                menu_dl.first.click(timeout=3000, force=True)
            return True

    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", default="http://127.0.0.1:18800")
    ap.add_argument("--max-items", type=int, default=100)
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        page = find_flow_page(browser)
        if not page:
            raise SystemExit("ERR: không tìm thấy tab Flow")

        page.bring_to_front()
        project_url = page.url

        # Ensure we're in gallery/videos panel if possible
        try:
            view_videos = page.locator("button,[role='button']").filter(has_text=re.compile(r"View videos", re.I))
            if view_videos.count() > 0 and view_videos.first.is_visible():
                view_videos.first.click(timeout=2500)
                time.sleep(0.6)
        except Exception:
            pass

        links = collect_edit_links(page)
        if not links:
            print("downloaded=0 found=0")
            return

        total = 0
        found = 0
        origin = "https://labs.google"

        for href in links:
            if total >= args.max_items:
                break
            found += 1
            url = urljoin(origin, href)

            sub = page.context.new_page()
            try:
                sub.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    sub.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                ok = click_download(sub)
                if ok:
                    total += 1
                    print(f"download_ok: {url}")
                else:
                    print(f"download_skip(no_button): {url}")
            except Exception as e:
                print(f"download_err: {url} :: {e}")
            finally:
                try:
                    sub.close()
                except Exception:
                    pass

        # restore project tab
        try:
            page.goto(project_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

        print(f"downloaded={total} found={found}")


if __name__ == "__main__":
    main()
