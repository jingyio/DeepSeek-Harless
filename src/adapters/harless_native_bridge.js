/** Browser presentation only; commands remain native registry executions. */
(async () => {
  'use strict';
  const dialog=document.createElement('dialog');dialog.setAttribute('aria-label','Harless 场景与 RSI');
  dialog.style.cssText='width:min(720px,calc(100% - 32px));padding:12px;border:1px solid #ddd;border-radius:12px;';
  const close=document.createElement('button');close.textContent='关闭';close.onclick=()=>dialog.close();
  const frame=document.createElement('iframe');frame.title='Harless 选择面板';frame.style.cssText='display:block;width:100%;height:620px;border:0';
  dialog.append(close,frame);document.body.append(dialog);
  const open=document.createElement('button');open.textContent='场景 · 模式 · RSI';open.style.cssText='position:fixed;right:18px;bottom:72px;z-index:9999;padding:10px;border-radius:8px;background:white;color:#245cba;border:1px solid #245cba';
  open.onclick=()=>{frame.src='/harless';if(!dialog.open)dialog.showModal();};document.body.append(open);
  let polling=false;
  async function poll(){if(polling||document.hidden||dialog.open)return;polling=true;try{
    const response=await fetch('/api/harless/settings?panels=1',{credentials:'same-origin',cache:'no-store'});if(!response.ok)return;
    const value=await response.json(), panel=value.panels?.[0];if(!panel)return;
    frame.src='/harless?session_id='+encodeURIComponent(panel.session_id)+'&section='+encodeURIComponent(panel.section);dialog.showModal();
    await fetch('/api/harless/settings',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'dismiss_panel',session_id:panel.session_id,revision:panel.revision})});
  }finally{polling=false;}}
  await poll().catch(()=>{});const timer=setInterval(()=>poll().catch(()=>{}),1000);
  window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
})();
