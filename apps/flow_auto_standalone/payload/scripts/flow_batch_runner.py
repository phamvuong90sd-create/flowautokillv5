import argparse
import subprocess
import sys
import json
import random
import re
import sys
import time
from datetime import datetime
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


def resolve_first_ref_image(refs_dir: Path | None):
    if refs_dir is None:
        return None
    exts = [".jpg", ".jpeg", ".png", ".webp"]
    files = []
    for ext in exts:
        files.extend(sorted(refs_dir.glob(f"*{ext}")))
    return files[0] if files else None


def set_upload_file_input(page, image_path: Path):
    # set file vào input[type=file] đúng dialog hiện tại, ưu tiên input mới nhất
    wanted = image_path.name.lower()
    try:
        inputs = page.locator("input[type='file']")
        c = inputs.count()
        if c <= 0:
            return False

        # thử từ input cuối về đầu (thường input mới mở nằm cuối DOM)
        for i in range(c - 1, -1, -1):
            try:
                ip = inputs.nth(i)
                ip.set_input_files(str(image_path))
                time.sleep(0.2)

                # verify input đang giữ đúng filename cần upload
                ok = False
                try:
                    v = (ip.input_value(timeout=1200) or "").lower()
                    if wanted in v:
                        ok = True
                except Exception:
                    pass

                if not ok:
                    try:
                        names = ip.evaluate("el => Array.from(el.files || []).map(f => f.name)")
                        if isinstance(names, list) and any(str(n).lower() == wanted for n in names):
                            ok = True
                    except Exception:
                        pass

                if ok:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def prompt_file_prefix(prompt: str, prompt_no: int):
    words = re.findall(r"[A-Za-z0-9À-ỹ]+", str(prompt or ""))[:6]
    base = "_".join(words) if words else f"prompt_{prompt_no}"
    return f"{prompt_no:03d}_{base}"


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


MODEL_LABELS = {
    "default": "Veo 3.1 - Fast",
    "veo3_lite": "Veo 3.1 - Lite",
    "veo3_fast": "Veo 3.1 - Fast",
    "veo3_quality": "Veo 3.1 - Quality",
    "nano_banana_pro": "Nano Banana Pro",
    "nano_banana2": "Nano Banana 2",
    "nano_banana": "Nano Banana 2",
    "imagen4": "Imagen 4",
}


def apply_task_mode(page, task_mode: str):
    task_mode = (task_mode or "createvideo").strip().lower()
    want = "image" if task_mode == "createimage" else "video"
    want_icon = "image" if want == "image" else "videocam"

    try:
        ok = page.evaluate(
            """
            async ({want, wantIcon}) => {
              const sleep = (ms) => new Promise(r => setTimeout(r, ms));
              const xpath = (xp) => document.evaluate(xp, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
              const visible = (el) => {
                if (!el) return false;
                const st = getComputedStyle(el);
                if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 12 && r.height > 12;
              };
              const clickLikeExtension = (el) => {
                if (!el || el.getAttribute('data-state') === 'active') return false;
                const r = el.getBoundingClientRect();
                const x = r.left + r.width / 2, y = r.top + r.height / 2;
                el.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true,cancelable:true,clientX:x,clientY:y,pointerId:1,pointerType:'mouse',isPrimary:true,button:0,buttons:1}));
                el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true,cancelable:true,clientX:x,clientY:y,button:0,buttons:1}));
                el.dispatchEvent(new PointerEvent('pointerup', {bubbles:true,cancelable:true,clientX:x,clientY:y,pointerId:1,pointerType:'mouse',isPrimary:true,button:0,buttons:0}));
                el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true,cancelable:true,clientX:x,clientY:y,button:0,buttons:0}));
                el.dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true,clientX:x,clientY:y,button:0}));
                return true;
              };
              // Extension er(): Step 1 open main control panel first.
              let openMenu = document.querySelector('[role="menu"][data-state="open"]');
              if (!openMenu) {
                const trigger = xpath("//button[@aria-haspopup='menu' and .//div[@data-type='button-overlay'] and text()[normalize-space() != '']]")
                  || Array.from(document.querySelectorAll("button[aria-haspopup='menu']")).filter(visible).find(b => b.querySelector('div[data-type="button-overlay"]'));
                if (trigger) { clickLikeExtension(trigger); await sleep(700); }
                openMenu = document.querySelector('[role="menu"][data-state="open"]');
              }
              if (!openMenu) return false;

              // Extension er(): Step 2 select output type by exact tab/icon inside the settings menu.
              const xp = `//button[@role='tab' and contains(@class,'flow_tab_slider_trigger') and .//i[normalize-space(text())='${wantIcon}']]`;
              const direct = xpath(xp);
              if (direct) { clickLikeExtension(direct); await sleep(500); return true; }
              const labels = want === 'image' ? ['image','photo','ảnh','hình ảnh','tạo ảnh','create image'] : ['video','tạo video','create video'];
              const bad = ['upload','tải lên','add image','thêm ảnh','reference','ảnh ref'];
              const nodes = Array.from(document.querySelectorAll("button[role='tab'],[role='tab'],button,[role='button']")).filter(visible);
              let best = null, bestScore = -999;
              for (const b of nodes) {
                const icon = (b.querySelector('i')?.textContent || '').trim().toLowerCase();
                const txt = ((b.innerText||'')+' '+(b.getAttribute('aria-label')||'')+' '+(b.getAttribute('title')||'')).toLowerCase();
                let score = 0;
                if (b.getAttribute('role') === 'tab') score += 1000;
                if (icon === wantIcon) score += 800;
                if (labels.some(x => txt.includes(x))) score += 500;
                if (bad.some(x => txt.includes(x))) score -= 1800;
                if (score > bestScore) { bestScore = score; best = b; }
              }
              if (!best || bestScore < 400) return false;
              clickLikeExtension(best); await sleep(450); return true;
            }
            """,
            {"want": want, "wantIcon": want_icon},
        )
        if ok:
            time.sleep(0.45)
            return True
    except Exception:
        pass
    return False


def apply_video_sub_mode(page, sub_mode: str):
    mode = (sub_mode or "frames").strip().lower()
    want_icon = "chrome_extension" if mode == "ingredients" else "crop_free"

    try:
        ok = page.evaluate(
            """
            (wantIcon) => {
              const visible = (el) => {
                if (!el) return false;
                const st = getComputedStyle(el);
                if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 8 && r.height > 8;
              };
              const tabs = Array.from(document.querySelectorAll("button[role='tab'],button,[role='button']")).filter(visible);
              for (const b of tabs) {
                const icon = (b.querySelector('i')?.textContent || '').trim();
                if (icon === wantIcon) {
                  b.click();
                  return true;
                }
              }
              return false;
            }
            """,
            want_icon,
        )
        if ok:
            time.sleep(0.2)
            return True
    except Exception:
        pass

    return False


def apply_output_count(page, count: str):
    c = str(count or "1").strip()
    if not c.isdigit():
        return False
    target = f"x{c}"

    try:
        btn = page.locator("button[role='tab'],button").filter(has_text=re.compile(rf"^{re.escape(target)}$", re.I))
        if btn.count() > 0:
            try:
                btn.first.click(timeout=2500)
            except Exception:
                btn.first.click(timeout=2500, force=True)
            time.sleep(0.2)
            return True
    except Exception:
        pass
    return False


def apply_model(page, model_key: str):
    key = (model_key or "default").strip().lower()
    if key == "custom":
        return True
    label = MODEL_LABELS.get(key, MODEL_LABELS["default"])

    try:
        # mở dropdown model bên trong settings panel giống extension
        opened = page.evaluate("""
        () => {
          const visible = (el) => {
            if (!el) return false;
            const st = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 8 && r.height > 8;
          };
          const menu = document.querySelector('div[role="menu"][data-state="open"], [role="menu"][data-state="open"]');
          const scope = menu || document;
          const triggers = Array.from(scope.querySelectorAll("button[aria-haspopup='menu']")).filter(visible);
          const trigger = triggers.find(b => b.querySelector('div[data-type="button-overlay"]')) || triggers[triggers.length - 1];
          if (!trigger) return false;
          trigger.click();
          return true;
        }
        """)
        if opened:
            time.sleep(0.35)

        opt = page.locator("[role='menuitem'],button,[role='option']").filter(has_text=re.compile(re.escape(label), re.I))
        if opt.count() > 0:
            try:
                opt.first.click(timeout=2500)
            except Exception:
                opt.first.click(timeout=2500, force=True)
            time.sleep(0.25)
            return True
    except Exception:
        pass

    return False


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


def apply_flow_settings(page, args):
    task_mode = (args.task_mode or "createvideo").strip().lower()
    model_key = (args.flow_model or "default").strip().lower()
    if task_mode == "createimage" and model_key == "default":
        model_key = "nano_banana_pro"
    elif task_mode == "createvideo" and model_key == "default":
        model_key = "veo3_fast"

    payload = {
        "taskMode": task_mode,
        "model": model_key,
        "aspectRatio": args.flow_aspect_ratio,
        "count": str(args.flow_count or "1"),
        "videoSubMode": args.video_sub_mode,
    }
    try:
        ok = page.evaluate(
            """
            async (cfg) => {
              const p = (ms) => new Promise(r => setTimeout(r, ms));
              const v = (xp) => document.evaluate(xp, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
              const visible = (el) => {
                if (!el) return false;
                const st = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 8 && r.height > 8;
              };
              const clickExt = (el) => {
                if (!el) return false;
                if (el.getAttribute('data-state') === 'active') return false;
                const r = el.getBoundingClientRect();
                const x = r.left + r.width / 2, y = r.top + r.height / 2;
                const base = {bubbles:true,cancelable:true,view:window,clientX:x,clientY:y,screenX:window.screenX+x,screenY:window.screenY+y,button:0};
                el.dispatchEvent(new PointerEvent('pointerdown', {...base,isPrimary:true,buttons:1,pointerId:1,pointerType:'mouse'}));
                el.dispatchEvent(new MouseEvent('mousedown', {...base,buttons:1}));
                el.dispatchEvent(new PointerEvent('pointerup', {...base,isPrimary:true,buttons:0,pointerId:1,pointerType:'mouse'}));
                el.dispatchEvent(new MouseEvent('mouseup', {...base,buttons:0}));
                el.dispatchEvent(new MouseEvent('click', base));
                return true;
              };
              const closeMenus = () => document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true,cancelable:true,composed:true}));
              const models = {
                default:'Veo 3.1 - Fast', veo3_lite:'Veo 3.1 - Lite', veo3_fast:'Veo 3.1 - Fast', veo3_quality:'Veo 3.1 - Quality',
                nano_banana_pro:'Nano Banana Pro', nano_banana2:'Nano Banana 2', nano_banana:'Nano Banana 2', imagen4:'Imagen 4'
              };
              const isImage = cfg.taskMode === 'createimage';
              const typeIcon = isImage ? 'image' : 'videocam';

              // Extension er(): open main control panel.
              let panel = document.querySelector('[role="menu"][data-state="open"]');
              if (!panel) {
                const trigger = v("//button[@aria-haspopup='menu' and .//div[@data-type='button-overlay'] and text()[normalize-space() != '']]");
                if (!trigger) return {ok:false, step:'main_trigger_missing'};
                clickExt(trigger); await p(700);
                panel = document.querySelector('[role="menu"][data-state="open"]');
              }
              if (!panel) return {ok:false, step:'panel_missing'};

              // Step 2: output type image/video exact extension XPath.
              const typeTab = v(`//button[@role='tab' and contains(@class,'flow_tab_slider_trigger') and .//i[normalize-space(text())='${typeIcon}']]`);
              if (!typeTab) return {ok:false, step:'type_tab_missing', icon:typeIcon};
              clickExt(typeTab); await p(500);

              // Step 3: video sub-mode only for video.
              if (!isImage) {
                const subIcon = cfg.videoSubMode === 'ingredients' ? 'chrome_extension' : 'crop_free';
                const subTab = v(`//button[@role='tab' and contains(@class,'flow_tab_slider_trigger') and .//i[normalize-space(text())='${subIcon}']]`);
                if (subTab) { clickExt(subTab); await p(300); }
              }

              // Step 4: aspect ratio (same map as extension).
              const ratioMap = {landscape:'crop_16_9','16:9':'crop_16_9',landscape_4_3:'crop_landscape',square:'crop_square',portrait_3_4:'crop_portrait',portrait:'crop_9_16','9:16':'crop_9_16'};
              const ratioIcon = ratioMap[cfg.aspectRatio] || 'crop_16_9';
              const ratioTab = v(`//button[@role='tab' and contains(@class,'flow_tab_slider_trigger') and .//i[normalize-space(text())='${ratioIcon}']]`);
              if (ratioTab) { clickExt(ratioTab); await p(300); }

              // Step 5: count.
              const countTab = v(`//button[@role='tab' and contains(@class,'flow_tab_slider_trigger') and normalize-space(text())='x${cfg.count}']`);
              if (countTab) { clickExt(countTab); await p(300); }

              // Step 6: model dropdown inside control panel.
              if (cfg.model !== 'custom') {
                const label = models[cfg.model] || (isImage ? 'Nano Banana Pro' : 'Veo 3.1 - Fast');
                const modelTrigger = v("//div[@role='menu' and @data-state='open']//button[@aria-haspopup='menu' and .//div[@data-type='button-overlay']]");
                if (modelTrigger) {
                  clickExt(modelTrigger); await p(550);
                  const modelBtn = v(`//div[@role='menuitem']//button[.//span[contains(normalize-space(text()),'${label}')]]`)
                    || Array.from(document.querySelectorAll('[role="menuitem"] button, button')).filter(visible).find(b => (b.innerText||'').includes(label));
                  if (modelBtn) { modelBtn.click(); await p(450); }
                }
              }

              const isActiveType = () => {
                const tab = v(`//button[@role='tab' and contains(@class,'flow_tab_slider_trigger') and .//i[normalize-space(text())='${typeIcon}']]`);
                if (!tab) return false;
                const state = (tab.getAttribute('data-state') || tab.getAttribute('aria-selected') || '').toLowerCase();
                const cls = (tab.className || '').toString().toLowerCase();
                return state === 'active' || state === 'true' || cls.includes('active');
              };
              const ensureType = async () => {
                for (let k = 0; k < 4; k++) {
                  let tab = v(`//button[@role='tab' and contains(@class,'flow_tab_slider_trigger') and .//i[normalize-space(text())='${typeIcon}']]`);
                  if (!tab) {
                    let trigger = v("//button[@aria-haspopup='menu' and .//div[@data-type='button-overlay'] and text()[normalize-space() != '']]");
                    if (trigger) { clickExt(trigger); await p(500); }
                    tab = v(`//button[@role='tab' and contains(@class,'flow_tab_slider_trigger') and .//i[normalize-space(text())='${typeIcon}']]`);
                  }
                  if (!tab) continue;
                  if (isActiveType()) return true;
                  clickExt(tab); await p(550);
                  if (isActiveType()) return true;
                }
                return isActiveType();
              };

              // Re-apply + verify output type after model selection to prevent Flow from snapping back.
              const typeOk = await ensureType();
              closeMenus(); await p(500);
              return {ok:typeOk, step:typeOk ? 'done' : 'type_not_active'};
            }
            """,
            payload,
        )
        if ok and ok.get("ok"):
            log_line(f"[flow] settings applied: {payload}")
            return True
        log_line(f"[flow] settings apply failed/fallback: {ok}")
    except Exception as e:
        log_line(f"[flow] settings apply exception/fallback: {e}")

    # Fallback old per-setting path if Flow UI changed.
    apply_task_mode(page, task_mode)
    apply_model(page, model_key)
    apply_task_mode(page, task_mode)
    if task_mode == "createvideo":
        apply_video_sub_mode(page, args.video_sub_mode)
    apply_aspect_ratio(page, args.flow_aspect_ratio)
    apply_output_count(page, args.flow_count)
    close_open_menus(page)
    return False


def get_box_text(box):
    try:
        return (box.inner_text(timeout=1200) or "").strip()
    except Exception:
        return ""


def clear_attached_references(page):
    # Extension-style pre-flight cleanup: click close button for attached references/chips if present.
    try:
        page.evaluate(
            """
            () => {
              const visible = (el) => {
                if (!el) return false;
                const st = getComputedStyle(el);
                if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 8 && r.height > 8;
              };
              const btns = Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible);
              for (const b of btns) {
                const icon = (b.querySelector('i')?.textContent || '').trim().toLowerCase();
                const txt = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('title') || '')).toLowerCase();
                if (icon === 'close' || txt.includes('remove') || txt.includes('xóa') || txt.includes('clear')) {
                  // chỉ click close gần prompt/reference area, tránh đóng browser/dialog lớn
                  const r = b.getBoundingClientRect();
                  if (r.top > window.innerHeight * 0.45) {
                    try { b.click(); } catch {}
                  }
                }
              }
            }
            """
        )
    except Exception:
        pass
    time.sleep(0.25)


def close_open_menus(page):
    try:
        page.keyboard.press("Escape")
        time.sleep(0.15)
        page.keyboard.press("Escape")
    except Exception:
        pass
    time.sleep(0.2)


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


def type_prompt_with_verify(page, prompt: str, type_delay_ms: float = 12.0, retries: int = 3):
    prompt = (prompt or "").strip()
    if not prompt:
        return False

    for _ in range(retries):
        try:
            # đóng menu/popover còn mở trước khi nhập
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

            box = find_input_box(page)
            try:
                box.click(timeout=3000)
            except Exception:
                box.click(timeout=3000, force=True)

            page.keyboard.type(prompt, delay=type_delay_ms)
            time.sleep(0.5)

            txt = get_box_text(box)
            if txt and len(txt.strip()) >= min(8, len(prompt)):
                return True

            # fallback insert_text nếu type thường không vào box
            try:
                page.keyboard.insert_text(prompt)
            except Exception:
                pass
            time.sleep(0.5)
            txt = get_box_text(box)
            if txt and len(txt.strip()) >= min(8, len(prompt)):
                return True
        except Exception:
            pass

        time.sleep(0.6)

    return False


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
    # Chọn ảnh bằng cách click trực tiếp vùng có chứa text '1.jpg' (hoặc filename tương ứng)
    # sau đó fallback mapping theo id/data-*.
    stem = image_path.stem.strip()
    m = re.search(r"(\d+)", stem)
    number = m.group(1) if m else stem
    idx = int(number) if str(number).isdigit() else None

    # Step 1: tìm element hiển thị text filename và click vào chính vùng đó bằng tọa độ
    try:
        click_point = page.evaluate(
            """
            ({fileName, stem, number}) => {
              const visible = (el) => {
                if (!el) return false;
                const st = getComputedStyle(el);
                if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 10 && r.height > 10;
              };

              const norm = (s) => String(s || '').toLowerCase().trim();
              const targets = [fileName, stem, number].filter(Boolean).map(norm);

              const els = Array.from(document.querySelectorAll('body *')).filter(visible);
              let best = null;
              let bestScore = Number.POSITIVE_INFINITY;

              for (const el of els) {
                const txt = norm(el.innerText || el.textContent || '');
                if (!txt) continue;
                if (!targets.some(t => t && txt.includes(t))) continue;

                const r = el.getBoundingClientRect();
                // ưu tiên element nhỏ/vừa (label/card) hơn các container lớn
                const area = r.width * r.height;
                if (area < 30 || area > 500000) continue;

                // nếu element nằm trong popup có ảnh thì ưu tiên
                let score = area;
                const host = el.closest('[role="menu"],[role="listbox"],[role="dialog"],.MuiPopover-root,.MuiPopper-root,.cdk-overlay-pane,[data-radix-popper-content-wrapper]');
                if (!host) score += 200000;

                if (score < bestScore) {
                  bestScore = score;
                  best = r;
                }
              }

              if (!best) return null;
              return {
                x: Math.floor(best.left + best.width / 2),
                y: Math.floor(best.top + best.height / 2),
              };
            }
            """,
            {"fileName": image_path.name, "stem": stem, "number": number},
        )
        if click_point and isinstance(click_point, dict):
            x = float(click_point.get("x", 0))
            y = float(click_point.get("y", 0))
            if x > 0 and y > 0:
                page.mouse.click(x, y)
                time.sleep(0.7)
                return True
    except Exception:
        pass

    # Step 2: fallback mapping id/data-* trong popup
    try:
        picked = page.evaluate(
            """
            ({fileName, stem, number, idx}) => {
              const visible = (el) => {
                if (!el) return false;
                const st = getComputedStyle(el);
                if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 10 && r.height > 10;
              };

              const clickEl = (el) => {
                if (!el) return false;
                const target = el.closest('button,[role="button"],[role="option"],[role="menuitem"],[role="gridcell"],li,div') || el;
                target.click();
                return true;
              };

              const zNum = (el) => {
                try {
                  const n = parseInt(getComputedStyle(el).zIndex || '0', 10);
                  return Number.isFinite(n) ? n : 0;
                } catch { return 0; }
              };

              const allNodes = Array.from(document.querySelectorAll('body *')).filter(visible);
              const overlayCandidates = allNodes.filter(el => el.querySelector('img'));
              let root = null;
              let best = -1;
              for (const el of overlayCandidates) {
                const score = zNum(el) * 1000 + el.querySelectorAll('img').length;
                if (score > best) { best = score; root = el; }
              }
              if (!root) return false;

              const norm = (s) => String(s || '').toLowerCase();
              const targets = [fileName, stem, number].filter(Boolean).map(norm);
              const numberRe = number ? new RegExp(`(^|[^0-9])${number}([^0-9]|$)`) : null;

              const cards = Array.from(root.querySelectorAll('*')).filter(el => {
                if (!visible(el)) return false;
                if (el.tagName === 'IMG') return true;
                return !!el.querySelector('img');
              });

              const metaOf = (el) => {
                const img = el.tagName === 'IMG' ? el : el.querySelector('img');
                return [
                  el.id,
                  el.getAttribute('data-id'),
                  el.getAttribute('data-key'),
                  el.getAttribute('data-testid'),
                  el.getAttribute('aria-label'),
                  el.getAttribute('title'),
                  el.textContent,
                  img?.getAttribute('alt'),
                  img?.getAttribute('src'),
                  img?.id,
                  img?.getAttribute('data-id'),
                  img?.getAttribute('data-key'),
                  img?.getAttribute('data-testid')
                ].map(norm).join(' ');
              };

              for (const el of cards) {
                const meta = metaOf(el);
                if (targets.some(t => t && meta.includes(t))) {
                  return clickEl(el);
                }
              }

              if (numberRe) {
                for (const el of cards) {
                  const meta = metaOf(el);
                  if (numberRe.test(meta)) {
                    return clickEl(el);
                  }
                }
              }

              const thumbs = Array.from(root.querySelectorAll('img')).filter(visible);
              if (!thumbs.length) return false;
              thumbs.sort((a, b) => {
                const ra = a.getBoundingClientRect();
                const rb = b.getBoundingClientRect();
                const dy = ra.top - rb.top;
                if (Math.abs(dy) > 6) return dy;
                return ra.left - rb.left;
              });
              let pick = 0;
              if (Number.isInteger(idx) && idx > 0) pick = Math.min(idx - 1, thumbs.length - 1);
              return clickEl(thumbs[pick]);
            }
            """,
            {"fileName": image_path.name, "stem": stem, "number": number, "idx": idx},
        )
        if picked:
            time.sleep(0.7)
            return True
    except Exception:
        pass

    return False


def _click_upload_image_item(page):
    upload_item_selectors = [
        "button:has-text('Upload image')",
        "button:has-text('Upload an image')",
        "button:has-text('Tải hình ảnh lên')",
        "button:has-text('Tải ảnh lên')",
        "[role='menuitem']:has-text('Upload image')",
        "[role='menuitem']:has-text('Upload an image')",
        "[role='menuitem']:has-text('Tải hình ảnh lên')",
        "[role='option']:has-text('Upload image')",
        "[role='option']:has-text('Upload an image')",
    ]

    for sel in upload_item_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                try:
                    loc.first.click(timeout=3500)
                except Exception:
                    loc.first.click(timeout=3500, force=True)
                time.sleep(0.35)
                return True
        except Exception:
            pass

    # fallback mạnh: click theo text trên mọi phần tử menu/list
    try:
        ok = page.evaluate(
            """
            () => {
              const visible = (el) => {
                if (!el) return false;
                const st = getComputedStyle(el);
                if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 6 && r.height > 6;
              };
              const texts = ['upload image','upload an image','tải hình ảnh lên','tải ảnh lên'];
              const els = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], button, div, span')).filter(visible);
              for (const el of els) {
                const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                if (!t) continue;
                if (texts.some(x => t.includes(x))) {
                  el.click();
                  return true;
                }
              }
              return false;
            }
            """
        )
        if ok:
            time.sleep(0.35)
            return True
    except Exception:
        pass

    return False


def upload_reference_image(page, image_path: Path, prompt_box=None):
    """Extension-style image pipeline: upload to Flow library, then search by filename and attach.

    This replaces the old UI-position based uploader. It follows extension 2.0.6 logic:
    add_2 trigger -> file input inject -> wait settle -> add_2 trigger -> search filename -> click result row.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise RuntimeError(f"missing_ref_image:{image_path}")

    fname = image_path.name

    # Phase 1: open add_2 picker / upload menu
    if not _open_plus_menu(page, prompt_box=prompt_box):
        raise RuntimeError("extension_upload:cannot_open_add2")

    # Try explicit Upload image item if present, otherwise set file into available image input directly.
    _click_upload_image_item(page)
    file_set = set_upload_file_input(page, image_path)
    if not file_set:
        raise RuntimeError(f"extension_upload:cannot_inject_file:{fname}")

    log_line(f"[flow] extension-upload injected file: {fname}")
    time.sleep(3.0)

    # Phase 2: attach by reopening picker and searching filename (extension-style)
    attached = False
    for attempt in range(1, 6):
        try:
            if not _open_plus_menu(page, prompt_box=prompt_box):
                time.sleep(0.8)
                continue

            # search input inside asset picker/dialog
            found = page.evaluate(
                """
                (fname) => {
                  const visible = (el) => {
                    if (!el) return false;
                    const st = getComputedStyle(el);
                    if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 8 && r.height > 8;
                  };
                  const inputs = Array.from(document.querySelectorAll('[role="dialog"] input[type="text"], input[type="text"]')).filter(visible);
                  const input = inputs[inputs.length - 1];
                  if (!input) return {ok:false, step:'no_search_input'};
                  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                  if (setter) setter.call(input, fname); else input.value = fname;
                  input.dispatchEvent(new Event('input', {bubbles:true}));
                  input.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true, key:'Enter'}));
                  return {ok:true, step:'searched'};
                }
                """,
                fname,
            )
            if not found or not found.get("ok"):
                time.sleep(0.8)
                continue

            # wait for virtuoso/list result exact filename and click its row
            deadline = time.time() + 12
            while time.time() < deadline:
                clicked = page.evaluate(
                    """
                    (fname) => {
                      const visible = (el) => {
                        if (!el) return false;
                        const st = getComputedStyle(el);
                        if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 8 && r.height > 8;
                      };
                      const norm = s => String(s || '').trim().toLowerCase();
                      const target = norm(fname);
                      const imgs = Array.from(document.querySelectorAll('[data-testid="virtuoso-item-list"] img[alt], [role="dialog"] img[alt], img[alt]')).filter(visible);
                      let img = imgs.find(i => norm(i.getAttribute('alt')) === target) || imgs.find(i => norm(i.getAttribute('alt')).endsWith('/' + target));
                      if (!img) return false;
                      const row = img.closest('button,[role="button"],[role="option"],[role="menuitem"],[role="gridcell"],li,div') || img.parentElement || img;
                      row.click();
                      return true;
                    }
                    """,
                    fname,
                )
                if clicked:
                    attached = True
                    break
                time.sleep(0.35)

            if attached:
                break
        except Exception:
            pass
        time.sleep(1.0)

    if not attached:
        raise RuntimeError(f"extension_upload:cannot_attach_by_filename:{fname}")

    # close any remaining popover and wait for attach chip/reference to settle
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
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


def classify_flow_error(page):
    try:
        txt = (page.locator("body").inner_text(timeout=2000) or "").lower()
        if "daily" in txt and ("limit" in txt or "quota" in txt):
            return "daily_limit"
        if "queue" in txt and ("full" in txt or "đầy" in txt):
            return "queue_full"
        if "policy" in txt or "chính sách" in txt:
            return "policy"
        if "oops, something went wrong" in txt:
            return "oops"
    except Exception:
        pass
    return ""


def has_failure(page):
    # Conservative check: only treat explicit global Oops banner as failure.
    # Per-item "Failed/Retry" cards may exist from older jobs and should not stop the loop.
    body = page.locator("body")
    txt = body.inner_text(timeout=2000)
    return "Oops, something went wrong" in txt


def snapshot_media_tiles(page):
    try:
        return set(page.evaluate(
            """
            () => Array.from(document.querySelectorAll('[data-tile-id], video, img[src*="media.getMediaUrlRedirect"], video[src*="media.getMediaUrlRedirect"], img[src^="blob:"], canvas'))
              .map((el, i) => el.getAttribute('data-tile-id') || el.currentSrc || el.src || el.getAttribute('src') || `media-${i}`)
              .filter(Boolean)
            """
        ) or [])
    except Exception:
        return set()


def wait_new_completed_media(page, before_ids=None, expected_count=1, timeout_sec=480):
    before_ids = set(before_ids or [])
    deadline = time.time() + timeout_sec
    last_count = 0
    while time.time() < deadline:
        try:
            data = page.evaluate(
                """
                (before) => {
                  const visible = (el) => {
                    if (!el) return false;
                    const st = getComputedStyle(el);
                    if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 20 && r.height > 20;
                  };
                  const beforeSet = new Set(before || []);
                  const nodes = Array.from(document.querySelectorAll('[data-tile-id], video, img[src*="media.getMediaUrlRedirect"], video[src*="media.getMediaUrlRedirect"], img[src^="blob:"], img[src^="https://"], canvas')).filter(visible);
                  const ready = [];
                  for (let i=0;i<nodes.length;i++) {
                    const el = nodes[i];
                    const id = el.getAttribute('data-tile-id') || el.currentSrc || el.src || el.getAttribute('src') || `media-${i}`;
                    const hasMedia = !!(el.querySelector?.('video[src*="media.getMediaUrlRedirect"],img[src*="media.getMediaUrlRedirect"],video,img[src^="blob:"],canvas') || el.matches?.('video,img,canvas'));
                    if (id && !beforeSet.has(id) && hasMedia) ready.push(id);
                  }
                  const txt = (document.body?.innerText || '').toLowerCase();
                  const queueFull = txt.includes('queue') && (txt.includes('full') || txt.includes('đầy'));
                  const policy = txt.includes('policy') || txt.includes('chính sách');
                  const generating = txt.includes('generating') || txt.includes('đang tạo') || txt.includes('%');
                  return {count: ready.length, queueFull, policy, generating};
                }
                """,
                list(before_ids),
            ) or {}
            last_count = int(data.get("count") or 0)
            if data.get("policy"):
                return False, "policy"
            if data.get("queueFull"):
                return False, "queue_full"
            if last_count >= int(expected_count or 1):
                return True, "ready"
        except Exception:
            pass
        time.sleep(3.0)
    return False, f"timeout_media_count_{last_count}"


def wait_generation_complete(page, timeout_sec=360):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            state = page.evaluate(
                """
                () => {
                  const txt = (document.body?.innerText || '').toLowerCase();
                  const hasGenerating = txt.includes('generating') || txt.includes('đang tạo') || txt.includes('rendering');

                  const hasKebab = Array.from(document.querySelectorAll('button,[role="button"]')).some(b => {
                    const t = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('title') || '')).toLowerCase();
                    return t.includes('more') || t.includes('more_vert') || t.includes('more_horiz') || t.includes('menu') || t.includes('tùy chọn');
                  });

                  const hasDownloadText = txt.includes('download') || txt.includes('tải xuống');
                  const hasReady = hasKebab || hasDownloadText;
                  return {hasGenerating, hasReady};
                }
                """
            )
            if state and state.get("hasReady") and not state.get("hasGenerating"):
                return True
        except Exception:
            pass
        time.sleep(2.0)
    return False


def extension_download_tile_via_ui(page, resolution="720p", before_ids=None, output_prefix="flow-auto"):
    """Downloader ported from extension 2.0.6 (yr + Un): tile media -> context menu -> download -> quality."""
    try:
        download_obj = None
        with page.expect_download(timeout=30000) as download_info:
            step = page.evaluate(
            """
            async ({resolution, beforeIds}) => {
              const p = (ms) => new Promise(r => setTimeout(r, ms));
              const before = new Set(beforeIds || []);
              const visible = (el) => {
                if (!el) return false;
                const st = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 10 && r.height > 10;
              };

              // Extension helpers: On(tile), Dn(tile), $n(snapshot)
              const On = (tile) => !!tile.querySelector('video[src*="media.getMediaUrlRedirect"]') || !!tile.querySelector('img[src*="media.getMediaUrlRedirect"]');
              const Dn = (tile) => !!tile.querySelector('video');
              const collectNewTiles = (snapshot) => {
                const out = [], seen = new Set();
                document.querySelectorAll('[data-tile-id]').forEach(tile => {
                  const id = tile.getAttribute('data-tile-id');
                  if (!id || seen.has(id)) return;
                  seen.add(id);
                  if (snapshot && snapshot.has(id)) return;
                  if (On(tile) && visible(tile)) out.push({tileId:id, tileEl:tile, isVideo:Dn(tile)});
                });
                return out;
              };

              // Extension yr(e,t): choose requested quality, fallback best enabled.
              const yr = (menu, targetQuality) => {
                const btns = [...menu.querySelectorAll('button[role="menuitem"], button')];
                if (btns.length === 0) return null;
                const items = btns.map(btn => {
                  const label = btn.querySelectorAll('span')[0]?.textContent.trim() || btn.textContent.trim();
                  const enabled = btn.getAttribute('aria-disabled') !== 'true';
                  return {btn, label, enabled};
                });
                const enabled = items.filter(x => x.enabled);
                if (targetQuality) {
                  const exact = items.find(x => x.label === targetQuality);
                  if (exact) {
                    if (exact.enabled) return exact.btn;
                  }
                  const partial = items.find(x => x.enabled && x.label.includes(targetQuality));
                  if (partial) return partial.btn;
                }
                if (enabled.length > 0) return enabled[enabled.length - 1].btn;
                return btns[0];
              };

              // Extension Un(tile, quality): right-click tile media and download via UI.
              const Un = async (tile, targetQuality=null) => {
                try {
                  const media = tile.querySelector('video[src*="media.getMediaUrlRedirect"]') || tile.querySelector('img[src*="media.getMediaUrlRedirect"]');
                  if (!media) return {ok:false, step:'no_media_in_tile'};
                  const r = media.getBoundingClientRect();
                  const x = r.left + r.width / 2, y = r.top + r.height / 2;
                  media.dispatchEvent(new MouseEvent('mouseenter', {bubbles:true, clientX:x, clientY:y}));
                  media.dispatchEvent(new MouseEvent('mousemove', {bubbles:true, clientX:x, clientY:y}));
                  await p(400);
                  media.dispatchEvent(new MouseEvent('contextmenu', {bubbles:true, cancelable:true, clientX:x, clientY:y, button:2}));
                  await p(600);
                  const contextMenu = document.querySelector('[data-radix-menu-content][data-state="open"]');
                  if (!contextMenu) return {ok:false, step:'no_context_menu'};
                  const downloadItem = [...contextMenu.querySelectorAll('[role="menuitem"]')].find(item => item.querySelector('i')?.textContent.trim() === 'download');
                  if (!downloadItem) {
                    document.body.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
                    return {ok:false, step:'no_download_item'};
                  }
                  downloadItem.click();
                  await p(600);
                  const menus = [...document.querySelectorAll('[data-radix-menu-content][data-state="open"]')];
                  let qualityMenu = menus.find(m => m !== contextMenu) || menus[menus.length - 1];
                  if ((!qualityMenu || qualityMenu === contextMenu) && !([...document.querySelectorAll('[data-radix-popper-content-wrapper]')].flatMap(w => [...w.querySelectorAll('[role="menuitem"]')]).length > 0 ? document.querySelector('[data-radix-popper-content-wrapper]:last-of-type') : null)) {
                    document.body.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
                    return {ok:false, step:'no_quality_menu'};
                  }
                  if (!qualityMenu || qualityMenu === contextMenu) {
                    qualityMenu = document.querySelector('[data-radix-popper-content-wrapper]:last-of-type') || qualityMenu;
                  }
                  const qualityBtn = yr(qualityMenu, targetQuality);
                  if (!qualityBtn) {
                    document.body.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
                    return {ok:false, step:'no_quality_button'};
                  }
                  qualityBtn.click();
                  await p(300);
                  return {ok:true, step:'done'};
                } catch (err) {
                  document.body.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
                  return {ok:false, step:'exception:' + (err && err.message || err)};
                }
              };

              let tiles = collectNewTiles(before);
              if (!tiles.length) {
                // Khi có snapshot beforeIds, tuyệt đối không fallback sang tile khác để tránh tải nhầm file khi auto đang chạy.
                if (before.size > 0) return {ok:false, step:'no_new_tile_from_snapshot'};
                tiles = collectNewTiles(new Set());
              }
              if (!tiles.length) return {ok:false, step:'no_tiles'};
              tiles.sort((a,b) => {
                const ar = a.tileEl.getBoundingClientRect(), br = b.tileEl.getBoundingClientRect();
                // Khi tải trễ nhiều prompt, tile cũ hơn thường nằm thấp hơn; ưu tiên tile cũ nhất để không tải nhầm prompt mới.
                return br.top - ar.top;
              });
              const targetTile = tiles[0].tileEl;
              targetTile.scrollIntoView({block:'center', inline:'center', behavior:'instant'});
              await p(350);
              return await Un(targetTile, resolution || null);
            }
            """,
            {"resolution": str(resolution), "beforeIds": list(before_ids or [])},
        )
        if not (step and step.get("ok")):
            return False, (step or {}).get("step", "unknown")
        download_obj = download_info.value
        filename = (download_obj.suggested_filename or "").lower()
        valid_exts = (".mp4", ".mov", ".webm", ".mkv", ".jpg", ".jpeg", ".png", ".webp", ".gif")
        download_path = None
        try:
            pth = download_obj.path()
            download_path = Path(pth) if pth else None
        except Exception:
            download_path = None

        detected_ext = None
        try:
            if download_path and download_path.exists():
                head = download_path.read_bytes()[:64]
                if head.startswith(b"\xff\xd8\xff"):
                    detected_ext = ".jpg"
                elif head.startswith(b"\x89PNG\r\n\x1a\n"):
                    detected_ext = ".png"
                elif head.startswith(b"RIFF") and b"WEBP" in head[:16]:
                    detected_ext = ".webp"
                elif len(head) > 12 and b"ftyp" in head[:16]:
                    detected_ext = ".mp4"
                elif head.startswith(b"\x1aE\xdf\xa3"):
                    detected_ext = ".webm"
                elif head[:6] in (b"GIF87a", b"GIF89a"):
                    detected_ext = ".gif"
        except Exception:
            detected_ext = None

        uuidish = bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(\.[a-z0-9]+)?", filename or ""))
        if filename.endswith(valid_exts) and not uuidish:
            return True, f"done:{filename}"
        if detected_ext and download_path and download_path.exists():
            out_dir = Path.home() / "Downloads"
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            safe_prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", str(output_prefix or "flow-auto")).strip("_")[:80] or "flow-auto"
            stem = f"{safe_prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            target = out_dir / f"{stem}{detected_ext}"
            n = 1
            while target.exists():
                target = out_dir / f"{stem}-{n}{detected_ext}"
                n += 1
            try:
                download_obj.save_as(str(target))
            except Exception:
                try:
                    target.write_bytes(download_path.read_bytes())
                except Exception:
                    pass
            return True, f"done_saved_as:{target.name}"

        try:
            if download_path and download_path.exists():
                download_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            download_obj.cancel()
        except Exception:
            pass
        return False, f"invalid_download_file:{filename or 'unknown'}"
    except Exception as e:
        return False, f"exception:{e}"

def auto_download_with_retry(page, resolution="720p", timeout_sec=480, before_ids=None, output_prefix="flow-auto"):
    deadline = time.time() + timeout_sec
    last = "unknown"
    res = str(resolution)
    if res == "720":
        res = "720p"
    while time.time() < deadline:
        ok, step = extension_download_tile_via_ui(page, resolution=res, before_ids=before_ids, output_prefix=output_prefix)
        last = step
        if ok:
            return True, step
        time.sleep(4.0)
    return False, last


def license_guard_or_raise():
    checker = Path(__file__).resolve().with_name("flow_license_online_check.py")
    if not checker.exists():
        return
    try:
        r = subprocess.run([sys.executable, str(checker), "--check", "--json"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
        raw = (r.stdout or r.stderr or "").strip()
        ok = False
        reason = "license_check_failed"
        try:
            obj = json.loads(raw)
            ok = bool(obj.get("ok")) and r.returncode == 0
            reason = str(obj.get("reason") or reason)
        except Exception:
            ok = r.returncode == 0
            reason = raw[:120] or reason
        if not ok:
            raise RuntimeError(f"license_invalid:{reason}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("license_invalid:timeout")


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
        delayed_downloads = []
        for idx in range(done, total):
            prompt = prompts[idx]
            prompt_no = idx + 1
            ok = False

            for attempt in range(1, args.max_retries + 2):
                try:
                    license_guard_or_raise()
                    page.bring_to_front()

                    # Áp dụng toàn bộ setting truyền từ GUI/worker theo thứ tự chuẩn
                    apply_flow_settings(page, args)

                    box = find_input_box(page)

                    if needs_clear_before_insert:
                        clear_prompt_box(page, box)
                        clear_attached_references(page)
                        needs_clear_before_insert = False

                    # Paired mode: 1.jpg -> prompt1, 2.jpg -> prompt2 ...
                    if args.paired_mode:
                        ref_img = resolve_ref_image(refs_dir, prompt_no)
                    else:
                        ref_img = resolve_first_ref_image(refs_dir)

                    prompt_to_type = prompt
                    if ref_img is not None:
                        log_line(f"[flow] prompt #{prompt_no} use ref image: {ref_img.name}")
                        upload_reference_image(page, ref_img, prompt_box=box)
                        if args.reference_mode == "tag":
                            prompt_to_type = f"@{ref_img.stem} {prompt}"

                    time.sleep(random.uniform(args.pre_paste_min, args.pre_paste_max))

                    # Quy trình nhập prompt mới với verify
                    typed_ok = type_prompt_with_verify(page, prompt_to_type, type_delay_ms=args.type_delay_ms, retries=3)
                    if not typed_ok:
                        raise RuntimeError("prompt_not_typed_after_image_upload")

                    # Snapshot media tiles trước submit để monitor output mới giống extension
                    pre_submit_tiles = snapshot_media_tiles(page)

                    # Bỏ chọn tỉ lệ theo yêu cầu: giữ nguyên tỉ lệ hiện tại trên UI
                    time.sleep(args.before_create_sec)
                    btn = find_create_button(page)
                    btn.click(timeout=5000)

                    time.sleep(2)
                    fail_reason = classify_flow_error(page)
                    if fail_reason:
                        if fail_reason == "daily_limit" and args.flow_model != "default":
                            log_line("[flow] daily limit detected, fallback model=default and retry")
                            args.flow_model = "default"
                        raise RuntimeError(f"flow_error:{fail_reason}")

                    if args.auto_download:
                        if int(args.download_delay_prompts or 0) > 0:
                            delayed_downloads.append({
                                "prompt_no": prompt_no,
                                "before_ids": pre_submit_tiles,
                                "task_mode": args.task_mode,
                                "count": args.flow_count,
                                "output_prefix": prompt_file_prefix(prompt, prompt_no),
                            })
                            if len(delayed_downloads) >= int(args.download_delay_prompts or 0):
                                item = delayed_downloads.pop(0)
                                log_line(f"[flow] delayed download prompt #{item['prompt_no']}")
                                media_ok, media_reason = wait_new_completed_media(page, before_ids=item["before_ids"], expected_count=max(1, int(item["count"] or "1")), timeout_sec=args.download_wait_sec)
                                if not media_ok:
                                    done_wait = wait_generation_complete(page, timeout_sec=90)
                                    if not done_wait:
                                        raise RuntimeError(f"generation_not_completed:{media_reason}")
                                download_resolution = "1K" if item["task_mode"] == "createimage" else args.download_resolution
                                dl_ok, dl_step = auto_download_with_retry(page, resolution=download_resolution, timeout_sec=220, before_ids=item["before_ids"], output_prefix=item.get("output_prefix", f"prompt_{item['prompt_no']}"))
                                if not dl_ok:
                                    raise RuntimeError(f"auto_download_failed:{dl_step}")
                        else:
                            media_ok, media_reason = wait_new_completed_media(
                                page,
                                before_ids=pre_submit_tiles,
                                expected_count=max(1, int(args.flow_count or "1")),
                                timeout_sec=args.download_wait_sec,
                            )
                            if not media_ok:
                                # fallback old watcher for UI variants, then still try download
                                done_wait = wait_generation_complete(page, timeout_sec=90)
                                if not done_wait:
                                    raise RuntimeError(f"generation_not_completed:{media_reason}")
                            download_resolution = "1K" if args.task_mode == "createimage" else args.download_resolution
                            dl_ok, dl_step = auto_download_with_retry(page, resolution=download_resolution, timeout_sec=220, before_ids=pre_submit_tiles, output_prefix=prompt_file_prefix(prompt, prompt_no))
                            if not dl_ok:
                                raise RuntimeError(f"auto_download_failed:{dl_step}")

                    ok = True
                    break
                except (PWTimeout, Exception) as e:
                    needs_clear_before_insert = True
                    log_line(f"[flow] prompt #{prompt_no} attempt {attempt} error: {e}")
                    if attempt <= args.max_retries:
                        time.sleep(2)

            # Sau khi tạo/download thành công: reset UI để prompt kế tiếp upload ảnh mới đúng paired-mode
            if ok and prompt_no < total:
                try:
                    page.bring_to_front()
                    close_open_menus(page)
                    clear_attached_references(page)

                    # Nếu có thư mục ảnh ref, tạo project mới cho prompt kế tiếp để không reuse ảnh/prompt cũ
                    if refs_dir is not None:
                        try:
                            _try_click_new_project(page)
                            time.sleep(1.2)
                        except Exception:
                            pass

                    next_box = find_input_box(page)
                    clear_prompt_box(page, next_box)
                    clear_attached_references(page)
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

        if args.auto_download and int(args.download_delay_prompts or 0) > 0:
            while delayed_downloads:
                item = delayed_downloads.pop(0)
                log_line(f"[flow] delayed final download prompt #{item['prompt_no']}")
                media_ok, media_reason = wait_new_completed_media(page, before_ids=item["before_ids"], expected_count=max(1, int(item["count"] or "1")), timeout_sec=args.download_wait_sec)
                if not media_ok:
                    done_wait = wait_generation_complete(page, timeout_sec=90)
                    if not done_wait:
                        log_line(f"[flow] delayed final download skipped prompt #{item['prompt_no']}: {media_reason}")
                        continue
                download_resolution = "1K" if item["task_mode"] == "createimage" else args.download_resolution
                dl_ok, dl_step = auto_download_with_retry(page, resolution=download_resolution, timeout_sec=220, before_ids=item["before_ids"], output_prefix=item.get("output_prefix", f"prompt_{item['prompt_no']}"))
                if not dl_ok:
                    log_line(f"[flow] delayed final download failed prompt #{item['prompt_no']}: {dl_step}")

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
    ap.add_argument("--auto-download", action="store_true", help="Tự động tải video sau khi render xong")
    ap.add_argument("--submit-only", action="store_true", help="Chỉ submit prompt rồi chuyển prompt tiếp theo, không chờ render và không auto-download")
    ap.add_argument("--download-resolution", default="720", help="Độ phân giải tải về, mặc định 720")
    ap.add_argument("--download-wait-sec", type=int, default=420, help="Thời gian chờ render hoàn tất trước khi tải")
    ap.add_argument("--download-delay-prompts", type=int, default=0, help="Chế độ chạy liên tục: chờ N prompt sau mới tải prompt cũ")

    # Flow settings (đồng bộ với extension)
    ap.add_argument("--task-mode", default="createvideo", choices=["createvideo", "createimage"], help="Chế độ tạo: video hoặc image")
    ap.add_argument("--flow-model", default="default", help="Model key: default|veo3_lite|veo3_fast|veo3_quality|nano_banana_pro|nano_banana2|imagen4")
    ap.add_argument("--flow-aspect-ratio", default="16:9", help="Tỉ lệ: 16:9 | 9:16 | square | landscape_4_3 | portrait_3_4")
    ap.add_argument("--flow-count", default="1", help="Số lượng output x1/x2/x3/x4")
    ap.add_argument("--video-sub-mode", default="frames", choices=["frames", "ingredients"], help="Video sub mode")
    ap.add_argument("--reference-mode", default="ingredients", choices=["ingredients", "tag"], help="Reference mode")
    ap.add_argument("--paired-mode", dest="paired_mode", action="store_true", help="Map ảnh theo số prompt (1.jpg->prompt1)")
    ap.add_argument("--no-paired-mode", dest="paired_mode", action="store_false", help="Không map theo số prompt")
    ap.set_defaults(paired_mode=True)

    args = ap.parse_args()
    if args.submit_only:
        args.auto_download = False
    run(args)


if __name__ == "__main__":
    main()
