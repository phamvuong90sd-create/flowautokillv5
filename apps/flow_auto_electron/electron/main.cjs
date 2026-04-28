const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn, spawnSync } = require('child_process');

const isDev = !app.isPackaged;
// Share runtime/license with stable standalone app so existing activated keys are visible.
const BASE_DIR = path.join(os.homedir(), '.flow-auto-standalone');
const FLOW_DIR = path.join(BASE_DIR, 'flow-auto');
const JOB_DIR = path.join(FLOW_DIR, 'job-state');
const DEBUG_DIR = path.join(FLOW_DIR, 'debug');
const SCRIPTS_DIR = path.join(BASE_DIR, 'scripts');
const PYENV_DIR = path.join(BASE_DIR, 'electron-python');
const REQ_FILE = path.join(BASE_DIR, 'electron-requirements.txt');
const PID_RUN = path.join(JOB_DIR, 'electron-runner.pid');
const PAUSE_FILE = path.join(JOB_DIR, 'pause.flag');
const RUN_STATE = path.join(JOB_DIR, 'electron-runner-state.json');
const CDP_PORT = 18800;
const CDP_PROFILE = path.join(BASE_DIR, 'chrome-cdp-profile');
const LICENSE_CONFIG = path.join(BASE_DIR, 'keys', 'license-online.json');

function ensureDirs(){ [BASE_DIR,FLOW_DIR,JOB_DIR,DEBUG_DIR,SCRIPTS_DIR].forEach(p=>fs.mkdirSync(p,{recursive:true})); }
function resourcePath(rel){ return app.isPackaged ? path.join(process.resourcesPath, rel) : path.join(__dirname, '..', rel); }
function appPath(rel){ return app.isPackaged ? path.join(process.resourcesPath, 'app.asar', rel) : path.join(__dirname, '..', rel); }
function bootstrap(){ ensureDirs(); const src=resourcePath('payload/scripts'); if(fs.existsSync(src)){ for(const f of fs.readdirSync(src)){ const sp=path.join(src,f); const dp=path.join(SCRIPTS_DIR,f); if(fs.statSync(sp).isFile()) fs.copyFileSync(sp,dp); } } const req=resourcePath('payload/requirements.txt'); if(fs.existsSync(req)) fs.copyFileSync(req, REQ_FILE); }
function systemPython(){ return process.platform==='win32' ? 'python' : 'python3'; }
function bundledPython(){ const base=resourcePath('payload/python/runtime'); const exe=process.platform==='win32'?path.join(base,'python.exe'):path.join(base,'bin','python3'); if(fs.existsSync(exe)) return exe; const exe2=process.platform==='win32'?path.join(base,'python.exe'):path.join(base,'bin','python'); return fs.existsSync(exe2)?exe2:''; }
function venvPython(){ return process.platform==='win32' ? path.join(PYENV_DIR,'Scripts','python.exe') : path.join(PYENV_DIR,'bin','python'); }
function ensurePythonEnv(){
  bootstrap();
  const bundled=bundledPython();
  if(bundled){
    const ok=spawnSync(bundled,['-c','import playwright, certifi'],{encoding:'utf8'}).status===0;
    if(ok) return bundled;
  }
  const py=venvPython();
  const check=()=>fs.existsSync(py) && spawnSync(py,['-c','import playwright, certifi'],{encoding:'utf8'}).status===0;
  if(check()) return py;
  fs.mkdirSync(PYENV_DIR,{recursive:true});
  let r=spawnSync(systemPython(), ['-m','venv',PYENV_DIR], {encoding:'utf8'});
  if(r.status!==0) throw new Error(r.stderr||r.stdout||'python venv failed');
  r=spawnSync(py, ['-m','pip','install','-U','pip'], {encoding:'utf8'});
  if(r.status!==0) throw new Error(r.stderr||r.stdout||'pip upgrade failed');
  const req=fs.existsSync(REQ_FILE)?REQ_FILE:resourcePath('payload/requirements.txt');
  r=spawnSync(py, ['-m','pip','install','-r',req], {encoding:'utf8'});
  if(r.status!==0) throw new Error(r.stderr||r.stdout||'pip install requirements failed');
  return py;
}
function spawnOpts(extra={}){ return {cwd:BASE_DIR, env:{...process.env,FLOW_WORKSPACE:BASE_DIR,FLOW_PAUSE_FILE:PAUSE_FILE}, windowsHide:true, ...extra}; }
function runScript(script,args=[]){ return new Promise((resolve)=>{ bootstrap(); let p, py; try{ py=ensurePythonEnv(); p=spawn(py, [path.join(SCRIPTS_DIR,script), ...args], spawnOpts()); }catch(e){ resolve({ok:false,error:String(e)}); return; } let out='',err=''; p.stdout.on('data',d=>out+=d); p.stderr.on('data',d=>err+=d); p.on('error',e=>resolve({ok:false,error:String(e)})); p.on('close',code=>resolve({ok:code===0, code, stdout:out.trim(), stderr:err.trim()})); }); }

function machineId(){
  try{
    if(process.platform==='win32'){
      const out=require('child_process').execFileSync('powershell',['-NoProfile','-ExecutionPolicy','Bypass','-Command',"$x=''; try{$x=(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography' -Name MachineGuid -ErrorAction Stop).MachineGuid}catch{}; if([string]::IsNullOrWhiteSpace($x)){try{$x=(Get-CimInstance Win32_ComputerSystemProduct -ErrorAction SilentlyContinue).UUID}catch{}}; if([string]::IsNullOrWhiteSpace($x)){$x=$env:COMPUTERNAME}; $x.ToString().Trim().ToLower()"],{encoding:'utf8'}).trim();
      if(out) return out.toLowerCase();
    }
  }catch{}
  if(process.platform==='darwin'){
    try{ const out=require('child_process').execFileSync('ioreg',['-rd1','-c','IOPlatformExpertDevice'],{encoding:'utf8'}); const m=out.match(/"IOPlatformUUID"\s*=\s*"([^"]+)"/); if(m) return m[1].toLowerCase(); }catch{}
  }
  if(process.platform==='linux'){
    try{ const v=fs.readFileSync('/etc/machine-id','utf8').trim(); if(v) return v.toLowerCase(); }catch{}
  }
  return os.hostname().toLowerCase();
}
function licenseApiBase(){ try{ const cfg=JSON.parse(fs.readFileSync(LICENSE_CONFIG,'utf8')); return cfg.api_base||''; }catch{return ''} }


function loadLicenseCfg(){ try{return JSON.parse(fs.readFileSync(LICENSE_CONFIG,'utf8'))}catch{return {}} }
function saveLicenseCfg(cfg){ fs.mkdirSync(path.dirname(LICENSE_CONFIG),{recursive:true}); fs.writeFileSync(LICENSE_CONFIG,JSON.stringify(cfg,null,2),'utf8'); }
function normalizeBase(b){ b=String(b||'').trim().replace(/\/+$/,''); if(b.endsWith('/activate')||b.endsWith('/verify')) b=b.replace(/\/[^\/]+$/,''); return b; }
async function postJson(url,payload){ const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); let data={}; try{data=await r.json()}catch{} return {status:r.status,data}; }
async function verifyLicenseJs(){ const cfg=loadLicenseCfg(); const base=normalizeBase(cfg.api_base||''); if(!base) return {ok:false,reason:'missing_api_base'}; if(!cfg.license_key) return {ok:false,reason:'missing_license_key'}; cfg.machine_id=cfg.machine_id||machineId(); const payload={license_key:cfg.license_key,machine_id:cfg.machine_id,app_version:'V2.0',nonce:Date.now().toString(36),timestamp:new Date().toISOString().replace(/\.\d{3}Z$/,'Z')}; if(cfg.signed_token) payload.signed_token=cfg.signed_token; try{ const {status,data}=await postJson(`${base}/verify`,payload); if(status===200 && data.valid){ ['signed_token','expires_at','grace_until','next_check_at'].forEach(k=>{if(data[k])cfg[k]=data[k]}); cfg.last_verified_at=payload.timestamp; saveLicenseCfg(cfg); return {ok:true,expires_at:data.expires_at||cfg.expires_at,data}; } return {ok:false,reason:data.reason||`http_${status}`,data}; }catch(e){ return {ok:false,reason:`network_error:${e.message||e}`}; }}

const STYLE_SUFFIX={CINEMATIC:'photorealistic, cinematic lighting, 8k, highly detailed',ANIME:'anime style, vibrant colors, detailed background',PAINTING:'digital painting, concept art, masterpiece',RENDER_3D:'3d render, unreal engine 5, octane render',COMIC_BOOK:'comic book style, bold outlines, high contrast',PIXEL_ART:'pixel art, 16-bit, retro gaming style',WATERCOLOR:'watercolor painting, soft edges, dreamy',CYBERPUNK:'cyberpunk style, neon lights, futuristic city',STEAMPUNK:'steampunk style, brass gears, victorian retro futuristic',NONE:''};
async function geminiText(apiKey,parts,system,jsonMode=false){ const models=['gemini-2.5-flash','gemini-2.0-flash','gemini-1.5-flash']; let last=''; for(const m of models){ try{ const body={contents:[{role:'user',parts}],systemInstruction:{parts:[{text:system}]},generationConfig:{temperature:.7}}; if(jsonMode) body.generationConfig.responseMimeType='application/json'; const r=await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${m}:generateContent?key=${apiKey}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const obj=await r.json().catch(()=>({})); if(!r.ok){ last=obj.error?.message||`http_${r.status}`; continue; } return (obj.candidates?.[0]?.content?.parts||[]).map(p=>p.text||'').join('\n').trim(); }catch(e){last=String(e)} } throw new Error(last||'gemini_failed'); }
function splitIdeas(t){return String(t||'').split(/\n+/).map(x=>x.trim()).filter(Boolean)}
function writeGenerated(name,prompts){ const file=path.join(JOB_DIR,name); fs.writeFileSync(file,prompts.map(x=>String(x).replace(/\s+/g,' ').trim()).filter(Boolean).join('\n\n')+'\n','utf8'); return {file,count:prompts.length,prompts}; }
async function generatePromptsJs(payload){ const apiKey=payload.apiKey||''; const style=payload.style||'CINEMATIC'; const media=payload.mediaType||'IMAGE'; const sys=`Bạn là chuyên gia prompt. Chỉ trả về prompt tiếng Anh đã tối ưu. Style: ${STYLE_SUFFIX[style]||''}. Media: ${media}.`; const results=[]; for(const idea of splitIdeas(payload.ideas)){ const prompt=await geminiText(apiKey,[{text:idea}],sys,false); results.push(prompt); } return {ok:true,generated:writeGenerated('electron-ai-generated-prompts.txt',results)}; }
function durationScenes(d){ const s=String(d||'60 seconds').toLowerCase(); let sec=0; let m=s.match(/(\d+)\s*(m|minute|phút)/); if(m)sec+=Number(m[1])*60; m=s.match(/(\d+)\s*(s|second|giây)/); if(m)sec+=Number(m[1]); if(!sec){m=s.match(/^(\d+)$/); if(m)sec=Number(m[1])*60;} return Math.max(1,Math.ceil((sec||60)/8)); }
async function generateScriptJs(payload){ const n=durationScenes(payload.duration); const sys=`Tạo JSON kịch bản video gồm đúng ${n} scenes. Mỗi scene có sceneNumber,duration,description,prompt tiếng Anh chi tiết. Chỉ trả JSON {title,characterSheet,scenes:[...]}. Style: ${STYLE_SUFFIX[payload.style]||''}`; const txt=await geminiText(payload.apiKey,[{text:`Chủ đề: ${payload.topic}. Tổng cảnh: ${n}.`}],sys,true); const obj=JSON.parse(txt.replace(/^```json\s*|```$/g,'')); const prompts=(obj.scenes||[]).sort((a,b)=>(a.sceneNumber||0)-(b.sceneNumber||0)).map(s=>s.prompt).filter(Boolean); return {ok:true,generated:writeGenerated('electron-ai-script-prompts.txt',prompts)}; }

async function activateLicenseJs(key,api){ const cfg=loadLicenseCfg(); cfg.api_base=normalizeBase(api||cfg.api_base||''); cfg.license_key=String(key||'').trim(); cfg.machine_id=machineId(); if(!cfg.api_base) return {ok:false,error:'missing_api_base'}; if(!cfg.license_key) return {ok:false,error:'missing_license_key'}; const payload={license_key:cfg.license_key,machine_id:cfg.machine_id,app_version:'V2.0',nonce:Date.now().toString(36),timestamp:new Date().toISOString().replace(/\.\d{3}Z$/,'Z')}; try{ const {status,data}=await postJson(`${cfg.api_base}/activate`,payload); if(status===200 && data.valid!==false){ ['signed_token','expires_at','grace_until','next_check_at'].forEach(k=>{if(data[k])cfg[k]=data[k]}); cfg.last_verified_at=payload.timestamp; saveLicenseCfg(cfg); return {ok:true,expires_at:data.expires_at||cfg.expires_at,data}; } return {ok:false,error:data.reason||`http_${status}`,data}; }catch(e){ return {ok:false,error:`network_error:${e.message||e}`}; }}

function cachedLicense(){ try{ const cfg=JSON.parse(fs.readFileSync(LICENSE_CONFIG,'utf8')); if(cfg.expires_at) return {ok:true, cached:true, expires_at:cfg.expires_at}; if(cfg.license_key) return {ok:true, cached:true, reason:'Đã có key local nhưng chưa có thời hạn'}; }catch{} return null; }
function readPid(){ try{return Number(fs.readFileSync(PID_RUN,'utf8').trim())}catch{return 0} }
function isRunningPid(pid){ if(!pid) return false; try{ process.kill(pid,0); return true; }catch{return false;} }
function runState(){ let progress=null; try{ const st=JSON.parse(fs.readFileSync(RUN_STATE,'utf8')); progress={done:st.done||0,total:st.total||0,current:Math.min((st.done||0)+1, st.total||0)}; }catch{} const pid=readPid(); const running=isRunningPid(pid); if(pid && !running){ try{fs.rmSync(PID_RUN,{force:true})}catch{} } return {pid: running?pid:0, running, paused:fs.existsSync(PAUSE_FILE), progress}; }
function parseJsonMaybe(txt){ try{return JSON.parse(txt||'{}')}catch{return null} }
async function onlineLicenseGuard(){ const r=await verifyLicenseJs(); if(r.ok) return {ok:true,license:r}; return {ok:false,error:r.reason||r.error||'license_invalid_or_revoked'}; }
function killPid(pid){ if(!pid)return; try{ if(process.platform==='win32') spawn('taskkill',['/PID',String(pid),'/F'],{windowsHide:true}); else process.kill(pid,'SIGTERM'); }catch{} }
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
  const p=spawn(exe,args,{detached:true,stdio:'ignore',windowsHide:true}); p.unref();
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
  args.push(payload.pairedMode===false?'--no-paired-mode':'--paired-mode'); if(payload.autoDownload!==false) args.push('--auto-download'); if(payload.runMode==='continuous_submit_only') args.push('--submit-only'); if(payload.runMode==='continuous_download_delay_3') args.push('--download-delay-prompts','3'); if(payload.refsDir) args.push('--refs-dir',payload.refsDir);
  const runner=appPath('electron/runner/flowRunner.cjs'); const env={...process.env,FLOW_WORKSPACE:BASE_DIR,FLOW_PAUSE_FILE:PAUSE_FILE,ELECTRON_RUN_AS_NODE:'1'}; const jsArgs=[runner,...args.slice(1)]; const p=spawn(process.execPath, jsArgs, {cwd:BASE_DIR, detached:true, stdio:['ignore',out,out], env, windowsHide:true}); p.unref(); fs.writeFileSync(PID_RUN,String(p.pid)); return {ok:true,pid:p.pid,logFile,promptFile,runner:'node-playwright-js'};
}

function createWindow(){
  const win = new BrowserWindow({ width: 1280, height: 820, minWidth: 1100, minHeight: 720, backgroundColor:'#07111f', title:'FLOW AUTO VEO 3 Modern', webPreferences:{ preload:path.join(__dirname,'preload.cjs'), contextIsolation:true, nodeIntegration:false }});
  if(isDev) win.loadURL('http://127.0.0.1:5173'); else win.loadFile(path.join(__dirname,'..','dist','index.html'));
}

app.whenReady().then(()=>{ ensureDirs(); createWindow(); setTimeout(()=>{ try{ bootstrap(); }catch{} }, 1200); });
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
ipcMain.handle('license:machineId', async()=>({ok:true,machineId:machineId()}));
ipcMain.handle('license:cached', async()=>cachedLicense() || {ok:false, reason:'missing_local_license'});
ipcMain.handle('license:activate', async(_e,payload)=>activateLicenseJs(payload?.licenseKey, payload?.apiBase||licenseApiBase()));
ipcMain.handle('license:check', async()=>{ const r=await verifyLicenseJs(); if(r.ok) return r; const cached=cachedLicense(); if(cached) return {...cached, warning:r.reason||r.error||'online_check_failed'}; return r; });
ipcMain.handle('prompt:generate', async(_e,payload)=>{ const lic=await onlineLicenseGuard(); if(!lic.ok) return lic; return generatePromptsJs(payload||{}); });
ipcMain.handle('prompt:script', async(_e,payload)=>{ const lic=await onlineLicenseGuard(); if(!lic.ok) return lic; return generateScriptJs(payload||{}); });
