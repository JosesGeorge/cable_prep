const STAGES = ["FEED","STRAIGHTEN","MEASURE","CUT","PEEL","FORM","INSPECT"];
const flowEl = document.getElementById('flow');
STAGES.forEach((s,i)=>{
  const d=document.createElement('div'); d.className='stage'; d.id='stage-'+i;
  d.innerHTML = `<span class="dot"></span><span>${s}</span><span class="tag"></span>`;
  flowEl.appendChild(d);
});

const feedSlider=document.getElementById('feedSlider'), depthSlider=document.getElementById('depthSlider'), limitSlider=document.getElementById('limitSlider');
const feedVal=document.getElementById('feedVal'), depthVal=document.getElementById('depthVal'), limitVal=document.getElementById('limitVal');

function syncLabels(){
  feedVal.textContent = feedSlider.value+' mm/s';
  depthVal.textContent = (depthSlider.value/10).toFixed(1)+' mm';
  limitVal.textContent = limitSlider.value+' N';
}
function pushParams(){
  fetch('/api/params', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({feed_speed: parseFloat(feedSlider.value), cut_depth: depthSlider.value/10, force_limit: parseFloat(limitSlider.value)})
  });
}
[feedSlider,depthSlider,limitSlider].forEach(el=>{
  el.addEventListener('input', syncLabels);
  el.addEventListener('change', pushParams);
});
syncLabels();

function setStages(stageIdx, running){
  STAGES.forEach((s,idx)=>{
    const el=document.getElementById('stage-'+idx);
    el.classList.remove('active','done');
    const tag=el.querySelector('.tag');
    if(idx<stageIdx || (!running && stageIdx>=STAGES.length)){ el.classList.add('done'); tag.textContent='✓'; }
    else if(idx===stageIdx && running){ el.classList.add('active'); tag.textContent='● RUNNING'; }
    else tag.textContent='';
  });
}

let lastInspectionShown = null;

function applyState(d){
  const led=document.getElementById('sysLed');
  const txt=document.getElementById('sysText');
  txt.textContent = 'SYSTEM: '+d.status;
  led.className = 'led ' + (d.status==='RUNNING' ? 'on' : d.status==='EMERGENCY STOP' ? 'stop' : d.force_spike_active ? 'warn' : '');

  setStages(d.stage_idx, d.running);

  const s=d.sensors;
  document.getElementById('s-diam').innerHTML = s.diameter.toFixed(2)+'<span class="unit">mm</span>';
  document.getElementById('s-oval').innerHTML = s.ovality.toFixed(2)+'<span class="unit">mm</span>';
  document.getElementById('s-force').innerHTML = s.force.toFixed(1)+'<span class="unit">N</span>';
  document.getElementById('s-feed').innerHTML = s.feed.toFixed(1)+'<span class="unit">mm/s</span>';
  document.getElementById('s-len').innerHTML = s.length.toFixed(0)+'<span class="unit">mm</span>';
  const statusEl=document.getElementById('s-status');
  statusEl.textContent = d.running ? (d.force_spike_active?'WARNING':'NORMAL') : 'IDLE';
  statusEl.style.color = d.force_spike_active ? 'var(--amber)' : (d.running?'var(--green)':'var(--muted)');

  document.getElementById('p-diam').textContent = s.diameter.toFixed(2)+' mm';
  document.getElementById('p-oval').textContent = s.ovality.toFixed(2)+' mm';
  document.getElementById('p-run').textContent = s.runout.toFixed(2)+' mm';
  document.getElementById('p-len').textContent = s.length.toFixed(1)+' mm';
  const ry = Math.max(40, 58 - s.ovality*40);
  document.getElementById('cableEllipse').setAttribute('ry', ry.toFixed(1));

  if(d.adaptive){
    document.getElementById('a-diam').textContent = s.diameter.toFixed(2)+' mm';
    document.getElementById('a-bound').textContent = d.adaptive.boundary.toFixed(2)+' mm';
    document.getElementById('a-target').textContent = d.adaptive.target_depth.toFixed(2)+' mm';
    document.getElementById('a-limit').textContent = d.adaptive.limit+' N';
    const loopForce=document.getElementById('loopForce'), loopDepth=document.getElementById('loopDepth');
    if(d.force_spike_active){
      loopForce.textContent = 'CURRENT FORCE '+s.force.toFixed(1)+' N ⚠';
      loopForce.classList.add('warn');
      loopDepth.textContent = 'REDUCED DEPTH = '+d.adaptive.adaptive_depth.toFixed(2)+' mm';
      loopDepth.classList.add('warn');
    } else {
      loopForce.textContent = 'CURRENT FORCE '+s.force.toFixed(1)+' N';
      loopForce.classList.remove('warn');
      loopDepth.textContent = 'ADAPTIVE DEPTH = '+d.adaptive.adaptive_depth.toFixed(2)+' mm';
      loopDepth.classList.remove('warn');
    }
  }

  if(d.last_inspection && d.last_inspection !== lastInspectionShown){
    lastInspectionShown = d.last_inspection;
    showInspection(d.last_inspection);
    loadSpecimens();
  }
  if(!d.last_inspection && d.running){
    resetInspectionView();
  }
}

function resetInspectionView(){
  ['v-len','v-wid','v-thk','v-edge','v-surf'].forEach(id=>{
    document.getElementById(id).innerHTML = '<span class="wait">···</span>';
  });
  const b=document.getElementById('resultBanner');
  b.textContent='AWAITING SPECIMEN'; b.className='result-banner';
}

function showInspection(r){
  document.getElementById('v-len').innerHTML = r.length.toFixed(1)+' mm '+(r.length_ok?'<span class="ok">✓</span>':'<span class="bad">✕</span>');
  document.getElementById('v-wid').innerHTML = r.width.toFixed(1)+' mm '+(r.width_ok?'<span class="ok">✓</span>':'<span class="bad">✕</span>');
  document.getElementById('v-thk').innerHTML = r.thickness.toFixed(1)+' mm '+(r.thickness_ok?'<span class="ok">✓</span>':'<span class="bad">✕</span>');
  document.getElementById('v-edge').innerHTML = r.edge_ok?'<span class="ok">✓</span>':'<span class="bad">✕</span>';
  document.getElementById('v-surf').innerHTML = r.surface_ok?'<span class="ok">✓</span>':'<span class="bad">✕</span>';
  const b=document.getElementById('resultBanner');
  b.textContent = r.pass ? '● SPECIMEN PASS' : '● SPECIMEN FAIL';
  b.className = 'result-banner ' + (r.pass?'pass':'fail');
}

function loadSpecimens(){
  fetch('/api/specimens').then(r=>r.json()).then(rows=>{
    const tbody=document.getElementById('logBody');
    if(!rows.length){ tbody.innerHTML='<tr><td colspan="7" style="color:var(--dim)">No specimens run yet</td></tr>'; return; }
    tbody.innerHTML = rows.map(r=>`<tr><td>${r.specimen_id}</td><td>${r.diameter.toFixed(2)} mm</td><td>${r.cut_depth.toFixed(2)} mm</td><td>${r.max_force.toFixed(1)} N</td><td>${r.length.toFixed(1)} mm</td><td class="${r.result==='PASS'?'pass':'fail'}">${r.result}</td><td>${r.created_at}</td></tr>`).join('');
  });
}

function poll(){
  fetch('/api/state').then(r=>r.json()).then(applyState).catch(()=>{});
}
setInterval(poll, 500);
poll();
loadSpecimens();

document.getElementById('btnStart').addEventListener('click', ()=> fetch('/api/control/start', {method:'POST'}));
document.getElementById('btnStop').addEventListener('click', ()=> fetch('/api/control/stop', {method:'POST'}));
document.getElementById('btnReset').addEventListener('click', ()=>{
  fetch('/api/control/reset', {method:'POST'}).then(()=>{ lastInspectionShown=null; resetInspectionView(); });
});
document.getElementById('btnEstop').addEventListener('click', ()=>{
  fetch('/api/control/estop', {method:'POST'}).then(()=>{ lastInspectionShown=null; });
});
document.getElementById('btnSpike').addEventListener('click', ()=> fetch('/api/spike', {method:'POST'}));
document.getElementById('btnExport').addEventListener('click', ()=>{ window.location.href='/api/export'; });

document.querySelectorAll('nav button').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('nav button').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
    document.getElementById('screen-'+btn.dataset.screen).classList.add('active');
  });
});
