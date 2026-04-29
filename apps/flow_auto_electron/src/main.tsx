import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Bot, Film, KeyRound, Pause, Play, Square, Wand2, ImagePlus, CreditCard, Scissors, Music } from 'lucide-react';
import './style.css';

declare global { interface Window { flowAPI: any } }

const styles = ['CINEMATIC','ANIME','PAINTING','RENDER_3D','COMIC_BOOK','PIXEL_ART','WATERCOLOR','CYBERPUNK','STEAMPUNK','NONE'];
const models = ['default','veo3_lite','veo3_fast','veo3_quality','nano_banana_pro','nano_banana2','imagen4'];
const ratios = ['16:9','9:16','square','landscape_4_3','portrait_3_4'];

function Card({title, icon, children}:{title:string; icon?:React.ReactNode; children:React.ReactNode}){return <div className="card"><div className="card-title">{icon}{title}</div>{children}</div>}
function Button({children,onClick,variant='soft'}:{children:React.ReactNode;onClick?:()=>void;variant?:'primary'|'soft'|'danger'}){return <button onClick={onClick} className={`btn ${variant}`}>{children}</button>}
function Field({label,children}:{label:string;children:React.ReactNode}){return <label className="field"><span>{label}</span>{children}</label>}

function App(){
  const [page,setPage]=useState('flow');
  const [apiKeys,setApiKeys]=useState(localStorage.getItem('gemini_api_keys')||'');
  const [style,setStyle]=useState('CINEMATIC');
  const [mediaType,setMediaType]=useState('VIDEO');
  const [ideas,setIdeas]=useState('');
  const [topic,setTopic]=useState('');
  const [durationValue,setDurationValue]=useState('60');
  const [durationUnit,setDurationUnit]=useState<'seconds'|'minutes'>('seconds');
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
  const [lang,setLang]=useState(localStorage.getItem('flow_lang')||'VI');
  const [langNotice,setLangNotice]=useState(false);
  const [videoFolder,setVideoFolder]=useState('');
  const [videoFiles,setVideoFiles]=useState<string[]>([]);
  const [audioFile,setAudioFile]=useState('');
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
  const T=(vi:string,en:string)=>lang==='EN'?en:vi;
  const nav=[['flow',T('Vận hành Flow','Flow Operation'),Film],['ai','AI Prompt Studio',Wand2],['post',T('Hậu kì video','Video Post-production'),Scissors],['payment',T('Thanh toán','Payment'),CreditCard],['license','License',KeyRound]];
  async function pickImages(){const r=await window.flowAPI.openFile({properties:['openFile','multiSelections'],filters:[{name:'Images',extensions:['jpg','jpeg','png','webp']}]}); if(r?.length){setCharacterImages(r); append(`Đã chọn ${r.length} ảnh nhân vật`)}}
  async function pickPrompt(){const r=await window.flowAPI.openFile({properties:['openFile'],filters:[{name:'Text',extensions:['txt','json']},{name:'All',extensions:['*']}]}); if(r?.[0]){setPromptFile(r[0]); append(`Prompt file: ${r[0]}`)}}
  async function pickRefs(){const r=await window.flowAPI.openFile({properties:['openDirectory']}); if(r?.[0]){setRefsDir(r[0]); append(`Ref folder: ${r[0]}`)}}
  async function pickVideoFolder(){const r=await window.flowAPI.openFile({properties:['openDirectory']}); if(r?.[0]){setVideoFolder(r[0]); const x=await window.flowAPI.videoList(r[0]); setVideoFiles(x?.files||[]); append(`Đã chọn thư mục video: ${r[0]}`)}}
  async function pickAudio(){const r=await window.flowAPI.openFile({properties:['openFile'],filters:[{name:'Audio',extensions:['mp3','wav','m4a','aac']},{name:'All',extensions:['*']} ]}); if(r?.[0]){setAudioFile(r[0]); append(`Audio: ${r[0]}`)}}
  async function mergeVideos(){append('Đang ghép video...'); append(await window.flowAPI.videoMerge({folder:videoFolder,files:videoFiles}))}
  async function extractAudio(){append('Đang tách âm thanh...'); append(await window.flowAPI.videoExtractAudio({file:videoFiles[0]}))}
  async function generatePrompt(){append('Đang tạo prompt AI...'); const r=await window.flowAPI.generatePrompt({apiKey:firstKey(),style,mediaType,ideas}); if(r?.generated?.file)setGeneratedFile(r.generated.file); append(r)}
  async function generateScript(){append('Đang tạo kịch bản video...'); const duration=`${durationValue} ${durationUnit}`; const r=await window.flowAPI.generateScript({apiKey:firstKey(),style,topic,duration,characterImages}); if(r?.generated?.file)setGeneratedFile(r.generated.file); append(r)}
  async function pause(){append('⏸ Đang tạm dừng tiến trình...'); const r=await window.flowAPI.pause(); append(r); setTimeout(()=>window.flowAPI.status().then(append).catch(()=>{}),500)}
  async function resume(){append('▶ Đang tiếp tục tiến trình...'); const r=await window.flowAPI.resume(); append(r); setTimeout(()=>window.flowAPI.status().then(append).catch(()=>{}),500)}
  async function stop(){append(await window.flowAPI.stop())}
  async function checkLicense(){ const r=await window.flowAPI.licenseCheck(); const msg=friendly(r); setLicenseText(msg); append(msg); return r }
  async function activateLicense(){ const r=await window.flowAPI.activateLicense({licenseKey}); const msg=friendly(r); setLicenseText(msg); append(msg); return r }
  useEffect(()=>{ const t=setTimeout(()=>setBootLoading(false),1800); window.flowAPI.licenseCached().then((r:any)=>{ const msg=friendly(r); setLicenseText(msg); }).catch(()=>{}); window.flowAPI.machineId().then((r:any)=>{ if(r?.machineId)setMachineId(r.machineId) }).catch(()=>{}); window.flowAPI.status().then(append).catch(()=>{}); return ()=>clearTimeout(t); },[])
  async function ensureCdp(){append('Đang mở/kiểm tra Chrome CDP...'); append(await window.flowAPI.ensureCdp())}
  function runPayload(file?:string){return {promptFile:file||promptFile||generatedFile, mode, model, ratio, count, spacing, refsDir, runMode, autoDownload:true, pairedMode:true, subMode:'frames', referenceMode:'ingredients'}}
  async function start(file?:string){append('Đang bắt đầu chạy...'); append(await window.flowAPI.start(runPayload(file)))}
  async function quick(){append('Đang quick start...'); append(await window.flowAPI.start({...runPayload(), startFrom:1}))}
  return <div className="app">{bootLoading&&<div className="boot-loading"><div className="loader-card"><div className="spinner"></div><b>Đang tải ứng dụng...</b><span>FLOW AUTO VEO 3 đang khởi động, vui lòng chờ.</span></div></div>}{langNotice&&<div className="modal-backdrop"><div className="small-modal"><b>{T('Đã đổi ngôn ngữ','Language changed')}</b><p>{T('Vui lòng khởi động lại app để áp dụng đầy đủ cài đặt ngôn ngữ.','Please restart the app to fully apply the language setting.')}</p><Button variant="primary" onClick={()=>setLangNotice(false)}>OK</Button></div></div>}
    <aside className="side"><div className="brand"><Bot/><div><b>FLOW AUTO VEO 3</b><span>Modern UI</span></div></div><div className="lang-switch"><button type="button" className={lang==='VI'?'active':''} onClick={(e)=>{e.preventDefault();e.stopPropagation();switchLang('VI')}}>VI</button><button type="button" className={lang==='EN'?'active':''} onClick={(e)=>{e.preventDefault();e.stopPropagation();switchLang('EN')}}>EN</button></div>{nav.map(([id,label,Icon]:any)=><button key={id} onClick={()=>setPage(id)} className={page===id?'active':''}><Icon size={18}/>{label}</button>)}<div className="price">{T('100K / tháng','100K / month')}<br/>{T('1.200K vĩnh viễn','1.200K lifetime')}</div></aside>
    <main className="main">
      <header><div><h1>{page==='ai'?'AI Prompt Studio':page==='flow'?T('Vận hành Flow','Flow Operation'):page==='license'?T('License & Đăng ký','License & Activation'):page==='payment'?T('Thanh toán','Payment'):page==='post'?T('Hậu kì video','Video Post-production'):'FLOW AUTO VEO 3'}</h1><p>FLOW AUTO VEO 3 Modern UI</p></div><div className="header-actions"><div className="status">{activity}</div><div className="lang-switch header-lang"><button type="button" className={lang==='VI'?'active':''} onClick={(e)=>{e.preventDefault();switchLang('VI')}}>VI</button><button type="button" className={lang==='EN'?'active':''} onClick={(e)=>{e.preventDefault();switchLang('EN')}}>EN</button></div></div></header>
      {page==='flow'&&<div className="grid"><Card title="Thiết lập chạy" icon={<Film/>}><div className="actions"><Button onClick={pickPrompt}>📄 Chọn file prompt</Button><Button onClick={pickRefs}>🖼 Chọn thư mục ref</Button><Button onClick={ensureCdp}>🌐 Mở Chrome Flow</Button></div><p className="hint">Prompt: {promptFile || generatedFile || 'chưa chọn'}<br/>Refs: {refsDir || 'chưa chọn'}</p><div className="form4"><Field label="Mode"><select value={mode} onChange={e=>setMode(e.target.value)}><option>createvideo</option><option>createimage</option></select></Field><Field label="Model"><select value={model} onChange={e=>setModel(e.target.value)}>{models.map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Tỉ lệ"><select value={ratio} onChange={e=>setRatio(e.target.value)}>{ratios.map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Số output"><select value={count} onChange={e=>setCount(e.target.value)}>{['1','2','3','4'].map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Giãn cách prompt"><input value={spacing} onChange={e=>setSpacing(e.target.value)}/></Field><Field label="Chế độ chạy"><select value={runMode} onChange={e=>setRunMode(e.target.value)}><option value="single">single</option><option value="continuous_submit_only">submit only liên tục</option><option value="continuous_download_delay_3">download trễ sau 3 prompt</option></select></Field></div></Card><Card title="Điều khiển" icon={<Play/>}><div className="actions"><Button variant="primary" onClick={()=>start()}><Play size={16}/> Bắt đầu</Button><Button onClick={pause}><Pause size={16}/> Tạm dừng</Button><Button variant="primary" onClick={resume}><Play size={16}/> Tiếp tục</Button><Button variant="danger" onClick={stop}><Square size={16}/> Stop</Button></div></Card></div>}
      {page==='ai'&&<div className="grid ai"><Card title="API & Prompt" icon={<Wand2/>}><Field label="Gemini API keys"><textarea className="masked" value={apiKeys} onChange={e=>setApiKeys(e.target.value)} placeholder="Dán key, mỗi dòng hoặc dấu phẩy 1 key"/></Field><div className="form4"><Field label="Style"><select value={style} onChange={e=>setStyle(e.target.value)}>{styles.map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Loại"><select value={mediaType} onChange={e=>setMediaType(e.target.value)}><option>IMAGE</option><option>VIDEO</option></select></Field><Field label="Thời lượng"><div className="duration-row"><input value={durationValue} onChange={e=>setDurationValue(e.target.value.replace(/[^0-9]/g,''))} placeholder="60"/><select value={durationUnit} onChange={e=>setDurationUnit(e.target.value as any)}><option value="seconds">Giây</option><option value="minutes">Phút</option></select></div></Field><Field label="Giãn cách"><input value={spacing} onChange={e=>setSpacing(e.target.value)}/></Field></div><Field label="Ý tưởng thô"><textarea value={ideas} onChange={e=>setIdeas(e.target.value)} placeholder="Mỗi dòng một ý tưởng"/></Field><div className="actions"><Button onClick={saveApiConfig}>💾 Lưu cấu hình API</Button><Button onClick={pickImages}><ImagePlus size={16}/> Upload ảnh nhân vật</Button><Button variant="primary" onClick={generateScript}>🎬 Tạo kịch bản</Button></div><p className="hint">Đã chọn {characterImages.length} ảnh nhân vật</p></Card><Card title="Thiết lập Flow" icon={<Film/>}><div className="form4"><Field label="Mode"><select value={mode} onChange={e=>setMode(e.target.value)}><option>createvideo</option><option>createimage</option></select></Field><Field label="Model"><select value={model} onChange={e=>setModel(e.target.value)}>{models.map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Tỉ lệ"><select value={ratio} onChange={e=>setRatio(e.target.value)}>{ratios.map(x=><option key={x}>{x}</option>)}</select></Field><Field label="Số output"><select value={count} onChange={e=>setCount(e.target.value)}>{['1','2','3','4'].map(x=><option key={x}>{x}</option>)}</select></Field></div><div className="actions"><Button variant="primary" onClick={()=>start(generatedFile)}>▶ Chạy prompt AI</Button><Button onClick={pause}>⏸ Tạm dừng</Button><Button variant="primary" onClick={resume}>▶ Tiếp tục</Button><Button variant="danger" onClick={stop}>⏹ Stop</Button></div></Card></div>}
      {page==='post'&&<div className="grid"><Card title="Chọn thư mục video" icon={<Film/>}><div className="actions"><Button onClick={pickVideoFolder}>📁 Chọn thư mục chứa video</Button><Button onClick={async()=>{if(videoFolder){const x=await window.flowAPI.videoList(videoFolder); setVideoFiles(x?.files||[]); append('Đã làm mới danh sách video')}}}>🔄 Làm mới</Button></div><p className="hint">Thư mục: {videoFolder||'chưa chọn'}<br/>Số video: {videoFiles.length}</p><div className="video-list">{videoFiles.map((f,i)=><div key={f} className="video-item"><b>{String(i+1).padStart(2,'0')}</b><span>{f.split(/[\\/]/).pop()}</span></div>)}</div></Card><Card title="Công cụ hậu kì" icon={<Scissors/>}><p>Ghép nối, cắt, chèn hiệu ứng, chèn âm thanh và tách âm thanh video gốc.</p><div className="actions"><Button variant="primary" onClick={mergeVideos}>🎞 Ghép toàn bộ video</Button><Button onClick={extractAudio}>🎧 Tách âm video đầu tiên</Button><Button onClick={pickAudio}><Music size={16}/> Chọn âm thanh chèn</Button></div><p className="hint">Audio chèn: {audioFile||'chưa chọn'}</p><div className="timeline"><div>Timeline preview</div><div className="track video">Video track</div><div className="track audio">Audio track</div><div className="track fx">Effect / transition track</div></div><p className="hint">Các nút cắt, kéo thả timeline, hiệu ứng nâng cao và chèn audio sẽ được nối vào engine FFmpeg ở bước tiếp theo.</p></Card></div>}
      {page==='payment'&&<div className="payment-page payment-single"><Card title={T('Thanh toán','Payment')} icon={<CreditCard/>}><div className="pay-info single"><div className="pay-block"><h3>USDT ETH</h3><p><b>{T('Người nhận','Receiver')}:</b> PHAM VAN VUONG</p><p><b>100.000 VNĐ / 1 Tháng</b><br/><b>5 USDT / 1 Tháng</b><br/><b>1.200.000 VNĐ / Vĩnh Viễn</b><br/><b>50 USDT / Vĩnh Viễn</b></p><p><b>{T('Ví USDT mạng ETH','USDT wallet on ETH network')}:</b><br/><code>0xcbcf357d5d2f5165c544d0ba1d520dbaaaef11c7</code></p><p>{T('Nội dung chuyển khoản','Transfer note')}: <b>FLOWAUTO + SĐT</b></p></div><div className="pay-contact"><b>{T('Hỗ trợ cấp key','Key/support contact')}</b><br/>Zalo: 0989139295<br/>Telegram: https://t.me/flowautotool<br/><span>{T('Sau khi thanh toán, gửi Machine ID cho admin để nhận key.','After payment, send Machine ID to admin to receive your key.')}</span></div></div></Card><Card title="QR USDT ETH - PHAM VAN VUONG" icon={<CreditCard/>}><img className="qr qr-huge" src="assets/subscription_qr.png"/></Card></div>}
            {page==='license'&&<div className="grid"><Card title="License hiện tại" icon={<KeyRound/>}><div className="license-box">{licenseText}</div><Field label="Machine ID - gửi mã này cho admin để lấy key kích hoạt"><div className="machine-row"><input readOnly value={machineId}/><Button onClick={()=>{navigator.clipboard?.writeText(machineId); append('Đã copy Machine ID')}}>Copy</Button></div></Field><div className="actions"><Button variant="primary" onClick={checkLicense}>🔄 Cập nhật trạng thái license</Button></div></Card><Card title="Kích hoạt online" icon={<KeyRound/>}><p>Nhập key admin gửi để kích hoạt. API kích hoạt được cấu hình ẩn trong hệ thống.</p><Field label="License key admin gửi"><input value={licenseKey} onChange={e=>setLicenseKey(e.target.value)} placeholder="Nhập key kích hoạt"/></Field><div className="actions"><Button variant="primary" onClick={activateLicense}>🔐 Kích hoạt online</Button></div><div className="pricing"><div><b>100.000 VND</b><span>/ 1 tháng</span></div><div><b>1.200.000 VNĐ</b><span>/ vĩnh viễn</span></div></div><p>Zalo: 0989139295<br/>Telegram: https://t.me/flowautotool</p></Card></div>}

    </main>
  </div>
}

createRoot(document.getElementById('root')!).render(<App/>);
