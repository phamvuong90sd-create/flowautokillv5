const fs=require('fs'); const path=require('path');
const { chromium } = require('playwright-core');
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
const arg=(name,def='')=>{const i=process.argv.indexOf(name);return i>=0?process.argv[i+1]:def};
const has=(name)=>process.argv.includes(name);
const stateFile=arg('--state'); const promptsFile=arg('--prompts'); const cdp=arg('--cdp','http://127.0.0.1:18800');
const pauseFile=process.env.FLOW_PAUSE_FILE||'';
function log(s){ console.log(`[flow-js] ${s}`); }
function save(done,total,current=''){ if(stateFile) fs.writeFileSync(stateFile,JSON.stringify({done,total,current,updated_at:new Date().toISOString()},null,2)); }
function prompts(){ const t=fs.readFileSync(promptsFile,'utf8'); return t.split(/\n\s*\n/g).map(x=>x.trim()).filter(Boolean); }
async function findFlowPage(browser){ for(const ctx of browser.contexts()){ for(const p of ctx.pages()){ if((p.url()||'').includes('labs.google')||(p.url()||'').includes('flow')) return p; }} const ctx=browser.contexts()[0]||await browser.newContext(); return await ctx.newPage(); }
async function closeMenus(page){ try{await page.keyboard.press('Escape'); await sleep(150); await page.keyboard.press('Escape');}catch{} }
async function findInput(page){ const sels=['textarea','[contenteditable="true"]','div[role="textbox"]']; for(const s of sels){ const loc=page.locator(s).last(); try{ await loc.waitFor({timeout:2500}); return loc; }catch{} } throw new Error('Không tìm thấy ô nhập prompt'); }
async function fillPrompt(page,text){ const box=await findInput(page); await box.click({timeout:5000}); await page.keyboard.press(process.platform==='darwin'?'Meta+A':'Control+A'); await page.keyboard.type(text,{delay:1}); }
async function clickSubmit(page){ const sels=['button[aria-label*="Submit" i]','button[aria-label*="Create" i]','button[aria-label*="Generate" i]','button:has-text("Submit")','button:has-text("Create")','button:has-text("Generate")']; for(const s of sels){ const b=page.locator(s).last(); try{ if(await b.count()){ await b.click({timeout:3000}); return; }}catch{} } await page.keyboard.press('Enter'); }
async function applySettings(page){ /* placeholder: Python parity will be ported incrementally; Flow often remembers last settings. */ await closeMenus(page); }
async function run(){ const list=prompts(); let done=0; save(0,list.length); const browser=await chromium.connectOverCDP(cdp); const page=await findFlowPage(browser); if(!page.url().includes('labs.google')) await page.goto('https://labs.google/fx/tools/flow'); await page.bringToFront();
 for(let i=0;i<list.length;i++){ while(pauseFile&&fs.existsSync(pauseFile)){ log('paused'); await sleep(1000); } save(i,list.length,list[i].slice(0,80)); await applySettings(page); await fillPrompt(page,list[i]); await clickSubmit(page); done=i+1; save(done,list.length); await sleep(Number(arg('--between-prompts-sec','10'))*1000); }
 await browser.close().catch(()=>{}); save(done,list.length); }
run().catch(e=>{ console.error(e.stack||String(e)); process.exit(1); });
