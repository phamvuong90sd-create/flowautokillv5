const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn } = require('child_process');

const isDev = !app.isPackaged;
const BASE_DIR = path.join(os.homedir(), '.flow-auto-electron');
const FLOW_DIR = path.join(BASE_DIR, 'flow-auto');
const JOB_DIR = path.join(FLOW_DIR, 'job-state');
const DEBUG_DIR = path.join(FLOW_DIR, 'debug');
const SCRIPTS_DIR = path.join(BASE_DIR, 'scripts');
const PID_RUN = path.join(JOB_DIR, 'electron-runner.pid');
const PAUSE_FILE = path.join(JOB_DIR, 'pause.flag');

function ensureDirs(){ [BASE_DIR,FLOW_DIR,JOB_DIR,DEBUG_DIR,SCRIPTS_DIR].forEach(p=>fs.mkdirSync(p,{recursive:true})); }
function resourcePath(rel){ return app.isPackaged ? path.join(process.resourcesPath, rel) : path.join(__dirname, '..', rel); }
function bootstrap(){ ensureDirs(); const src=resourcePath('payload/scripts'); if(fs.existsSync(src)){ for(const f of fs.readdirSync(src)){ const sp=path.join(src,f); const dp=path.join(SCRIPTS_DIR,f); if(fs.statSync(sp).isFile()) fs.copyFileSync(sp,dp); } } }
function pythonCmd(){ return process.platform==='win32' ? 'python' : 'python3'; }
function runScript(script,args=[]){ return new Promise((resolve)=>{ bootstrap(); const p=spawn(pythonCmd(), [path.join(SCRIPTS_DIR,script), ...args], {cwd:BASE_DIR, env:{...process.env,FLOW_WORKSPACE:BASE_DIR,FLOW_PAUSE_FILE:PAUSE_FILE}}); let out='',err=''; p.stdout.on('data',d=>out+=d); p.stderr.on('data',d=>err+=d); p.on('close',code=>resolve({ok:code===0, code, stdout:out.trim(), stderr:err.trim()})); }); }
function readPid(){ try{return Number(fs.readFileSync(PID_RUN,'utf8').trim())}catch{return 0} }
function killPid(pid){ if(!pid)return; try{ if(process.platform==='win32') spawn('taskkill',['/PID',String(pid),'/F']); else process.kill(pid,'SIGTERM'); }catch{} }

function createWindow(){
  const win = new BrowserWindow({ width: 1280, height: 820, minWidth: 1100, minHeight: 720, backgroundColor:'#07111f', title:'FLOW AUTO VEO 3 Modern', webPreferences:{ preload:path.join(__dirname,'preload.cjs'), contextIsolation:true, nodeIntegration:false }});
  if(isDev) win.loadURL('http://127.0.0.1:5173'); else win.loadFile(path.join(__dirname,'..','dist','index.html'));
}

app.whenReady().then(()=>{ bootstrap(); createWindow(); });
app.on('window-all-closed',()=>{ if(process.platform!=='darwin') app.quit(); });
app.on('activate',()=>{ if(BrowserWindow.getAllWindows().length===0) createWindow(); });

ipcMain.handle('dialog:openFile', async (_e, opts={})=>{ const r=await dialog.showOpenDialog({properties:opts.properties||['openFile'], filters:opts.filters||[]}); return r.canceled?[]:r.filePaths; });
ipcMain.handle('shell:openPath', (_e,p)=>shell.openPath(p));
ipcMain.handle('flow:status', async()=>({base:BASE_DIR, running:!!readPid(), paused:fs.existsSync(PAUSE_FILE)}));
ipcMain.handle('flow:pause', async()=>{ ensureDirs(); fs.writeFileSync(PAUSE_FILE,String(Date.now())); return {ok:true, paused:true}; });
ipcMain.handle('flow:resume', async()=>{ try{fs.rmSync(PAUSE_FILE,{force:true})}catch{} return {ok:true, paused:false}; });
ipcMain.handle('flow:stop', async()=>{ const pid=readPid(); killPid(pid); try{fs.rmSync(PID_RUN,{force:true});fs.rmSync(PAUSE_FILE,{force:true})}catch{} return {ok:true, running:false}; });
ipcMain.handle('license:check', async()=>runScript('flow_license_online_check.py',['--check','--json']));
ipcMain.handle('prompt:generate', async(_e,payload)=>{
  const inFile=path.join(JOB_DIR,'electron-ai-ideas.txt'); const outFile=path.join(JOB_DIR,'electron-ai-prompts.json'); fs.writeFileSync(inFile,payload.ideas||'', 'utf8');
  return runScript('prompt_master_ai.py',['--mode','refine','--api-key',payload.apiKey||'', '--style',payload.style||'CINEMATIC','--media-type',payload.mediaType||'IMAGE','--input-file',inFile,'--output-file',outFile]);
});
ipcMain.handle('prompt:script', async(_e,payload)=>{
  const outFile=path.join(JOB_DIR,'electron-ai-script.json');
  const args=['--mode','script','--api-key',payload.apiKey||'', '--style',payload.style||'CINEMATIC','--topic',payload.topic||'','--duration',payload.duration||'60 seconds','--output-file',outFile];
  if(payload.characterImages) args.push('--character-images', payload.characterImages.join(path.delimiter));
  return runScript('prompt_master_ai.py',args);
});
