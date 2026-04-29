const fs=require('fs'); const path=require('path');
const { chromium } = require('playwright-core');
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
const arg=(name,def='')=>{const i=process.argv.indexOf(name);return i>=0?process.argv[i+1]:def};
const has=(name)=>process.argv.includes(name);
const stateFile=arg('--state'); const promptsFile=arg('--prompts'); const cdp=arg('--cdp','http://127.0.0.1:18800');
const pauseFile=process.env.FLOW_PAUSE_FILE||'';
const refsDir=arg('--refs-dir',''); const taskMode=arg('--task-mode','createvideo'); const model=arg('--flow-model','default'); const ratio=arg('--flow-aspect-ratio','16:9'); const count=arg('--flow-count','1');
const autoDownload=has('--auto-download'); const submitOnly=has('--submit-only'); const delayPrompts=Number(arg('--download-delay-prompts','0')||0); const pairedMode=!has('--no-paired-mode');
function log(s){ console.log(`[flow-js] ${s}`); }
function save(done,total,current=''){ if(stateFile) fs.writeFileSync(stateFile,JSON.stringify({done,total,current,updated_at:new Date().toISOString()},null,2)); }
function prompts(){ const t=fs.readFileSync(promptsFile,'utf8'); return t.split(/\n\s*\n/g).map(x=>x.trim()).filter(Boolean); }
function safePrefix(prompt,no){ return String(no).padStart(3,'0')+'_'+String(prompt).replace(/[^a-z0-9]+/gi,'_').replace(/^_+|_+$/g,'').slice(0,60); }
function refFor(idx){ if(!refsDir||!fs.existsSync(refsDir))return ''; const stems=pairedMode?[String(idx+1)]:['1','ref','reference']; for(const st of stems){ for(const ext of ['.jpg','.jpeg','.png','.webp']){ const p=path.join(refsDir,st+ext); if(fs.existsSync(p)) return p; }} return ''; }
async function findFlowPage(browser){ for(const ctx of browser.contexts()){ for(const p of ctx.pages()){ if((p.url()||'').includes('labs.google')||(p.url()||'').includes('flow')) return p; }} const ctx=browser.contexts()[0]||await browser.newContext(); return await ctx.newPage(); }
async function closeMenus(page){ try{await page.keyboard.press('Escape'); await sleep(150); await page.keyboard.press('Escape');}catch{} }
async function clickText(page, texts, timeout=1200){ for(const t of texts){ const loc=page.getByText(t,{exact:false}).last(); try{ if(await loc.count()){ await loc.click({timeout}); return true; }}catch{} } return false; }
async function clickIcon(page, icon){ const loc=page.locator(`text=${icon}`).last(); try{ if(await loc.count()){ await loc.click({timeout:1200}); return true; }}catch{} return false; }
async function ensureProjectPage(page){
  const url=page.url()||'';
  if(!/labs\.google\/fx(?:\/[a-z]{2})?\/tools\/flow/.test(url)){
    await page.goto('https://labs.google/fx/vi/tools/flow',{waitUntil:'domcontentloaded',timeout:30000}).catch(()=>{});
    await sleep(1200);
  }
  // Nếu đã có ô prompt thì đang ở editor/project rồi.
  try{ if(await page.locator('textarea,[contenteditable="true"],div[role="textbox"]').last().isVisible({timeout:1200})) return page; }catch{}
  const selectors=[
    "button:has-text('New project')",
    "button:has-text('Dự án mới')",
    "button:has-text('Tạo dự án')",
    "a:has-text('New project')",
    "[role='button']:has-text('New project')",
    "button[id*='new' i]",
    "button[data-testid*='new' i]"
  ];
  for(const sel of selectors){ try{ const loc=page.locator(sel).first(); if(await loc.count() && await loc.isVisible({timeout:700}).catch(()=>false)){ await loc.click({timeout:4000}).catch(()=>loc.click({timeout:4000,force:true})); await sleep(1500); return page; }}catch{} }
  try{
    const loc=page.locator('button,[role="button"],a,[role="link"]').filter({hasText:/new\s*project|dự\s*án\s*mới|tạo\s*dự\s*án|new/i}).first();
    if(await loc.count()){ await loc.click({timeout:4000}).catch(()=>loc.click({timeout:4000,force:true})); await sleep(1500); }
  }catch{}
  return page;
}
async function findInput(page){ const deadline=Date.now()+30000; let retried=false; const sels=['div[role="textbox"][contenteditable="true"]','div[contenteditable="true"]','textarea','input[type="text"]']; while(Date.now()<deadline){ for(const s of sels){ try{ const boxes=page.locator(s); const count=await boxes.count(); for(let i=count-1;i>=0;i--){ const b=boxes.nth(i); if(await b.isVisible({timeout:250}).catch(()=>false)) return b; }}catch{} } if(!retried){ await ensureProjectPage(page); retried=true; } await sleep(500); } throw new Error('Không tìm thấy ô nhập prompt'); }
async function fillPrompt(page,text){ const box=await findInput(page); await box.click({timeout:5000}); await page.keyboard.press(process.platform==='darwin'?'Meta+A':'Control+A'); try{ await page.keyboard.insertText(text); }catch{ await page.keyboard.type(text,{delay:1}); } }
async function clickSubmit(page){ const sels=['button[aria-label*="Submit" i]','button[aria-label*="Create" i]','button[aria-label*="Generate" i]','button:has-text("Submit")','button:has-text("Create")','button:has-text("Generate")','button:has-text("arrow_forward")']; for(const s of sels){ const b=page.locator(s).last(); try{ if(await b.count()){ await b.click({timeout:3000}); return true; }}catch{} } await page.keyboard.press('Enter'); return true; }
async function openSettings(page){ await closeMenus(page); if(await clickIcon(page,'tune')) return true; if(await clickIcon(page,'settings')) return true; const btn=page.locator('button').filter({hasText:/tune|settings|sliders|menu/i}).last(); try{ if(await btn.count()){await btn.click({timeout:1200}); return true;} }catch{} return false; }
async function applySettings(page){
  await openSettings(page).catch(()=>{}); await sleep(300);
  if(taskMode==='createimage') await clickText(page,['Image','Ảnh','image']).catch(()=>{}); else await clickText(page,['Video','video']).catch(()=>{});
  if(ratio) await clickText(page,[ratio, ratio.replace('_',' ')]).catch(()=>{});
  if(count) await clickText(page,[`${count} output`,`${count} outputs`,`${count}`]).catch(()=>{});
  if(model && model!=='default') await clickText(page,[model,model.replaceAll('_',' ')]).catch(()=>{});
  await closeMenus(page);
}
async function uploadRef(page,file){ if(!file)return false; await closeMenus(page); try{ const input=page.locator('input[type="file"]').last(); if(await input.count()){ await input.setInputFiles(file); await sleep(1500); return true; } }catch{}
  try{ await clickIcon(page,'add'); await sleep(300); await clickText(page,['Upload','Tải lên','Image','Ảnh']); const input=page.locator('input[type="file"]').last(); await input.setInputFiles(file); await sleep(1800); return true; }catch(e){ log('upload_ref_failed:'+e.message); return false; }
}
async function mediaTiles(page){ return await page.evaluate(()=>Array.from(document.querySelectorAll('[data-tile-id]')).map((el,i)=>({id:el.getAttribute('data-tile-id')||String(i),top:el.getBoundingClientRect().top}))); }
async function downloadLatest(page,prefix){
  try{ const tiles=await page.locator('[data-tile-id]').count(); if(!tiles) return false; const tile=page.locator('[data-tile-id]').last(); await tile.scrollIntoViewIfNeeded(); await tile.click({button:'right',timeout:4000}); await sleep(300); const isImg=taskMode==='createimage'; await clickText(page,['Download','Tải xuống']); await sleep(300); await clickText(page,[isImg?'1K':'720p','720','Download','Tải xuống']); return true; }catch(e){ log('download_failed:'+e.message); return false; }
}
async function waitAfterSubmit(page,beforeIds){ const start=Date.now(); while(Date.now()-start<90000){ const now=await mediaTiles(page).catch(()=>[]); if(now.some(t=>!beforeIds.has(t.id))) return true; await sleep(2000);} return false; }
async function run(){ const list=prompts(); let done=0; save(0,list.length); const browser=await chromium.connectOverCDP(cdp); const page=await findFlowPage(browser); await page.bringToFront(); await ensureProjectPage(page); const pending=[];
 for(let i=0;i<list.length;i++){ while(pauseFile&&fs.existsSync(pauseFile)){ log('paused'); await sleep(1000); } const prompt=list[i]; save(i,list.length,prompt.slice(0,80)); await applySettings(page); await uploadRef(page,refFor(i)); const before=new Set((await mediaTiles(page).catch(()=>[])).map(t=>t.id)); await fillPrompt(page,prompt); await clickSubmit(page); done=i+1; save(done,list.length); if(!submitOnly){ if(autoDownload){ if(delayPrompts>0){ pending.push({prompt,no:i+1}); if(pending.length>=delayPrompts){ await waitAfterSubmit(page,before); const item=pending.shift(); await downloadLatest(page,safePrefix(item.prompt,item.no)); }} else { await waitAfterSubmit(page,before); await downloadLatest(page,safePrefix(prompt,i+1)); } } } await sleep(Number(arg('--between-prompts-sec','10'))*1000); }
 while(pending.length){ const item=pending.shift(); await downloadLatest(page,safePrefix(item.prompt,item.no)); await sleep(1000); }
 await browser.close().catch(()=>{}); save(done,list.length); }
run().catch(e=>{ console.error(e.stack||String(e)); process.exit(1); });
