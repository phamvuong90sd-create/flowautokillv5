from pathlib import Path
p=Path('apps/flow_auto_electron/payload/scripts/flow_batch_runner.py')
s=p.read_text()
start=s.index('''            """\n            async (cfg) => {''')+len('''            """\n''')
end=s.index('''            """,\n            payload,''', start)
new=r'''            async (cfg) => {
              const p = (ms) => new Promise(r => setTimeout(r, ms));
              const v = (xp, root=document) => document.evaluate(xp, root, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
              const visible = (el) => {
                if (!el) return false;
                const st = getComputedStyle(el); const r = el.getBoundingClientRect();
                return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 8 && r.height > 8;
              };
              const clickExt = (el) => {
                if (!el) return false;
                const r = el.getBoundingClientRect(); const x = r.left + r.width/2, y = r.top + r.height/2;
                const base = {bubbles:true,cancelable:true,view:window,clientX:x,clientY:y,screenX:window.screenX+x,screenY:window.screenY+y,button:0};
                el.dispatchEvent(new PointerEvent('pointerdown', {...base,isPrimary:true,buttons:1,pointerId:1,pointerType:'mouse'}));
                el.dispatchEvent(new MouseEvent('mousedown', {...base,buttons:1}));
                el.dispatchEvent(new PointerEvent('pointerup', {...base,isPrimary:true,buttons:0,pointerId:1,pointerType:'mouse'}));
                el.dispatchEvent(new MouseEvent('mouseup', {...base,buttons:0}));
                el.dispatchEvent(new MouseEvent('click', base));
                return true;
              };
              const closeMenus = () => document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true,cancelable:true,composed:true}));
              const norm = (x) => String(x||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
              const tabIcon = (tab) => (tab?.querySelector('i')?.textContent || '').trim();
              const tabText = (tab) => (tab?.innerText || tab?.textContent || '').trim();
              const isActive = (tab) => {
                if (!tab) return false;
                const state = (tab.getAttribute('data-state') || tab.getAttribute('aria-selected') || '').toLowerCase();
                const cls = (tab.className || '').toString().toLowerCase();
                return state === 'active' || state === 'true' || cls.includes('active');
              };
              const openPanel = async () => {
                let panel = document.querySelector('[role="menu"][data-state="open"]');
                if (panel) return panel;
                const triggers = Array.from(document.querySelectorAll("button[aria-haspopup='menu']")).filter(visible);
                const trigger = triggers.find(b => /veo|banana|imagen|fast|lite|quality|16:9|9:16|x1|x2|x3|x4/i.test(b.innerText||''))
                  || v("//button[@aria-haspopup='menu' and .//div[@data-type='button-overlay'] and text()[normalize-space() != '']]");
                if (!trigger) return null;
                clickExt(trigger); await p(650);
                return document.querySelector('[role="menu"][data-state="open"]');
              };
              const panel = await openPanel();
              if (!panel) return {ok:false, step:'panel_missing'};
              const allTabs = () => Array.from((document.querySelector('[role="menu"][data-state="open"]') || panel || document).querySelectorAll("button[role='tab'].flow_tab_slider_trigger, button[role='tab']")).filter(visible);
              const sameGroup = (a,b) => {
                const pa = a.closest('[role="tablist"]') || a.parentElement;
                const pb = b.closest('[role="tablist"]') || b.parentElement;
                return pa && pa === pb;
              };
              const groupBy = (icons=[], texts=[]) => {
                const tabs = allTabs();
                const seed = tabs.find(t => icons.includes(tabIcon(t)) || texts.includes(tabText(t)));
                return seed ? tabs.filter(t => sameGroup(seed,t)) : [];
              };
              const clickGroup = async (group, pred, label) => {
                const tab = group.find(pred);
                if (!tab) return {ok:false,label,reason:'missing',group:group.map(t=>({icon:tabIcon(t),text:tabText(t),active:isActive(t)}))};
                if (!isActive(tab)) { clickExt(tab); await p(600); }
                const active = group.find(isActive) || tab;
                return {ok:isActive(tab),label,clicked:{icon:tabIcon(tab),text:tabText(tab)},active:{icon:tabIcon(active),text:tabText(active)},group:group.map(t=>({icon:tabIcon(t),text:tabText(t),active:isActive(t)}))};
              };
              const isImage = cfg.taskMode === 'createimage';
              const typeIcon = isImage ? 'image' : 'videocam';
              const typeRes = await clickGroup(groupBy(['image','videocam']), t => tabIcon(t) === typeIcon, 'type');
              await p(isImage ? 350 : 850);
              let subRes = {ok:true, skipped:true};
              if (!isImage) {
                const subIcon = cfg.videoSubMode === 'ingredients' ? 'chrome_extension' : 'crop_free';
                subRes = await clickGroup(groupBy(['chrome_extension','crop_free'], ['Video thành phần','Khung hình','Ingredients','Frames']), t => tabIcon(t) === subIcon || norm(tabText(t)).includes(cfg.videoSubMode === 'ingredients' ? 'ingredient' : 'frame') || norm(tabText(t)).includes(cfg.videoSubMode === 'ingredients' ? 'thanh phan' : 'khung hinh'), 'videoSubMode');
                await p(350);
              }
              const ratioMap = {landscape:'crop_16_9','16:9':'crop_16_9',landscape_4_3:'crop_landscape',square:'crop_square',portrait_3_4:'crop_portrait',portrait:'crop_9_16','9:16':'crop_9_16'};
              const ratioIcon = ratioMap[cfg.aspectRatio] || 'crop_16_9';
              const ratioRes = await clickGroup(groupBy(['crop_16_9','crop_9_16','crop_square','crop_landscape','crop_portrait']), t => tabIcon(t) === ratioIcon, 'ratio');
              const countRes = await clickGroup(groupBy([], ['x1','x2','x3','x4','1x','2x','3x','4x']), t => tabText(t) === `x${cfg.count}` || tabText(t) === `${cfg.count}x`, 'count');
              const models = {
                default:['Veo 3.1 - Fast','Veo 3.1 Fast','Veo 3 Fast','Fast'],
                veo3_lite:['Veo 3.1 - Lite','Veo 3.1 Lite','Veo 3 Lite','Lite'],
                veo3_fast:['Veo 3.1 - Fast','Veo 3.1 Fast','Veo 3 Fast','Fast'],
                veo3_quality:['Veo 3.1 - Quality','Veo 3.1 Quality','Veo 3 Quality','Quality'],
                nano_banana_pro:['Nano Banana Pro'], nano_banana2:['Nano Banana 2'], nano_banana:['Nano Banana 2','Nano Banana'], imagen4:['Imagen 4']
              };
              const aliases = models[cfg.model] || (isImage ? models.nano_banana_pro : models.veo3_fast);
              const matchAlias = (text) => aliases.some(a => { const t=norm(text), m=norm(a); return t.includes(m) || m.includes(t); });
              let modelRes = {ok:true, skipped: cfg.model === 'custom'};
              if (cfg.model !== 'custom') {
                await openPanel();
                const buttons = () => Array.from((document.querySelector('[role="menu"][data-state="open"]') || document).querySelectorAll('button')).filter(visible);
                let trigger = buttons().find(b => matchAlias(b.innerText||b.textContent||''))
                  || buttons().find(b => (b.getAttribute('aria-haspopup')||'').includes('menu') && /veo|banana|imagen|fast|lite|quality/i.test(b.innerText||''));
                const before = trigger ? (trigger.innerText || trigger.textContent || '') : '';
                if (trigger && matchAlias(before)) {
                  modelRes = {ok:true, already:true, before, aliases};
                } else if (trigger) {
                  clickExt(trigger); await p(750);
                  const opts = Array.from(document.querySelectorAll('[role="menuitem"] button, [role="option"], button')).filter(visible);
                  const exact = aliases[0];
                  const btn = opts.find(b => String(b.innerText||b.textContent||'').trim().includes(exact)) || opts.find(b => matchAlias(b.innerText||b.textContent||''));
                  if (btn) { clickExt(btn); await p(900); }
                  await openPanel();
                  const afterBtn = buttons().find(b => /veo|banana|imagen|fast|lite|quality/i.test(b.innerText||''));
                  const after = afterBtn ? (afterBtn.innerText || afterBtn.textContent || '') : '';
                  modelRes = {ok:!!btn && (matchAlias(after) || matchAlias(btn.innerText||btn.textContent||'')), before, after, clicked:btn ? (btn.innerText||btn.textContent||'') : '', aliases};
                } else {
                  modelRes = {ok:false, reason:'model_trigger_missing', aliases};
                }
              }
              closeMenus(); await p(300);
              const ok = !!(typeRes.ok && subRes.ok && ratioRes.ok && countRes.ok && modelRes.ok);
              return {ok, step:ok?'done':'verify_failed', typeRes, subRes, ratioRes, countRes, modelRes, cfg};
            }
'''
s=s[:start]+new+s[end:]
p.write_text(s)
dst=Path('scripts/flow_batch_runner.py')
if dst.exists(): dst.write_text(s)
print('patched')
