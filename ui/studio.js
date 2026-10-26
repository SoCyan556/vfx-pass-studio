'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const motionPreference=matchMedia('(prefers-reduced-motion: reduce)');
  let reduced=motionPreference.matches;
  motionPreference.addEventListener('change',event=>{reduced=event.matches;});
  const passes = [
    {key:'normal',name:'Normal',icon:'scan',tone:'#9b7aff'},
    {key:'basecolor',name:'Base Color',icon:'palette',tone:'#c79b78'},
    {key:'roughness',name:'Roughness',icon:'circle-dashed',tone:'#a6a3b0'},
    {key:'specular',name:'Specular',icon:'gem',tone:'#ddd9eb'},
    {key:'metallic',name:'Metallic',icon:'orbit',tone:'#8b93af'},
    {key:'depth',name:'Depth',icon:'layers-2',tone:'#b7b0c3'},
    {key:'alpha',name:'Alpha',icon:'scan-face',tone:'#e7e4ef'},
    {key:'source',name:'Source',icon:'film',tone:'#a28eb8'}
  ];
  const options = {
    materials:[['SuperMat estimates','SuperMat','Local material model'],['AI estimates','Marigold','Legacy estimate'],['Uniform values','Uniform values','Adjustable constants']],
    basecolor:[['Source colors','Source colors','Preserve artwork'],['AI albedo','AI albedo','Experimental estimate']],
    quality:[['AI materials + normals','AI materials + normals','Full inference'],['Fast draft','Fast draft','Quick iteration']],
    size:[['512','512 px','Fast preview'],['720','720 px','Compact'],['1080','1080 px','Balanced'],['1920','1920 px','Full HD'],['0','Original resolution','No resize']],
    fps:[['','Source frame rate','Preserve timing'],['24','24 fps','Cinema'],['24000/1001','23.976 fps','Cinema'],['25','25 fps','PAL'],['30','30 fps','Standard'],['30000/1001','29.97 fps','NTSC'],['60','60 fps','Smooth']],
    alpha:[['Anime subject','Anime subject','AI matte'],['General subject','General subject','AI matte'],['Source alpha','Source alpha','Preserve transparency'],['External matte','External matte','Use a matte video'],['Full frame','Full frame','Opaque']],
    processing:[['256','256 px','Fast'],['512','512 px','Balanced'],['768','768 px','Detailed']],
    pass:passes.map(p=>[p.key,p.name,p.key==='source'?'Original footage':''])
  };
  let api, settings={}, clip=null, video=null, currentPass='normal', frame=0, playing=false, expanded=false;
  let exporting=false, progressValue=0, progressStarted=0, elapsedTimer=null, progressReturn=null;
  let busy=false, starting=false, imageFront='a', requestId=0, playbackToken=0, lastPoll=false;
  let menuTrigger=null, menuKey=null, activeOption=0, drawerReturn=null, modalReturn=null;
  const frameCache=new Map(), pendingFrames=new Map();
  const icons=(root=document)=>window.lucide?.createIcons({root,attrs:{'stroke-width':1.65}});
  const escape=(value)=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon=(name,extra='')=>`<i data-lucide="${name}" ${extra}></i>`;
  const wait=(ms)=>new Promise(r=>setTimeout(r,ms));
  const time=(seconds)=>`${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
  const preciseTime=(seconds)=>`${time(seconds)}.${String(Math.floor((seconds%1)*100)).padStart(2,'0')}`;
  const log=(text)=>{const el=$('activity-log');el.textContent=(el.textContent+'\n'+text).split('\n').slice(-100).join('\n');el.scrollTop=el.scrollHeight;};

  function toast(message,error=false){
    const el=document.createElement('div');el.className='toast'+(error?' error':'');
    el.innerHTML=icon(error?'circle-alert':'check-check')+`<p>${escape(message)}</p>`;
    $('toasts').append(el);icons();setTimeout(()=>{el.classList.add('leaving');setTimeout(()=>el.remove(),400);},5500);
  }
  async function call(method,...args){
    if(!api){toast('Open the desktop launcher to use local files.',true);return null;}
    try{const result=await api[method](...args);if(result?.error)toast(result.error,true);return result;}
    catch(error){log(String(error));toast('That action could not finish. Check Activity for details.',true);return null;}
  }
  function renderCards(){
    $('pass-cards').innerHTML=passes.map((p,i)=>`<button class="pass-card${p.key===currentPass?' selected':''}" data-pass="${p.key}" aria-label="View ${p.name} pass" aria-pressed="${p.key===currentPass}" style="--tone:${p.tone};--order:${i}"><span class="pass-thumb"><span class="thumb-placeholder">${icon(p.icon)}</span><img alt="${p.name} pass thumbnail" draggable="false" hidden></span><span>${p.name}</span></button>`).join('');
    for(const card of document.querySelectorAll('.pass-card')){
      card.addEventListener('click',()=>choosePass(card.dataset.pass));
      card.addEventListener('pointermove',e=>{if(reduced)return;const r=card.getBoundingClientRect();card.style.setProperty('--tilt-x',`${(e.clientX-r.left-r.width/2)/r.width*7}deg`);card.style.setProperty('--tilt-y',`${-(e.clientY-r.top-r.height/2)/r.height*7}deg`);});
      card.addEventListener('pointerleave',()=>{card.style.setProperty('--tilt-x','0deg');card.style.setProperty('--tilt-y','0deg');});
    }
    icons();requestAnimationFrame(moveSelection);
  }
  function moveSelection(){
    const selected=document.querySelector('.pass-card.selected'), indicator=$('pass-selection');
    if(!selected){indicator.style.opacity=0;return;}indicator.style.opacity=1;
    // offset coordinates do not include hover transforms, so the indicator stays on the grid.
    const holder=$('pass-cards');indicator.style.left=`${holder.offsetLeft+selected.offsetLeft}px`;
    indicator.style.top=`${holder.offsetTop+selected.offsetTop}px`;indicator.style.width=`${selected.offsetWidth}px`;indicator.style.height=`${selected.offsetHeight}px`;
  }
  async function getFrame(pass,index,width=1400){
    if(!clip)return null;
    const key=`${clip.path}|${pass}|${index}|${width}`;
    if(frameCache.has(key))return frameCache.get(key);
    if(pendingFrames.has(key))return pendingFrames.get(key);
    const promise=api.frame(pass,index,width).then(data=>{pendingFrames.delete(key);if(data){frameCache.set(key,data);if(frameCache.size>80)frameCache.delete(frameCache.keys().next().value);}return data;}).catch(()=>{pendingFrames.delete(key);return null;});
    pendingFrames.set(key,promise);return promise;
  }
  async function thumbnails(index=0){
    const path=clip?.path;
    await Promise.all(passes.map(async p=>{
      const data=await getFrame(p.key,index,256);if(!data||clip?.path!==path)return;
      const img=document.querySelector(`[data-pass="${p.key}"] .pass-thumb img`);
      if(img){img.src=data;img.hidden=false;img.previousElementSibling.hidden=true;}
    }));
  }
  function updateTimeline(){
    const count=clip?.count||1,fps=clip?.fps||24;
    const percent=count>1?frame/(count-1)*100:0;
    $('timeline-fill').style.width=`${percent}%`;$('timeline-thumb').style.left=`${percent}%`;
    $('scrubber').value=frame;$('current-time').textContent=count/fps<1?preciseTime(frame/fps):time(frame/fps);
    $('duration').textContent=count/fps<1?preciseTime(count/fps):time(count/fps);$('frame-counter').textContent=`FRAME ${String(frame+1).padStart(3,'0')}`;
  }
  async function showFrame(index,transition=false){
    if(!clip)return;
    frame=Math.max(0,Math.min(clip.count-1,index));updateTimeline();
    const id=++requestId,pass=currentPass,data=await getFrame(pass,frame);
    if(!data||id!==requestId||pass!==currentPass)return;
    const front=$(`image-${imageFront}`),back=$(`image-${imageFront==='a'?'b':'a'}`);
    if(!transition){front.src=data;front.alt=`${passes.find(p=>p.key===pass).name} pass, frame ${frame+1}`;return;}
    back.src=data;back.alt=`${passes.find(p=>p.key===pass).name} pass preview`;
    try{await back.decode();}catch{}if(id!==requestId)return;
    $('stage').classList.add('switching');back.classList.add('active');front.classList.remove('active');
    imageFront=imageFront==='a'?'b':'a';setTimeout(()=>$('stage').classList.remove('switching'),550);
  }
  function choosePass(key){
    if(!passes.some(p=>p.key===key))return;
    currentPass=key;
    const pass=passes.find(p=>p.key===key);
    $('stage').dataset.pass=key;$('pass-label').textContent=pass.name.toUpperCase();
    document.querySelector('[data-select="pass"]>span').textContent=pass.name;
    for(const card of document.querySelectorAll('.pass-card')){const active=card.dataset.pass===key;card.classList.toggle('selected',active);card.setAttribute('aria-pressed',String(active));}
    moveSelection();showFrame(frame,true);
  }
  function setScreen(screen){
    if(screen==='setup')stopPlayback();
    document.body.dataset.screen=screen;
    $('resume-preview').hidden=!clip;
    requestAnimationFrame(moveSelection);
  }
  async function loadClip(data,reveal=true){
    if(!data)return;
    stopPlayback();clip=data;frame=0;frameCache.clear();pendingFrames.clear();requestId++;
    $('shot-name').textContent=data.name;$('shot-name').title=data.name;
    $('resolution-badge').textContent=`${data.width} × ${data.height}`;
    $('demo-badge').hidden=!data.demo;$('viewer-empty').hidden=true;
    $('stage').classList.add('has-preview');$('stage').dataset.pass=currentPass;
    $('scrubber').max=Math.max(0,data.count-1);$('scrubber').disabled=data.count<2;
    $('play').disabled=data.count<2;$('center-play').hidden=data.count<2;
    await Promise.all([showFrame(0,true),thumbnails()]);
    $('resume-preview').hidden=false;if(reveal)setScreen('preview');
    // Warm adjacent full-size frames, rather than blocking playback on an entire clip.
    for(let n=1;n<Math.min(data.count,4);n++)getFrame(currentPass,n);
  }
  function stopPlayback(){playing=false;playbackToken++;document.body.classList.remove('playing');$('play').innerHTML=icon('play','fill="currentColor"');$('play').setAttribute('aria-label','Play preview');icons();}
  async function togglePlayback(){
    if(!clip||clip.count<2){toast('Load a generated clip to preview its passes.');return;}
    if(playing){stopPlayback();return;}
    playing=true;document.body.classList.add('playing');$('play').innerHTML=icon('pause','fill="currentColor"');$('play').setAttribute('aria-label','Pause preview');icons();
    const token=++playbackToken;
    let nextAt=performance.now();
    while(playing&&token===playbackToken){
      const index=(frame+1)%clip.count;
      await getFrame(currentPass,index);
      if(!playing||token!==playbackToken)break;
      await showFrame(index,false);
      getFrame(currentPass,(index+1)%clip.count);
      nextAt+=1000/clip.fps;
      const delay=nextAt-performance.now();
      if(delay>0)await wait(delay);else nextAt=performance.now();
    }
  }
  function receiveVideo(result){
    $('dropzone').classList.remove('dragging');
    if(!result||result.error){if(result?.error)toast(result.error,true);return;}
    video=result.video;settings.alpha=result.alpha;setScreen('setup');
    $('dropzone').classList.add('has-file');$('drop-copy').hidden=true;$('file-selected').hidden=false;
    $('file-name').textContent=video.name;$('file-name').title=video.path;
    let fps=video.fps;const values=String(fps).split('/');fps=Number(values[0])/(Number(values[1])||1);
    $('file-meta').textContent=`${video.width} × ${video.height} · ${fps.toFixed(3).replace(/\.?0+$/,'')} fps · ${video.duration.toFixed(1)}s`;
    $('browse-label').textContent='Change File';log(`${video.name} is ready to generate.`);
    syncSelectLabels();if(!reduced)$('dropzone').animate([{boxShadow:'0 0 0 4px #f1435555'},{boxShadow:'0 0 0 0px #f1435500'}],{duration:800,easing:'ease-out'});
  }
  function syncSelectLabels(){
    for(const key of ['quality','alpha','processing','basecolor','materials']){
      const selected=options[key].find(o=>String(o[0])===String(settings[key]));
      for(const el of document.querySelectorAll(`[data-select="${key}"]>span`))el.textContent=selected?.[1]||String(settings[key]);
    }
    $('uniform-parameters').hidden=settings.quality!=='Fast draft'&&settings.materials!=='Uniform values';
    document.body.classList.toggle('draft-mode',settings.quality==='Fast draft');
  }
  function gather(){
    settings.size=$('size').value||'0';settings.fps=$('fps').value.trim();
    for(const key of ['steps','temporal','specular','roughness','metallic'])settings[key]=Number($(key).value);
    return {...settings};
  }
  function updateSettings(){
    $('size').value=settings.size??1080;$('fps').value=settings.fps||'';
    for(const key of ['steps','temporal','specular','roughness','metallic']){
      $(key).value=settings[key];updateSlider(key);
    }
    $('output-path').textContent=settings.output||'Choose export folder';
    $('matte-name').textContent=settings.matte?settings.matte.split(/[\\/]/).pop():'Choose external matte';syncSelectLabels();
  }
  function updateSlider(key){
    const el=$(key),value=Number(el.value),min=Number(el.min),max=Number(el.max);
    el.style.setProperty('--progress',`${(value-min)/(max-min)*100}%`);
    $(`${key}-value`).textContent=key==='steps'?String(value):key==='temporal'?`${Math.round(value*100)}%`:value.toFixed(2);
  }
  function setBusy(value){
    busy=value;document.body.classList.toggle('is-generating',value);
    $('workspace').inert=value;$('generation-overlay').hidden=!value;
    $('generate').disabled=value;$('preview').disabled=value;$('browse').disabled=value;
    $('generate-label').textContent='Generate passes';
    if(value){
      progressReturn=document.activeElement;$('toasts').replaceChildren();stopPlayback();progressValue=0;progressStarted=performance.now();
      $('mini-progress').style.width='0%';$('phase-percent').textContent='0%';$('phase-label').textContent='Preparing';
      $('progress-track').setAttribute('aria-valuenow','0');
      $('progress-frames').textContent='Preparing…';$('progress-elapsed').textContent='0:00 elapsed';
      document.querySelectorAll('[data-progress-stage]').forEach(e=>{e.classList.remove('done','active');});
      clearInterval(elapsedTimer);elapsedTimer=setInterval(()=>{$('progress-elapsed').textContent=time((performance.now()-progressStarted)/1000)+' elapsed';},1000);
      $('cancel').disabled=false;$('cancel').focus();
    }else{clearInterval(elapsedTimer);progressReturn?.focus();}
  }
  function updateProgress(event){
    if(Number.isFinite(event.progress))progressValue=Math.max(progressValue,Math.min(event.phase==='Complete'?1:.999,event.progress));
    const percent=Math.floor(progressValue*100);
    $('mini-progress').style.width=`${percent}%`;$('phase-percent').textContent=`${percent}%`;
    $('progress-track').setAttribute('aria-valuenow',String(percent));
    $('phase-label').textContent=event.phase==='Export'?'Finalizing':event.phase||'Preparing';
    $('progress-frames').textContent=event.total?`${event.current} / ${event.total} frames completed`:event.indeterminate?'Loading…':'Finalizing';
    const stages={'Decode':0,'Motion':0,'Alpha':1,'Alpha stabilization':1,'Depth':2,'Depth stabilization':2,'Depth export':2,'Normals':2,'Normals stabilization':2,'Materials':3,'SuperMat materials':3,'Draft materials':3,'Export':4,'Complete':5};
    const index=stages[event.phase]??0;
    document.querySelectorAll('[data-progress-stage]').forEach(el=>{const n=Number(el.dataset.progressStage);el.classList.toggle('done',n<index);el.classList.toggle('active',n===index);});
  }
  function setExporting(value){
    exporting=value;$('export-passes').disabled=value;$('new-clip').disabled=value;
    $('export-label').textContent=value?'Exporting…':'Export passes';
    if(!value)$('export-meter').style.width='0%';
  }
  async function exportPasses(){
    if(!clip||exporting||busy)return;
    setExporting(true);const result=await call('export_passes');
    if(!result?.ok)setExporting(false);
  }
  async function generate(preview=false){
    if(busy||starting)return;
    if(!video){toast('Choose a source video first.',true);if(!reduced)$('dropzone').animate([{transform:'translateX(0)'},{transform:'translateX(-5px)'},{transform:'translateX(5px)'},{transform:'translateX(0)'}],{duration:350});return;}
    starting=true;closeMenu();setBusy(true);
    const result=await call('start',gather(),preview);starting=false;
    if(!result?.ok)setBusy(false);
    else {log(preview?'Starting 8-frame preview.':'Starting full clip.');log('Local generation started. Your footage stays on this machine.');}
  }
  async function poll(){
    if(!api||lastPoll)return;lastPoll=true;
    try{
      const result=await api.poll();
      for(const event of result.events||[]){
        if(event.type==='complete'){
          updateProgress({progress:1,phase:'Complete',message:'All passes generated',current:event.package.count,total:event.package.count});
          await loadClip(event.package);await wait(reduced?0:250);setBusy(false);
          log('Your passes are ready. Choose Export passes to save a ZIP.');
          toast('Your passes are ready to preview and export.');celebrate();$('export-passes').focus();
        }else if(event.type==='export_progress'){
          $('export-meter').style.width=`${Math.floor(event.progress*100)}%`;
          $('export-label').textContent=`Exporting ${Math.floor(event.progress*100)}%`;
        }else if(event.type==='export_complete'){
          setExporting(false);log(`Saved to ${event.path}`);toast('Export saved: '+event.path);
        }else if(event.type==='export_error'){
          setExporting(false);toast(event.message,true);
        }else if(event.type==='error'||event.type==='cancelled'){
          setBusy(false);setScreen('setup');log(event.type==='cancelled'?'Generation cancelled. Your source is ready to try again.':event.message);
          toast(event.type==='cancelled'?'Generation cancelled.':event.message,event.type==='error');
        }else{
          updateProgress(event);log(event.message);
        }
        if(event.message)log(event.message);
      }
    }catch(error){log(String(error));}finally{lastPoll=false;}
  }
  function celebrate(){
    if(reduced)return;
    $('pass-strip').animate([{boxShadow:'0 0 0 1px #ff617a99,0 0 55px #ee2b4622'},{boxShadow:'0 0 0 1px #ff617a00,0 0 0 #ee2b4600'}],{duration:1700,easing:'ease-out'});
    document.querySelectorAll('.pass-card').forEach((el,i)=>el.animate([{transform:'translateY(0)'},{transform:'translateY(-9px)',offset:.4},{transform:'translateY(0)'}],{duration:650,delay:i*55,easing:'cubic-bezier(.22,1,.36,1)'}));
  }
  function closeMenu(){
    if(menuTrigger){menuTrigger.setAttribute('aria-expanded','false');menuTrigger.removeAttribute('aria-controls');}
    $('popover').hidden=true;menuTrigger=null;menuKey=null;
  }
  function selectOption(key,value){
    if(key==='pass')choosePass(value);
    else {settings[key]=value;if(key==='size')$('size').value=value;if(key==='fps')$('fps').value=value;syncSelectLabels();call('save_settings',gather());}
    const returnTo=menuTrigger;closeMenu();returnTo?.focus();
  }
  function openMenu(trigger){
    if(menuTrigger===trigger){closeMenu();return;}
    closeMenu();const key=trigger.dataset.select;if(busy&&key!=='pass')return;
    menuTrigger=trigger;menuKey=key;trigger.setAttribute('aria-expanded','true');trigger.setAttribute('aria-controls','popover');
    const list=$('popover'),current=key==='pass'?currentPass:settings[key];
    list.innerHTML=options[key].map(([value,label,description],i)=>`<button role="option" aria-selected="${String(value)===String(current)}" class="popover-option${String(value)===String(current)?' selected':''}${value==='source'?' source-option':''}" data-value="${escape(value)}" style="--i:${i}"><span>${escape(label)}</span>${String(value)===String(current)?icon('check'):''}</button>`).join('');
    list.hidden=false;list.style.animation='none';void list.offsetWidth;list.style.animation='';
    const rect=trigger.getBoundingClientRect();list.style.width=`${Math.max(200,rect.width)}px`;list.style.left=`${Math.min(rect.left,innerWidth-Math.max(200,rect.width)-14)}px`;
    const menuHeight=list.offsetHeight;list.style.top=`${rect.bottom+menuHeight+14>innerHeight?Math.max(12,rect.top-menuHeight-7):rect.bottom+7}px`;
    activeOption=Math.max(0,options[key].findIndex(o=>String(o[0])===String(current)));
    for(const button of list.querySelectorAll('button'))button.addEventListener('click',()=>selectOption(key,button.dataset.value));icons();
  }
  function openSettings(){
    closeMenu();drawerReturn=document.activeElement;
    $('drawer-backdrop').hidden=false;$('settings-drawer').hidden=false;
    $('drawer-backdrop').classList.remove('closing');$('settings-drawer').classList.remove('closing');
    updateSettings();setTimeout(()=>$('close-settings').focus(),100);
  }
  async function closeSettings(){
    closeMenu();call('save_settings',gather());$('settings-drawer').classList.add('closing');$('drawer-backdrop').classList.add('closing');
    await wait(reduced?0:350);$('settings-drawer').hidden=true;$('drawer-backdrop').hidden=true;drawerReturn?.focus();
  }
  const modalContent={
    help:{icon:'box',eyebrow:'YOUR EXISTING BLENDER WORKFLOW',title:'Blender import',content:'<ol><li>Keep your <strong>Beeble add-on enabled</strong> in Blender.</li><li>Choose <strong>Import VFX Passes</strong> and select the generated ZIP.</li><li>Open <strong>Edit & Render</strong> to adjust normals, alpha, depth, shadows and the original/relit blend.</li></ol><p>The optional <strong>Local VFX Pass Import</strong> companion preserves fractional FPS and exact output dimensions. Install <strong>vfx_blender_bridge.zip</strong>, then use File → Import → Local VFX Passes.</p>'},
    model:{icon:'box',eyebrow:'INDEPENDENT. ON-DEVICE.',title:'Models',content:'<div class="model-chips"><span>Depth Anything V2</span><span>Marigold Normals</span><span>SuperMat Materials</span></div><p>Depth, normals and material estimates run on your computer. Foreground extraction uses an anime or general subject model.</p><p>This is an independent pipeline, <strong>not SwitchLight</strong>. Specular is an adjustable value, and per-frame estimates can flicker. Preview a short section before generating the whole clip.</p><p>Model weights download on first use. <strong>Your footage stays local.</strong></p>'}
  };
  function openModal(name){
    closeMenu();modalReturn=document.activeElement;const data=modalContent[name];
    $('modal-title').textContent=data.title;
    $('modal-content').innerHTML=data.content;$('modal-icon').innerHTML=icon(data.icon);$('modal-backdrop').hidden=false;icons();$('modal-close').focus();
  }
  function closeModal(){$('modal-backdrop').hidden=true;modalReturn?.focus();}
  function fullscreen(){
    const viewer=$('viewer'),before=viewer.getBoundingClientRect();expanded=!expanded;
    viewer.classList.toggle('expanded',expanded);$('fullscreen').innerHTML=icon(expanded?'minimize':'maximize');icons();
    const after=viewer.getBoundingClientRect();
    if(!reduced)viewer.animate([{transformOrigin:'top left',transform:`translate(${before.x-after.x}px,${before.y-after.y}px) scale(${before.width/after.width},${before.height/after.height})`},{transformOrigin:'top left',transform:'translate(0,0) scale(1,1)'}],{duration:600,easing:'cubic-bezier(.22,1,.36,1)'});
  }
  function bind(){
    $('browse').onclick=async()=>receiveVideo(await call('browse_video'));
    $('model-info').onclick=()=>openModal('model');$('help').onclick=()=>openModal('help');
    $('settings-heading').onclick=openSettings;
    $('new-clip').onclick=()=>setScreen('setup');$('resume-preview').onclick=()=>setScreen('preview');
    $('export-passes').onclick=exportPasses;
    $('close-settings').onclick=$('drawer-backdrop').onclick=$('save-settings').onclick=closeSettings;
    $('modal-close').onclick=$('modal-done').onclick=closeModal;
    $('modal-backdrop').onclick=e=>{if(e.target===$('modal-backdrop'))closeModal();};
    $('reset-settings').onclick=()=>{Object.assign(settings,{processing:512,steps:4,temporal:.6,specular:.5,roughness:.65,metallic:0,basecolor:'Source colors',materials:'SuperMat estimates'});updateSettings();toast('Quality controls reset.');};
    $('output-folder').onclick=async()=>{const result=await call('choose_folder','output');if(result?.path){settings.output=result.path;updateSettings();}};
    $('matte-button').onclick=async()=>{const result=await call('choose_matte');if(result?.path){settings.matte=result.path;settings.alpha='External matte';updateSettings();}};
    $('load-export').onclick=async()=>{const result=await call('choose_folder','export');if(result?.package){await loadClip(result.package);toast('Export loaded.');}};
    $('open-output').onclick=()=>call('open_output');
    $('generate').onclick=()=>generate(false);$('preview').onclick=()=>generate(true);
    $('cancel').onclick=async()=>{$('cancel').disabled=true;await call('stop');$('phase-label').textContent='Cancelling safely…';log('Waiting for the current inference or model download to finish.');};
    $('play').onclick=$('center-play').onclick=togglePlayback;$('fullscreen').onclick=fullscreen;
    $('scrubber').addEventListener('input',e=>{stopPlayback();showFrame(Number(e.target.value));});
    $('scrubber').addEventListener('change',()=>thumbnails(frame));
    $('timeline').addEventListener('pointermove',e=>{if(!clip)return;const rect=$('timeline').getBoundingClientRect(),ratio=Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width));$('scrub-tooltip').style.left=`${ratio*100}%`;$('scrub-tooltip').textContent=preciseTime(Math.round(ratio*(clip.count-1))/clip.fps);});
    $('activity-button').onclick=()=>{$('activity-panel').hidden=!$('activity-panel').hidden;};$('activity-close').onclick=()=>{$('activity-panel').hidden=true;};
    document.querySelectorAll('[data-window]').forEach(b=>b.onclick=()=>call('window_action',b.dataset.window));
    document.querySelectorAll('[data-select]').forEach(b=>b.addEventListener('click',()=>openMenu(b)));
    for(const key of ['steps','temporal','specular','roughness','metallic'])$(key).addEventListener('input',()=>{settings[key]=Number($(key).value);updateSlider(key);});
    for(const key of ['size','fps'])$(key).addEventListener('change',()=>call('save_settings',gather()));
    document.addEventListener('pointerdown',e=>{if(menuTrigger&&!$('popover').contains(e.target)&&!e.target.closest('[data-select]'))closeMenu();
      const button=e.target.closest('.interactive,.pass-card,.purple-button,.secondary-button');if(!button||button.disabled||reduced)return;
      const r=button.getBoundingClientRect(),s=document.createElement('span');s.className='ripple';s.style.width=s.style.height=`${Math.max(r.width,r.height)*2}px`;s.style.left=`${e.clientX-r.left}px`;s.style.top=`${e.clientY-r.top}px`;button.append(s);setTimeout(()=>s.remove(),800);
    });
    let pointerFrame=false;
    document.addEventListener('pointermove',e=>{if(pointerFrame||reduced)return;pointerFrame=true;requestAnimationFrame(()=>{for(const el of document.querySelectorAll('.glass,.interactive,.dropzone')){const r=el.getBoundingClientRect();el.style.setProperty('--mx',`${e.clientX-r.left}px`);el.style.setProperty('--my',`${e.clientY-r.top}px`);}pointerFrame=false;});});
    let tipTimer;
    document.addEventListener('pointerover',e=>{const trigger=e.target.closest('[data-tip]');if(!trigger)return;clearTimeout(tipTimer);tipTimer=setTimeout(()=>{const r=trigger.getBoundingClientRect(),tip=$('tooltip');tip.textContent=trigger.dataset.tip;tip.style.left=`${Math.min(innerWidth-270,Math.max(12,r.left+r.width/2-65))}px`;tip.style.top=`${Math.min(innerHeight-50,r.bottom+9)}px`;tip.classList.add('visible');},600);});
    document.addEventListener('pointerout',e=>{if(e.target.closest('[data-tip]')){clearTimeout(tipTimer);$('tooltip').classList.remove('visible');}});
    let dragDepth=0;
    document.addEventListener('dragenter',e=>{e.preventDefault();if([...e.dataTransfer.types].includes('Files')){dragDepth++;$('dropzone').classList.add('dragging');}});
    document.addEventListener('dragover',e=>{e.preventDefault();e.dataTransfer.dropEffect='copy';});
    document.addEventListener('dragleave',e=>{e.preventDefault();dragDepth--;if(dragDepth<=0){dragDepth=0;$('dropzone').classList.remove('dragging');}});
    document.addEventListener('drop',e=>{e.preventDefault();dragDepth=0;$('dropzone').classList.remove('dragging');});
    document.addEventListener('keydown',e=>{
      if(e.key==='Escape'){if(busy)return;if(menuTrigger)closeMenu();else if(!$('modal-backdrop').hidden)closeModal();else if(!$('settings-drawer').hidden)closeSettings();else if(expanded)fullscreen();else $('activity-panel').hidden=true;return;}
      if(menuTrigger&&['ArrowDown','ArrowUp','Enter',' '].includes(e.key)){
        e.preventDefault();const buttons=[...$('popover').querySelectorAll('button')];
        if(e.key==='ArrowDown'||e.key==='ArrowUp'){activeOption=(activeOption+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length;buttons[activeOption].focus();}
        else selectOption(menuKey,buttons[activeOption].dataset.value);return;
      }
      const dialog=busy?$('generation-overlay'):!$('modal-backdrop').hidden?$('modal-backdrop'):!$('settings-drawer').hidden?$('settings-drawer'):null;
      if(dialog&&e.key==='Tab'){const focusable=[...dialog.querySelectorAll('button:not(:disabled),input:not(:disabled)')].filter(el=>el.offsetParent!==null);if(!focusable.length)return;const first=focusable[0],last=focusable.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}return;}
      if(dialog||document.body.dataset.screen!=='preview'||e.target.matches('input,textarea,button'))return;
      if(e.code==='Space'){e.preventDefault();togglePlayback();}
      if(e.key.toLowerCase()==='f')fullscreen();
      if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();stopPlayback();showFrame(frame+(e.key==='ArrowRight'?1:-1));}
      if(/^[1-8]$/.test(e.key))choosePass(passes[Number(e.key)-1].key);
    });
    new ResizeObserver(()=>{moveSelection();if(menuTrigger)closeMenu();}).observe($('pass-cards'));
  }
  async function boot(){
    api=window.pywebview?.api;if(!api)return;
    try{
      const data=await api.bootstrap();settings={basecolor:'Source colors',materials:'SuperMat estimates',...data.settings};updateSettings();
      if(data.video)receiveVideo({video:data.video,alpha:settings.alpha});
      if(data.package)await loadClip(data.package,false);
      setScreen('setup');
      if(data.busy)setBusy(true);if(data.exporting)setExporting(true);document.body.classList.remove('booting');
      log(data.package?.demo?'Demo preview · choose your own video to get started.':'Choose a video or resume your previous result.');
      setInterval(poll,350);window.studio.ready=true;
    }catch(error){document.body.classList.remove('booting');toast('The desktop connection could not initialize.',true);log(String(error));}
  }
  document.body.classList.add('booting');renderCards();bind();icons();
  window.studio={ready:false,receiveVideo,choosePass,loadClip,generate,openSettings,closeSettings,togglePlayback,showFrame,
    getState:()=>({screen:document.body.dataset.screen,exporting,progress:progressValue,currentPass,frame,playing,busy,clip:clip?.name,settings:{...settings}})};
  if(window.pywebview?.api)boot();else window.addEventListener('pywebviewready',boot,{once:true});
})();
