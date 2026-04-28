const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn } = require('child_process');

const isDev = !app.isPackaged;
// Share runtime/license with stable standalone app so existing activated keys are visible.
const BASE_DIR = path.join(os.homedir(), '.flow-auto-standalone');
const FLOW_DIR = path.join(BASE_DIR, 'flow-auto');
const JOB_DIR = path.join(FLOW_DIR, 'job-state');
const DEBUG_DIR = path.join(FLOW_DIR, 'debug');
const SCRIPTS_DIR = path.join(BASE_DIR, 'scripts');
const PID_RUN = path.join(JOB_DIR, 'electron-runner.pid');
const PAUSE_FILE = path.join(JOB_DIR, 'pause.flag');
const RUN_STATE = path.join(JOB_DIR, 'electron-runner-state.json');
const CDP_PORT = 18800;
const CDP_PROFILE = path.join(BASE_DIR, 'chrome-cdp-profile');
const LICENSE_CONFIG = path.join(BASE_DIR, 'keys', 'license-online.json');

function ensureDirs(){ [BASE_DIR,FLOW_DIR,JOB_DIR,DEBUG_DIR,SCRIPTS_DIR].forEach(p=>fs.mkdirSync(p,{recursive:true})); }
function resourcePath(rel){ return app.isPackaged ? path.join(process.resourcesPath, rel) : path.join(__dirname, '..', rel); }
function bootstrap(){ ensureDirs(); const src=resourcePath('payload/scripts'); if(fs.existsSync(src)){ for(const f of fs.readdirSync(src)){ const sp=path.join(src,f); const dp=path.join(SCRIPTS_DIR,f); if(fs.statSync(sp).isFile()) fs.copyFileSync(sp,dp); } } }
function pythonCmd(){ return process.platform==='win32' ? 'python' : 'python3'; }
function runScript(script,args=[]){ return new Promise((resolve)=>{ bootstrap(); let p; try{ p=spawn(pythonCmd(), [path.join(SCRIPTS_DIR,script), ...args], {cwd:BASE_DIR, env:{...process.env,FLOW_WORKSPACE:BASE_DIR,FLOW_PAUSE_FILE:PAUSE_FILE}}); }catch(e){ resolve({ok:false,error:String(e)}); return; } let out='',err=''; p.stdout.on('data',d=>out+=d); p.stderr.on('data',d=>err+=d); p.on('error',e=>resolve({ok:false,error:String(e)})); p.on('close',code=>resolve({ok:code===0, code, stdout:out.trim(), stderr:err.trim()})); }); }
function cachedLicense(){ try{ const cfg=JSON.parse(fs.readFileSync(LICENSE_CONFIG,'utf8')); if(cfg.expires_at) return {ok:true, cached:true, expires_at:cfg.expires_at}; if(cfg.license_key) return {ok:true, cached:true, reason:'Đã có key local nhưng chưa có thời hạn'}; }catch{} return null; }
function readPid(){ try{return Number(fs.readFileSync(PID_RUN,'utf8').trim())}catch{return 0} }
function isRunningPid(pid){ if(!pid) return false; try{ process.kill(pid,0); return true; }catch{return false;} }
function runState(){ let progress=null; try{ const st=JSON.parse(fs.readFileSync(RUN_STATE,'utf8')); progress={done:st.done||0,total:st.total||0,current:Math.min((st.done||0)+1, st.total||0)}; }catch{} const pid=readPid(); const running=isRunningPid(pid); if(pid && !running){ try{fs.rmSync(PID_RUN,{force:true})}catch{} } return {pid: running?pid:0, running, paused:fs.existsSync(PAUSE_FILE), progress}; }
function parseJsonMaybe(txt){ try{return JSON.parse(txt||'{}')}catch{return null} }
async function onlineLicenseGuard(){ const r=await runScript('flow_license_online_check.py',['--check','--json']); const obj=parseJsonMaybe(r.stdout)||parseJsonMaybe(r.stderr)||{}; if(r.ok && obj.ok!==false) return {ok:true, license:obj}; return {ok:false, error: obj.reason || obj.error || r.stderr || r.error || 'license_invalid_or_revoked'}; }
function killPid(pid){ if(!pid)return; try{ if(process.platform==='win32') spawn('taskkill',['/PID',String(pid),'/F']); else process.kill(pid,'SIGTERM'); }catch{} }
function chromeCandidates(){
  if(process.platform==='win32') return [
    path.join(process.env['PROGRAMFILES']||'C:/Program Files','Google/Chrome/Application/chrome.exe'),
    path.join(process.env['PROGRAMFILES(X86)']||'C:/Program Files (x86)','Google/Chrome/Application/chrome.exe'),
    path.join(process.env['LOCALAPPDATA']||'', 'Google/Chrome/Application/chrome.exe'),
    path.join(process.env['PROGRAMFILES']||'C:/Program Files','Microsoft/Edge/Application/msedge.exe')];
  if(process.platform==='darwin') return ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'];
  return ['/usr/bin/google-chrome','/usr/bin/chromium-browser','/usr/bin/chromium','/snap/bin/chromium','/usr/bin/microsoft-edge'];
}
function wait(ms){return new Promise(r=>setTimeout(r,ms));}
async function ensureCdp(){
  try{ const r=await fetch(`http://127.0.0.1:${CDP_PORT}/json/version`); if(r.ok) return {ok:true, already:true}; }catch{}
  fs.mkdirSync(CDP_PROFILE,{recursive:true});
  const exe=chromeCandidates().find(x=>x && fs.existsSync(x));
  if(!exe) return {ok:false,error:'chrome_not_found'};
  const args=[`--remote-debugging-port=${CDP_PORT}`,`--user-data-dir=${CDP_PROFILE}`,'--no-first-run','--no-default-browser-check','https://labs.google/fx/tools/flow'];
  const p=spawn(exe,args,{detached:true,stdio:'ignore'}); p.unref();
  for(let i=0;i<40;i++){ try{ const r=await fetch(`http://127.0.0.1:${CDP_PORT}/json/version`); if(r.ok) return {ok:true, launched:true}; }catch{} await wait(500); }
  return {ok:false,error:'cdp_not_ready'};
}
function writePromptFile(name, text){ ensureDirs(); const file=path.join(JOB_DIR,name); const blocks=(text||'').split(/\n\s*\n/).map(x=>x.trim()).filter(Boolean); fs.writeFileSync(file, blocks.join('\n\n')+'\n','utf8'); return file; }
function saveGeneratedPrompts(jsonPath, fallbackText, outName){
  let prompts=[]; try{ const obj=JSON.parse(fs.readFileSync(jsonPath,'utf8')); if(obj.results) prompts=obj.results.filter(r=>r.ok&&r.prompt).map(r=>String(r.prompt).replace(/\s+/g,' ').trim()); if(obj.script?.scenes) prompts=obj.script.scenes.sort((a,b)=>(a.sceneNumber||0)-(b.sceneNumber||0)).map(s=>String(s.prompt||'').replace(/\s+/g,' ').trim()).filter(Boolean); }catch{}
  if(!prompts.length && fallbackText) prompts=(fallbackText||'').split(/\n\s*\n/).map(x=>x.trim()).filter(Boolean);
  const out=path.join(JOB_DIR,outName); fs.writeFileSync(out,prompts.join('\n\n')+'\n','utf8'); return {file:out,count:prompts.length,prompts};
}
function startRunner(payload){
  ensureDirs(); try{fs.rmSync(PAUSE_FILE,{force:true})}catch{}
  const promptFile=payload.promptFile || writePromptFile('electron-manual-prompts.txt', payload.prompts||'');
  const logFile=path.join(DEBUG_DIR,'electron-runner.log'); const out=fs.openSync(logFile,'a');
  const args=['flow_batch_runner.py','--prompts',promptFile,'--state',RUN_STATE,'--start-from',String(payload.startFrom||1),'--cdp',`http://127.0.0.1:${CDP_PORT}`,'--task-mode',payload.mode||'createvideo','--video-sub-mode',payload.subMode||'frames','--reference-mode',payload.referenceMode||'ingredients','--flow-model',payload.model||'default','--flow-aspect-ratio',payload.ratio||'16:9','--flow-count',String(payload.count||1),'--download-resolution','720','--between-prompts-sec',String(payload.spacing||10)];
  args.push(payload.pairedMode===false?'--no-paired-mode':'--paired-mode'); if(payload.autoDownload!==false) args.push('--auto-download'); if(payload.refsDir) args.push('--refs-dir',payload.refsDir);
  const p=spawn(pythonCmd(), [path.join(SCRIPTS_DIR,args[0]), ...args.slice(1)], {cwd:BASE_DIR, detached:true, stdio:['ignore',out,out], env:{...process.env,FLOW_WORKSPACE:BASE_DIR,FLOW_PAUSE_FILE:PAUSE_FILE}}); p.unref(); fs.writeFileSync(PID_RUN,String(p.pid)); return {ok:true,pid:p.pid,logFile,promptFile,args};
}

function createWindow(){
  const win = new BrowserWindow({ width: 1280, height: 820, minWidth: 1100, minHeight: 720, backgroundColor:'#07111f', title:'FLOW AUTO VEO 3 Modern', webPreferences:{ preload:path.join(__dirname,'preload.cjs'), contextIsolation:true, nodeIntegration:false }});
  if(isDev) win.loadURL('http://127.0.0.1:5173'); else win.loadFile(path.join(__dirname,'..','dist','index.html'));
}

app.whenReady().then(()=>{ bootstrap(); createWindow(); });
app.on('window-all-closed',()=>{ if(process.platform!=='darwin') app.quit(); });
app.on('activate',()=>{ if(BrowserWindow.getAllWindows().length===0) createWindow(); });

ipcMain.handle('dialog:openFile', async (_e, opts={})=>{ const r=await dialog.showOpenDialog({properties:opts.properties||['openFile'], filters:opts.filters||[]}); return r.canceled?[]:r.filePaths; });
ipcMain.handle('shell:openPath', (_e,p)=>shell.openPath(p));
ipcMain.handle('flow:status', async()=>runState());
ipcMain.handle('flow:ensureCdp', async()=>ensureCdp());
ipcMain.handle('flow:start', async(_e,payload)=>{ const lic=await onlineLicenseGuard(); if(!lic.ok) return lic; const c=await ensureCdp(); if(!c.ok) return c; return startRunner(payload||{}); });
ipcMain.handle('flow:pause', async()=>{ const st=runState(); if(!st.running) return {ok:false,error:'process_not_running'}; ensureDirs(); fs.writeFileSync(PAUSE_FILE,String(Date.now())); return {ok:true, paused:true}; });
ipcMain.handle('flow:resume', async()=>{ const st=runState(); if(!st.running) return {ok:false,error:'process_not_running'}; try{fs.rmSync(PAUSE_FILE,{force:true})}catch{} return {ok:true, paused:false}; });
ipcMain.handle('flow:stop', async()=>{ const pid=readPid(); killPid(pid); try{fs.rmSync(PID_RUN,{force:true});fs.rmSync(PAUSE_FILE,{force:true})}catch{} return {ok:true, running:false}; });
ipcMain.handle('license:check', async()=>{ const r=await runScript('flow_license_online_check.py',['--check','--json']); if(r.ok) return r; const cached=cachedLicense(); if(cached) return {...cached, warning:r.error||r.stderr||'online_check_failed'}; return r; });
ipcMain.handle('prompt:generate', async(_e,payload)=>{
  const lic=await onlineLicenseGuard(); if(!lic.ok) return lic;
  const inFile=path.join(JOB_DIR,'electron-ai-ideas.txt'); const outFile=path.join(JOB_DIR,'electron-ai-prompts.json'); fs.writeFileSync(inFile,payload.ideas||'', 'utf8');
  const r=await runScript('prompt_master_ai.py',['--mode','refine','--api-key',payload.apiKey||'', '--style',payload.style||'CINEMATIC','--media-type',payload.mediaType||'IMAGE','--input-file',inFile,'--output-file',outFile]);
  if(r.ok) r.generated=saveGeneratedPrompts(outFile,'','electron-ai-generated-prompts.txt'); return r;
});
ipcMain.handle('prompt:script', async(_e,payload)=>{
  const lic=await onlineLicenseGuard(); if(!lic.ok) return lic;
  const outFile=path.join(JOB_DIR,'electron-ai-script.json');
  const args=['--mode','script','--api-key',payload.apiKey||'', '--style',payload.style||'CINEMATIC','--topic',payload.topic||'','--duration',payload.duration||'60 seconds','--output-file',outFile];
  if(payload.characterImages) args.push('--character-images', payload.characterImages.join(path.delimiter));
  const r=await runScript('prompt_master_ai.py',args); if(r.ok) r.generated=saveGeneratedPrompts(outFile,'','electron-ai-script-prompts.txt'); return r;
});
