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
async function fillPrompt(page,text){
  for(let attempt=0;attempt<3;attempt++){
    const box=await findInput(page); await box.click({timeout:5000});
    await page.keyboard.press(process.platform==='darwin'?'Meta+A':'Control+A'); await sleep(100);
    try{ await page.keyboard.insertText(text); }catch{ await page.keyboard.type(text,{delay:1}); }
    await sleep(250);
    const ok=await box.evaluate((el,want)=>{const got=('value' in el?el.value:el.innerText||el.textContent||'').trim(); return got.length>=Math.min(20,want.trim().length) && (got.includes(want.trim().slice(0,30)) || want.trim().includes(got.slice(0,30)));}, text).catch(()=>false);
    if(ok) return true;
    await sleep(400);
  }
  throw new Error('prompt_not_typed_after_verify');
}
async function clickSubmit(page){ const sels=['button[aria-label*="Submit" i]','button[aria-label*="Create" i]','button[aria-label*="Generate" i]','button:has-text("Submit")','button:has-text("Create")','button:has-text("Generate")','button:has-text("arrow_forward")']; for(const s of sels){ const b=page.locator(s).last(); try{ if(await b.count()){ await b.click({timeout:3000}); return true; }}catch{} } await page.keyboard.press('Enter'); return true; }
async function openMainSettings(page){
  return await page.evaluate(async()=>{
    const sleep=ms=>new Promise(r=>setTimeout(r,ms));
    const visible=el=>{if(!el)return false;const st=getComputedStyle(el);const r=el.getBoundingClientRect();return st.display!=='none'&&st.visibility!=='hidden'&&r.width>8&&r.height>8};
    const click=el=>{if(!el)return false;const r=el.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;for(const ev of ['pointerdown','mousedown','pointerup','mouseup','click'])el.dispatchEvent(new MouseEvent(ev,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0}));return true};
    let menu=document.querySelector('[role="menu"][data-state="open"]'); if(menu) return true;
    const xp=x=>document.evaluate(x,document,null,XPathResult.FIRST_ORDERED_NODE_TYPE,null).singleNodeValue;
    const trigger=xp("//button[@aria-haspopup='menu' and .//div[@data-type='button-overlay'] and text()[normalize-space() != '']]") || Array.from(document.querySelectorAll("button[aria-haspopup='menu']")).filter(visible).find(b=>b.querySelector('div[data-type="button-overlay"]')) || Array.from(document.querySelectorAll('button')).filter(visible).find(b=>/tune|settings|menu|more_vert/.test((b.innerText||'')+(b.getAttribute('aria-label')||'')));
    if(trigger){click(trigger); await sleep(700)}
    return !!document.querySelector('[role="menu"][data-state="open"]');
  });
}
async function applyTaskMode(page){
  const want=taskMode==='createimage'?'image':'video'; const wantIcon=want==='image'?'image':'videocam';
  const ok=await page.evaluate(async({want,wantIcon})=>{
    const sleep=ms=>new Promise(r=>setTimeout(r,ms));
    const visible=el=>{if(!el)return false;const st=getComputedStyle(el);const r=el.getBoundingClientRect();return st.display!=='none'&&st.visibility!=='hidden'&&r.width>12&&r.height>12};
    const click=el=>{if(!el||el.getAttribute('data-state')==='active')return false;const r=el.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;['pointerdown','mousedown','pointerup','mouseup','click'].forEach(ev=>el.dispatchEvent(new MouseEvent(ev,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0})));return true};
    const xp=x=>document.evaluate(x,document,null,XPathResult.FIRST_ORDERED_NODE_TYPE,null).singleNodeValue;
    let menu=document.querySelector('[role="menu"][data-state="open"]'); if(!menu)return false;
    const direct=xp(`//button[@role='tab' and contains(@class,'flow_tab_slider_trigger') and .//i[normalize-space(text())='${wantIcon}']]`);
    if(direct){click(direct); await sleep(500); return true;}
    const labels=want==='image'?['image','photo','ảnh','hình ảnh','tạo ảnh','create image']:['video','tạo video','create video'];
    const bad=['upload','tải lên','add image','thêm ảnh','reference','ảnh ref'];
    let best=null,score=-999; for(const b of Array.from(document.querySelectorAll("button[role='tab'],[role='tab'],button,[role='button']")).filter(visible)){const icon=(b.querySelector('i')?.textContent||'').trim().toLowerCase();const txt=((b.innerText||'')+' '+(b.getAttribute('aria-label')||'')+' '+(b.getAttribute('title')||'')).toLowerCase();let sc=0;if(b.getAttribute('role')==='tab')sc+=1000;if(icon===wantIcon)sc+=800;if(labels.some(x=>txt.includes(x)))sc+=500;if(bad.some(x=>txt.includes(x)))sc-=1800;if(sc>score){score=sc;best=b}}
    if(!best||score<400)return false; click(best); await sleep(450); return true;
  },{want,wantIcon}).catch(()=>false); if(ok) await sleep(450); return ok;
}
async function applyOutputCount(page){ const c=String(count||'1'); return await clickText(page,[`x${c}`],800); }
async function applyModel(page){
  const labels={default:'Veo 3.1 - Fast',veo3_lite:'Veo 3.1 - Lite',veo3_fast:'Veo 3.1 - Fast',veo3_quality:'Veo 3.1 - Quality',nano_banana_pro:'Nano Banana Pro',nano_banana2:'Nano Banana 2',nano_banana:'Nano Banana 2',imagen4:'Imagen 4'};
  const label=labels[String(model||'default').toLowerCase()]||model; if(!label||model==='custom') return true;
  await page.evaluate(()=>{const visible=el=>{if(!el)return false;const st=getComputedStyle(el);const r=el.getBoundingClientRect();return st.display!=='none'&&st.visibility!=='hidden'&&r.width>8&&r.height>8}; const menu=document.querySelector('div[role="menu"][data-state="open"],[role="menu"][data-state="open"]'); const scope=menu||document; const triggers=Array.from(scope.querySelectorAll("button[aria-haspopup='menu']")).filter(visible); const t=triggers.find(b=>b.querySelector('div[data-type="button-overlay"]'))||triggers[triggers.length-1]; if(t)t.click();}).catch(()=>{});
  await sleep(350); return await clickText(page,[label,String(label).replaceAll('_',' ')],1800);
}
async function applyAspect(page){
  const r=String(ratio||'16:9'); if(!['16:9','9:16'].includes(r))return;
  const pats=r==='9:16'?['9:16','crop_9_16','PORTRAIT']:['16:9','crop_16_9','LANDSCAPE'];
  if(await clickText(page,pats,1200))return;
  try{ const chip=page.locator("button[aria-haspopup='menu']").nth(5); await chip.click({timeout:1500}).catch(()=>chip.click({timeout:1500,force:true})); await sleep(250); await clickText(page,pats,1500); }catch{}
}
async function applySettings(page){
  await closeMenus(page); await openMainSettings(page).catch(()=>{}); await sleep(350);
  await applyTaskMode(page).catch(e=>log('apply_task_failed:'+e.message));
  await applyModel(page).catch(e=>log('apply_model_failed:'+e.message));
  await applyAspect(page).catch(e=>log('apply_ratio_failed:'+e.message));
  await applyOutputCount(page).catch(e=>log('apply_count_failed:'+e.message));
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
