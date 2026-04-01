#!/usr/bin/env python3
import argparse
import json
import sys
from playwright.sync_api import sync_playwright


def is_logged_in(page) -> bool:
    """
    Best-effort detection for Google account login state.
    """
    try:
        url = (page.url or "").lower()
        if "servicelogin" in url or "signin" in url:
            return False

        # strong login-required signals
        if page.locator("input[type='email']").count() > 0:
            return False
        if page.locator("input[type='password']").count() > 0:
            return False

        body = (page.locator("body").inner_text(timeout=2500) or "").lower()
        if "sign in" in body and "create account" in body:
            return False

        # account surfaces that usually appear when logged in
        if page.locator("a[href*='SignOutOptions']").count() > 0:
            return True
        if page.locator("a[href*='myaccount.google.com']").count() > 0:
            return True

        # fallback: if not on explicit login URL and no email/password form, treat as logged in
        return True
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", default="http://127.0.0.1:18800")
    ap.add_argument("--accounts-url", default="https://accounts.google.com")
    ap.add_argument("--flow-url", default="https://labs.google/fx/tools/flow")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        if not browser.contexts:
            out = {"ok": False, "reason": "no_browser_context"}
            print(json.dumps(out) if args.json else "ok=False reason=no_browser_context")
            return 12

        context = browser.contexts[0]
        page = context.new_page()
        page.goto(args.accounts_url, wait_until="domcontentloaded", timeout=45000)

        logged_in = is_logged_in(page)
        if logged_in:
            # Already logged in -> no need to run login flow; just continue to Flow
            page.goto(args.flow_url, wait_until="domcontentloaded", timeout=45000)
            out = {"ok": True, "reason": "already_logged_in", "action": "skip_login_open_flow"}
            print(json.dumps(out) if args.json else "ok=True reason=already_logged_in")
            return 0

        # Not logged in: keep account page open for manual login
        out = {"ok": False, "reason": "login_required", "action": "manual_login_needed"}
        print(json.dumps(out) if args.json else "ok=False reason=login_required")
        return 20


if __name__ == "__main__":
    sys.exit(main())
