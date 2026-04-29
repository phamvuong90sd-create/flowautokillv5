import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Bot, Film, KeyRound, Pause, Play, Square, Wand2, ImagePlus, Settings, Activity } from 'lucide-react';
import './style.css';

declare global { interface Window { flowAPI: any } }

const styles = ['CINEMATIC','ANIME','PAINTING','RENDER_3D','COMIC_BOOK','PIXEL_ART','WATERCOLOR','CYBERPUNK','STEAMPUNK','NONE'];
const models = ['default','veo3_lite','veo3_fast','veo3_quality','nano_banana_pro','nano_banana2','imagen4'];
const ratios = ['16:9','9:16','square','landscape_4_3','portrait_3_4'];

function Card({title, icon, children}:{title:string; icon?:React.ReactNode; children:React.ReactNode}){return <div className="card"><div className="card-title">{icon}{title}</div>{children}</div>}
function Button({children,onClick,variant='soft'}:{children:React.ReactNode;onClick?:()=>void;variant?:'primary'|'soft'|'danger'}){return <button onClick={onClick} className={`btn ${variant}`}>{children}</button>}
function Field({label,children}:{label:string;children:React.ReactNode}){return <label className="field"><span>{label}</span>{children}</label>}

function App(){
  const [page,setPage]=useState('dashboard');
  const [apiKeys,setApiKeys]=useState('');
  const [style,setStyle]=useState('CINEMATIC');
  const [mediaType,setMediaType]=useState('VIDEO');
  const [ideas,setIdeas]=useState('');
  const [topic,setTopic]=useState('');
  const [duration,setDuration]=useState('60 seconds');
  const [mode,setMode]=useState('createvideo');
  const [model,setModel]=useState('default');
  const [ratio,setRatio]=useState('16:9');
  const [count,setCount]=useState('1');
  const [spacing,setSpacing]=useState('10');
  const [runMode,setRunMode]=useState('single');
  const [characterImages,setCharacterImages]=useState<string[]>([]);
  const [promptFile,setPromptFile]=useState('');
  const [refsDir,setRefsDir]=useState('');
  const [generatedFile,setGeneratedFile]=useState('');
  const [activity,setActivity]=useState('Sẵn sàng.');
  const [licenseText,setLicenseText]=useState('Đang kiểm tra license...');
  const [machineId,setMachineId]=useState('Đang lấy Machine ID...');
  const [licenseKey,setLicenseKey]=useState('');
  const [bootLoading,setBootLoading]=useState(true);
  const firstKey=()=>apiKeys.split(/[\n,]+/).map(s=>s.trim()).filter(Boolean)[0]||'';
  const friendly=(x:any)=>{
    if(typeof x==='string') return x;
    if(!x) return 'Không có phản hồi';
    if(x.ok===false){ const e=x.error||x.stderr||x.reason||''; if(String(e).includes('process_not_running')) return 'ℹ️ Tiến trình chưa chạy hoặc đã dừng.'; if(String(e).includes('revoked')||String(e).includes('expired')||String(e).includes('license_invalid')) return '❌ License đã hết hạn hoặc đã bị thu hồi. Các tính năng đã bị khóa.'; return `❌ ${e || 'Không kiểm tra được license. Vui lòng kiểm tra cấu hình hoặc kích hoạt lại.'}`; }
    if(x.base!==undefined && x.running!==undefined) {
      if(x.running && x.paused) return `⏸ Tiến trình đang tạm dừng${x.progress?.total?' • đã xong '+x.progress.done+'/'+x.progress.total:''}.`;
      if(x.running) return `✅ Tiến trình đang chạy${x.progress?.total?' • prompt '+Math.min(x.progress.current,x.progress.total)+'/'+x.progress.total:''}.`;
      if(x.progress?.done) return `⏹ Tiến trình đã dừng • đã xong ${x.progress.done}/${x.progress.total||'?'} prompt.`;
      return 'ℹ️ Tiến trình chưa chạy.';
    }
    if(x.paused===true) return '⏸ Đã tạm dừng. App sẽ dừng trước prompt kế tiếp.';
    if(x.paused===false && x.ok===true) return '▶ Đã tiếp tục chạy.';
    if(x.running===false) return '⏹ Đã dừng tiến trình.';
    if(x.launched||x.already) return '🌐 Chrome Flow/CDP đã sẵn sàng.';
    if(x.pid) return `✅ Đã bắt đầu chạy. PID: ${x.pid}`;
    if(x.generated?.count!==undefined) return `✅ Đã tạo ${x.generated.count} prompt.`;
    if(x.expires_at) return `✅ License hiện tại hết hạn: ${x.expires_at}${x.warning?' • đang dùng dữ liệu local':''}`;
    if(x.stdout){
      try{
        const obj=JSON.parse(x.stdout);
        if(obj.ok===false) return `❌ License không hợp lệ${obj.reason?' • '+obj.reason:''}`;
        if(obj.ok===true) return `✅ License hợp lệ${obj.expires_at?' • hết hạn: '+obj.expires_at:''}`;
      }catch{}
      return '✅ Thao tác hoàn tất.';
    }
    if(x.ok===true) return '✅ Thành công';
    return 'ℹ️ Đã cập nhật trạng thái.';
  };
  const append=(x:any)=>setActivity(`${new Date().toLocaleTimeString()}  ${friendly(x)}`);
  const nav=[['dashboard','Tổng quan',Activity],['flow','Vận hành Flow',Film],['ai','AI Prompt Studio',Wand2],['license','License',KeyRound],['settings','Cài đặt',Settings]];
  async function pickImages(){const r=await window.flowAPI.openFile({properties:['openFile','multiSelections'],filters:[{name:'Images',extensions:['jpg','jpeg','png','webp']}]}); if(r?.length){setCharacterImages(r); append(`Đã chọn ${r.length} ảnh nhân vật`)}}
  async function pickPrompt(){const r=await window.flowAPI.openFile({properties:['openFile'],filters:[{name:'Text',extensions:['txt','json']},{name:'All',extensions:['*']}]}); if(r?.[0]){setPromptFile(r[0]); append(`Prompt file: ${r[0]}`)}}
  async function pickRefs(){const r=await window.flowAPI.openFile({properties:['openDirectory']}); if(r?.[0]){setRefsDir(r[0]); append(`Ref folder: ${r[0]}`)}}
  async function generatePrompt(){append('Đang tạo prompt AI...'); const r=await window.flowAPI.generatePrompt({apiKey:firstKey(),style,mediaType,ideas}); if(r?.generated?.file)setGeneratedFile(r.generated.file); append(r)}
  async function generateScript(){append('Đang tạo kịch bản video...'); const r=await window.flowAPI.generateScript({apiKey:firstKey(),style,topic,duration,characterImages}); if(r?.generated?.file)setGeneratedFile(r.generated.file); append(r)}
  async function pause(){append(await window.flowAPI.pause())}
  async function resume(){append(await window.flowAPI.resume())}
  async function stop(){append(await window.flowAPI.stop())}
  async function checkLicense(){ const r=await window.flowAPI.licenseCheck(); const msg=friendly(r); setLicenseText(msg); append(msg); return r }
  async function activateLicense(){ const r=await window.flowAPI.activateLicense({licenseKey}); const msg=friendly(r); setLicenseText(msg); append(msg); return r }
  useEffect(()=>{ const t=setTimeout(()=>setBootLoading(false),1800); window.flowAPI.licenseCached().then((r:any)=>{ const msg=friendly(r); setLicenseText(msg); }).catch(()=>{}); window.flowAPI.machineId().then((r:any)=>{ if(r?.machineId)setMachineId(r.machineId) }).catch(()=>{}); window.flowAPI.status().then(append).catch(()=>{}); return ()=>clearTimeout(t); },[])
  async function ensureCdp(){append('Đang mở/kiểm tra Chrome CDP...'); append(await window.flowAPI.ensureCdp())}
  function runPayload(file?:string){return {promptFile:file||promptFile||generatedFile, mode, model, ratio, count, spacing, refsDir, runMode, autoDownload:true, pairedMode:true, subMode:'frames', referenceMode:'ingredients'}}
  async function start(file?:string){append('Đang bắt đầu chạy...'); append(await window.flowAPI.start(runPayload(file)))}
  async function quick(){append('Đang quick start...'); append(await window.flowAPI.start({...runPayload(), startFrom:1}))}
  return <div className="app">{bootLoading&&<div className="boot-loading"><div className="loader-card"><div className="spinner"></div><b>Đang tải ứng dụng...</b><span>FLOW AUTO VEO 3 đang khởi động, vui lòng chờ.</span></div></div>}
    <aside className="side"><div className="brand"><Bot/><div><b>FLOW AUTO VEO 3</b><span>Modern UI</span></div></div>{nav.map(([id,label,Icon]:any)=><button key={id} onClick={()=>setPage(id)} className={page===id?'active':''}><Icon size={18}/>{label}</button>)}<div className="price">100K / tháng<br/>1.200K vĩnh viễn</div></aside>
    <main className="main">
      <header><div><h1>{page==='ai'?'AI Prompt Studio':page==='flow'?'Vận hành Flow':page==='license'?'License & Đăng ký':page==='settings'?'Cài đặt':'Dashboard'}</h1><p>FLOW AUTO VEO 3 Modern UI</p></div><div className="status">{activity}</div></header>
      {page==='dashboard'&&<div className="grid"><Card title="Trạng thái" icon={<Activity/>}><p>Theo dõi trạng thái chạy, tạm dừng, tiếp tục và dừng tiến trình Flow.</p><div className="mini-status">{licenseText}</div><div className="actions"><Button onClick={async()=>append(await window.flowAPI.status())}>Kiểm tra trạng thái</Button></div></Card><Card title="Điều khiển nhanh" icon={<Play/>}><div className="actions"><Button variant="soft" onClick={pause}><Pause size={16}/> Tạm dừng</Button><Button variant="primary" onClick={resume}><Play size={16}/> Tiếp tục</Button><Button variant="danger" onClick={stop}><Square size={16}/> Stop</Button><Button onClick={quick}>⚡ Quick Start</Button></div></Card></div>}
      {page==='flow'&&<div className="grid"><Card title="Thiết lập chạy" icon={<Film/>}><div className="actions"><Button onClick={pickPrompt}>📄 Chọn file prompt</Button><Button onClick={pickRefs}>🖼 Chọn thư mục ref</Button><Button onClick={ensureCdp}>🌐 Mở Chrome Flow</Button></div><p className="hint">Prompt: {promptFile || generatedFile || 'chưa chọn'}<br/>Refs: {refsDir || 'chưa chọn'}</p><div className="form4"><Field label="Mode"><select value={mode} onChange={e=>setMode(e.target.value)}><option>createvideo</option><option>createimage</option></select></Field><Field label="Model"><select value={model} onChange={e=>setModel(e.target.value)}>{models.map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Tỉ lệ"><select value={ratio} onChange={e=>setRatio(e.target.value)}>{ratios.map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Số output"><select value={count} onChange={e=>setCount(e.target.value)}>{['1','2','3','4'].map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Giãn cách prompt"><input value={spacing} onChange={e=>setSpacing(e.target.value)}/></Field><Field label="Chế độ chạy"><select value={runMode} onChange={e=>setRunMode(e.target.value)}><option value="single">single</option><option value="continuous_submit_only">submit only liên tục</option><option value="continuous_download_delay_3">download trễ sau 3 prompt</option></select></Field></div></Card><Card title="Điều khiển" icon={<Play/>}><div className="actions"><Button variant="primary" onClick={()=>start()}><Play size={16}/> Bắt đầu</Button><Button onClick={pause}><Pause size={16}/> Tạm dừng</Button><Button variant="primary" onClick={resume}><Play size={16}/> Tiếp tục</Button><Button variant="danger" onClick={stop}><Square size={16}/> Stop</Button></div></Card></div>}
      {page==='ai'&&<div className="grid ai"><Card title="API & Prompt" icon={<Wand2/>}><Field label="Gemini API keys"><textarea className="masked" value={apiKeys} onChange={e=>setApiKeys(e.target.value)} placeholder="Dán key, mỗi dòng hoặc dấu phẩy 1 key"/></Field><div className="form4"><Field label="Style"><select value={style} onChange={e=>setStyle(e.target.value)}>{styles.map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Loại"><select value={mediaType} onChange={e=>setMediaType(e.target.value)}><option>IMAGE</option><option>VIDEO</option></select></Field><Field label="Thời lượng"><input value={duration} onChange={e=>setDuration(e.target.value)}/></Field><Field label="Giãn cách"><input value={spacing} onChange={e=>setSpacing(e.target.value)}/></Field></div><Field label="Ý tưởng thô"><textarea value={ideas} onChange={e=>setIdeas(e.target.value)} placeholder="Mỗi dòng một ý tưởng"/></Field><div className="actions"><Button variant="primary" onClick={generatePrompt}><Wand2 size={16}/> Tạo prompt AI</Button><Button onClick={pickImages}><ImagePlus size={16}/> Upload ảnh nhân vật</Button><Button onClick={generateScript}>🎬 Tạo kịch bản</Button></div><p className="hint">Đã chọn {characterImages.length} ảnh nhân vật</p></Card><Card title="Thiết lập Flow" icon={<Settings/>}><div className="form4"><Field label="Mode"><select value={mode} onChange={e=>setMode(e.target.value)}><option>createvideo</option><option>createimage</option></select></Field><Field label="Model"><select value={model} onChange={e=>setModel(e.target.value)}>{models.map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Tỉ lệ"><select value={ratio} onChange={e=>setRatio(e.target.value)}>{ratios.map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Số output"><select value={count} onChange={e=>setCount(e.target.value)}>{['1','2','3','4'].map(x=><option key={x}>{x}</option>)}</select></Field></div><div className="actions"><Button variant="primary" onClick={()=>start(generatedFile)}>▶ Chạy prompt AI</Button><Button onClick={pause}>⏸ Tạm dừng</Button><Button variant="primary" onClick={resume}>▶ Tiếp tục</Button><Button variant="danger" onClick={stop}>⏹ Stop</Button></div></Card></div>}
      {page==='license'&&<div className="grid"><Card title="License hiện tại" icon={<KeyRound/>}><div className="license-box">{licenseText}</div><Field label="Machine ID - gửi mã này cho admin để lấy key kích hoạt"><div className="machine-row"><input readOnly value={machineId}/><Button onClick={()=>{navigator.clipboard?.writeText(machineId); append('Đã copy Machine ID')}}>Copy</Button></div></Field><div className="actions"><Button variant="primary" onClick={checkLicense}>🔄 Cập nhật trạng thái license</Button></div></Card><Card title="Kích hoạt online" icon={<KeyRound/>}><p>Nhập key admin gửi để kích hoạt. API kích hoạt được cấu hình ẩn trong hệ thống.</p><Field label="License key admin gửi"><input value={licenseKey} onChange={e=>setLicenseKey(e.target.value)} placeholder="Nhập key kích hoạt"/></Field><div className="actions"><Button variant="primary" onClick={activateLicense}>🔐 Kích hoạt online</Button></div><div className="pricing"><div><b>100.000 VND</b><span>/ 1 tháng</span></div><div><b>1.200.000 VNĐ</b><span>/ vĩnh viễn</span></div></div><p>Zalo: 0989139295<br/>Telegram: https://t.me/flowautotool</p></Card></div>}
      {page==='settings'&&<div className="grid"><Card title="Cài đặt giao diện" icon={<Activity/>}><p>Thông báo kỹ thuật đã được ẩn để giao diện gọn hơn. Trạng thái app hiển thị ở thanh phía trên.</p><div className="mini-status">{activity}</div></Card></div>}
    </main>
  </div>
}

createRoot(document.getElementById('root')!).render(<App/>);
