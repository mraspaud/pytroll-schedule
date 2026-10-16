const DATA = __DATA__;
const ANT_COLORS = ["#8dd3c7","#ffffb3","#bebada","#fb8072","#80b1d3","#fdb462","#b3de69","#fccde5","#d9d9d9","#bc80bd","#ccebc5","#ffed6f"]; // ColorBrewer Set3
const antennas = [...new Set(DATA.passes.filter(p=>!p.un).map(p=>p.ant))].sort();
const antColor = Object.fromEntries(antennas.map((a,i)=>[a,ANT_COLORS[i%ANT_COLORS.length]]));

// merge identical passes requested on several antennas
const merged = new Map();
for (const p of DATA.passes) {
  const k = p.un ? "un|"+p.sat+"|"+p.s : p.sat+"|"+p.s+"|"+p.e;
  if (merged.has(k)) merged.get(k).ants.push(p.ant);
  else merged.set(k, Object.assign({ants:[p.ant]}, p));
}
const passes = [...merged.values()].sort((a,b)=>(b.un||0)-(a.un||0) || a.s-b.s); // unscheduled first, so they sit behind
const sats = [...new Set(passes.map(p=>p.sat))].sort();
const satName = Object.fromEntries(passes.map(p=>[p.sat,p.name]));

// per-antenna overlap detection
for (const a of antennas) {
  const list = passes.filter(p=>!p.un && p.ants.includes(a)).sort((x,y)=>x.s-y.s);
  for (let i=1;i<list.length;i++) if (list[i].s < list[i-1].e) { list[i].conflict=list[i-1].conflict=true; }
}

const L=86, R=12, T=44, RH=26, PAD=6;
let W=1200, H=T+sats.length*RH+PAD;
let t0=DATA.span[0], t1=DATA.span[1];
const hidden = new Set();
const svg=document.getElementById("g"), tip=document.getElementById("tip"), wrap=document.getElementById("wrap");

function X(t){return L+(t-t0)/(t1-t0)*(W-L-R)}
function pad(n){return (n<10?"0":"")+n}
function hhmm(t){const d=new Date(t*1000);return pad(d.getUTCHours())+":"+pad(d.getUTCMinutes())}
function hhmmss(t){const d=new Date(t*1000);return hhmm(t)+":"+pad(d.getUTCSeconds())}
function ymd(t){const d=new Date(t*1000);return d.toISOString().slice(0,10)}
function dayLabel(t){const d=new Date(t*1000);return ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][d.getUTCDay()]+" "+ymd(t)}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}

function draw(){
  W = wrap.clientWidth || 1200;
  svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
  svg.setAttribute("height",H);
  let o=`<defs><clipPath id="cp"><rect x="${L}" y="0" width="${W-L-R}" height="${H}"/></clipPath>`;
  // striped fills for passes on several antennas
  const combos=new Set(passes.map(p=>p.ants.slice().sort().join("+")).filter(c=>c.includes("+")));
  for (const c of combos){
    const cols=c.split("+").map(a=>antColor[a]); const w=4*cols.length;
    o+=`<pattern id="pat-${c.replace(/[^a-z0-9]/gi,"_")}" width="${w}" height="${w}" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">`;
    cols.forEach((col,i)=>o+=`<rect x="${i*4}" width="4" height="${w}" fill="${col}"/>`);
    o+=`</pattern>`;
  }
  o+=`</defs>`;
  sats.forEach((s,i)=>{const y=T+i*RH;
    o+=`<rect x="0" y="${y}" width="${W}" height="${RH}" fill="${i%2?'var(--row)':'transparent'}"/>`;
    o+=`<text x="8" y="${y+17}" font-size="12" fill="var(--fg)" font-weight="500">${esc(satName[s])}</text>`;});
  o+=`<g clip-path="url(#cp)">`;
  const span=t1-t0;
  const pxPerSec=(W-L-R)/span;
  const step=[60,300,600,900,1800,3600,2*3600,3*3600,6*3600,12*3600].find(st=>st*pxPerSec>=64)||12*3600;
  // day boundaries + labels
  for (let d=Math.floor(t0/86400)*86400; d<=t1; d+=86400){
    const x=X(d);
    o+=`<line x1="${x}" y1="0" x2="${x}" y2="${H}" stroke="var(--border)" stroke-width="1"/>`;
    o+=`<text x="${Math.max(x,L)+4}" y="14" font-size="12" fill="var(--fg)" font-weight="600">${dayLabel(d)}</text>`;
  }
  for (let t=Math.ceil(t0/step)*step; t<=t1; t+=step){
    const x=X(t); if (t%86400===0) continue;
    o+=`<line x1="${x}" y1="${T-6}" x2="${x}" y2="${H}" stroke="var(--line)" stroke-width="1"/>`;
    o+=`<text x="${x+3}" y="${T-10}" font-size="11" fill="var(--muted)">${hhmm(t)}</text>`;
  }
  passes.forEach((p,i)=>{
    if (p.e<t0||p.s>t1) return;
    const y=T+sats.indexOf(p.sat)*RH+5, x=X(p.s), w=Math.max(2,X(p.e)-x);
    const key=p.ants.slice().sort().join("+");
    const fill=p.un?"var(--row)":p.ants.length>1?`url(#pat-${key.replace(/[^a-z0-9]/gi,"_")})`:antColor[p.ants[0]];
    const dim=(hidden.has(p.sat)?" dim":"")+(p.un?" un":"");
    const stroke=p.conflict?' stroke="#E24B4A" stroke-width="2"':'';
    o+=`<g class="bar${dim}" data-i="${i}">`;
    if (p.fs!==undefined){ const fx=X(p.fs), fw=Math.max(2,X(p.fe)-fx);
      o+=`<rect x="${fx}" y="${y+3}" width="${fw}" height="${RH-16}" rx="2" fill="var(--row)" stroke="rgba(128,128,128,.6)" stroke-dasharray="3 2"/>`; }
    o+=`<rect x="${x}" y="${y}" width="${w}" height="${RH-10}" rx="3" fill="${fill}"${stroke}/>`;
    if (p.orbit!==undefined && w>44) o+=`<text x="${x+w/2}" y="${y+12}" text-anchor="middle">${p.orbit}</text>`;
    o+=`</g>`;
  });
  const now=Date.now()/1000;
  if (now>t0&&now<t1) o+=`<line x1="${X(now)}" y1="0" x2="${X(now)}" y2="${H}" stroke="#E24B4A" stroke-width="1.5"/>`;
  o+=`</g><line x1="${L}" y1="${T}" x2="${W}" y2="${T}" stroke="var(--border)" stroke-width="1"/>`;
  svg.innerHTML=o;
  const nUn=passes.filter(p=>p.un).length;
  document.getElementById("status").textContent=`${ymd(t0)} ${hhmm(t0)} → ${ymd(t1)} ${hhmm(t1)} UTC · ${passes.length-nUn} scheduled, ${nUn} not`;
}

// ---- legend and filters
const legend=document.getElementById("legend");
legend.innerHTML=antennas.map(a=>`<span><i class="sw" style="background:${antColor[a]}"></i>${esc(a)}</span>`).join("")+
  (antennas.length>1?`<span><i class="sw" style="background:repeating-linear-gradient(45deg,${antennas.map((a,i)=>`${antColor[a]} ${i*3}px ${(i+1)*3}px`).join(",")})"></i>several antennas</span>`:"")+
  `<span><i class="sw" style="border:2px solid #E24B4A;box-sizing:border-box"></i>overlap within one antenna</span>`+
  (passes.some(p=>p.un)?`<span><i class="sw" style="background:var(--row);border:1px dashed var(--muted);box-sizing:border-box"></i>not scheduled</span>`:"");
const filters=document.getElementById("filters");
filters.innerHTML=`<label><input type="checkbox" id="all" checked> all</label>`+sats.map(s=>`<label><input type="checkbox" data-sat="${s}" checked> ${esc(satName[s])}</label>`).join("");
filters.addEventListener("change",e=>{
  if (e.target.id==="all"){ filters.querySelectorAll("[data-sat]").forEach(c=>{c.checked=e.target.checked; e.target.checked?hidden.delete(c.dataset.sat):hidden.add(c.dataset.sat);}); }
  else { e.target.checked?hidden.delete(e.target.dataset.sat):hidden.add(e.target.dataset.sat); }
  draw();
});

// ---- zoom / pan
svg.addEventListener("wheel",ev=>{ev.preventDefault();
  const r=svg.getBoundingClientRect(); const fx=(ev.clientX-r.left)/r.width*W;
  const tc=t0+(fx-L)/(W-L-R)*(t1-t0); const k=ev.deltaY>0?1.25:0.8;
  const ns=Math.min(DATA.span[1]-DATA.span[0]+2*3600, Math.max(1800,(t1-t0)*k));
  t0=tc-(tc-t0)*ns/(t1-t0); t1=t0+ns; draw();},{passive:false});
let dragX=null, moved=false;
svg.addEventListener("mousedown",ev=>{dragX=ev.clientX;moved=false});
window.addEventListener("mouseup",()=>{dragX=null});
svg.addEventListener("mousemove",ev=>{
  if (dragX!==null){ const r=svg.getBoundingClientRect(); const dt=(ev.clientX-dragX)/r.width*W/(W-L-R)*(t1-t0);
    if (Math.abs(ev.clientX-dragX)>2) moved=true; t0-=dt;t1-=dt;dragX=ev.clientX;draw(); tip.style.display="none"; return; }
  const g=ev.target.closest(".bar"); if(!g){tip.style.display="none";return;}
  showTip(passes[+g.dataset.i], ev);
});
svg.addEventListener("mouseleave",()=>{tip.style.display="none"});
svg.addEventListener("click",ev=>{ if (moved) return; const g=ev.target.closest(".bar"); if(!g) return;
  window.open(location.pathname+"?pass="+encodeURIComponent(passId(passes[+g.dataset.i])),"_blank"); });
document.getElementById("today").onclick=()=>{const d=Math.floor(Date.now()/86400000)*86400; t0=d; t1=d+86400; draw();};
document.getElementById("week").onclick=()=>{t0=DATA.span[0]; t1=DATA.span[1]; draw();};
document.getElementById("now").onclick=()=>{const n=Date.now()/1000, s=Math.min(t1-t0,6*3600); t0=n-s/3; t1=t0+s; draw();};
window.addEventListener("resize",draw);

// ---- near-sided perspective map
const MAP=DATA.map; let SZ=256;
const lat0=MAP.lat*Math.PI/180, lon0=MAP.lon*Math.PI/180, P=(6371+MAP.height_km)/6371;
const cosL=Math.cos(lat0), sinL=Math.sin(lat0);
const rmax = P/(P+1)*Math.sqrt(1-1/(P*P)); // disc radius at the horizon, in R units
let SCALE=(SZ/2-2)/rmax;
function setMapSize(n){ if(n!==SZ){ SZ=n; SCALE=(SZ/2-2)/rmax; base=null; } }
function proj(lon,lat){ // [x,y,visible]; hidden points are clamped onto the horizon rim
  const la=lat*Math.PI/180, lo=lon*Math.PI/180-lon0;
  const cosc = sinL*Math.sin(la)+cosL*Math.cos(la)*Math.cos(lo);
  let x=Math.cos(la)*Math.sin(lo), y=cosL*Math.sin(la)-sinL*Math.cos(la)*Math.cos(lo);
  const vis = cosc >= 1/P;
  if (vis){ const k=(P-1)/(P-cosc); x*=k; y*=k; }
  else { const n=Math.hypot(x,y)||1e-9; x*=rmax/n; y*=rmax/n; }
  return [SZ/2+x*SCALE, SZ/2-y*SCALE, vis];
}
function ringPath(c, ring, close){ // trace a ring, walking the rim between consecutive hidden points
  let any=false, prev=null;
  for (const [lon,lat] of ring){
    const q=proj(lon,lat); any=any||q[2];
    if (prev && !q[2] && !prev[2]){ // both on the rim: follow the rim the short way
      let a0=Math.atan2(prev[1]-SZ/2,prev[0]-SZ/2), a1=Math.atan2(q[1]-SZ/2,q[0]-SZ/2);
      let d=a1-a0; while(d>Math.PI)d-=2*Math.PI; while(d<-Math.PI)d+=2*Math.PI;
      const n=Math.ceil(Math.abs(d)/0.1);
      for(let i=1;i<n;i++){const a=a0+d*i/n; c.lineTo(SZ/2+rmax*SCALE*Math.cos(a),SZ/2+rmax*SCALE*Math.sin(a));}
    }
    prev?c.lineTo(q[0],q[1]):c.moveTo(q[0],q[1]); prev=q;
  }
  if (close) c.closePath();
  return any;
}
function toXYZ(lon,lat){const la=lat*Math.PI/180,lo=lon*Math.PI/180;return [Math.cos(la)*Math.cos(lo),Math.cos(la)*Math.sin(lo),Math.sin(la)]}
function fromXYZ(v){const n=Math.hypot(v[0],v[1],v[2]);return [Math.atan2(v[1],v[0])*180/Math.PI, Math.asin(v[2]/n)*180/Math.PI]}
function densify(ring, n){ // great-circle interpolation between consecutive vertices
  const out=[]; for(let i=0;i<ring.length;i++){const a=toXYZ(...ring[i]), b=toXYZ(...ring[(i+1)%ring.length]);
    for(let j=0;j<n;j++){const f=j/n; out.push(fromXYZ([a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f,a[2]+(b[2]-a[2])*f]));}} return out;
}
function cssVar(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim()}
var base=null;
function drawBase(){
  base=document.createElement("canvas"); base.width=base.height=SZ; const c=base.getContext("2d");
  c.fillStyle=cssVar("--sea"); c.beginPath(); c.arc(SZ/2,SZ/2,SZ/2-2,0,2*Math.PI); c.fill();
  c.fillStyle=cssVar("--land"); c.strokeStyle=cssVar("--border"); c.lineWidth=0.6;
  c.save(); c.beginPath(); c.arc(SZ/2,SZ/2,SZ/2-2,0,2*Math.PI); c.clip();
  for (const ring of MAP.lines){ c.beginPath(); if (ringPath(c, ring, true)){ c.fill(); c.stroke(); } }
  c.restore();
  // graticule
  c.strokeStyle="rgba(128,128,128,.35)"; c.lineWidth=0.5;
  for(let lat=-80;lat<=80;lat+=20){c.beginPath();let pen=false;for(let lon=-180;lon<=180;lon+=2){const q=proj(lon,lat);if(!q[2]){pen=false;continue;}pen?c.lineTo(q[0],q[1]):c.moveTo(q[0],q[1]);pen=true;}c.stroke();}
  for(let lon=-180;lon<180;lon+=30){c.beginPath();let pen=false;for(let lat=-90;lat<=90;lat+=2){const q=proj(lon,lat);if(!q[2]){pen=false;continue;}pen?c.lineTo(q[0],q[1]):c.moveTo(q[0],q[1]);pen=true;}c.stroke();}
  const st=proj(MAP.lon,MAP.lat); c.fillStyle="#E24B4A"; c.beginPath(); c.arc(st[0],st[1],3,0,2*Math.PI); c.fill();
}
function showTip(p, ev){
  setMapSize(256);
  tip.innerHTML=passInfoHtml(p)+(p.cov?`<canvas width="${SZ}" height="${SZ}"></canvas>`:`<div style="color:var(--muted)">no coverage (no TLE)</div>`)+
    `<div style="color:var(--muted);margin-top:6px">click to open in a new tab</div>`;
  if (p.cov) drawPassMap(tip.querySelector("canvas"), p);
  tip.style.display="block";
  const r=wrap.getBoundingClientRect(); const tw=tip.offsetWidth, th=tip.offsetHeight;
  let x=ev.clientX-r.left+14, y=ev.clientY-r.top+14;
  if (x+tw>r.width) x=ev.clientX-r.left-tw-14;
  if (ev.clientY+14+th>window.innerHeight) y=Math.max(-r.top+8, ev.clientY-r.top-th-14);
  tip.style.left=x+"px"; tip.style.top=y+"px";
}
function drawPassMap(canvas, p){
    if(!base) drawBase();
    const c=canvas.getContext("2d"); c.drawImage(base,0,0);
    const col=p.un?"#d9d9d9":antColor[p.ants[0]];
    c.save(); c.beginPath(); c.arc(SZ/2,SZ/2,SZ/2-2,0,2*Math.PI); c.clip();
    if (p.fcov){ c.strokeStyle="#777"; c.fillStyle="rgba(128,128,128,.35)"; c.lineWidth=1; c.setLineDash([3,2]);
      c.beginPath(); ringPath(c, densify(p.fcov,8), true); c.fill(); c.stroke(); c.setLineDash([]); }
    c.strokeStyle="#333"; c.fillStyle=p.un||p.ants.length<2?col+"66":stripePattern(c, p.ants.map(a=>antColor[a]+"66")); c.lineWidth=1.5;
    c.beginPath(); ringPath(c, densify(p.cov,8), true); c.fill(); c.stroke(); c.restore();
}
function stripePattern(c, cols){ // diagonal stripes, one per antenna, as a canvas fill
  const w=Math.max(4, Math.round(SZ/40)), n=cols.length, pc=document.createElement("canvas"); pc.width=w*n; pc.height=w;
  const g=pc.getContext("2d"); cols.forEach((col,i)=>{ g.fillStyle=col; g.fillRect(i*w,0,w,w); });
  const pat=c.createPattern(pc,"repeat"); pat.setTransform(new DOMMatrix().rotate(45)); return pat;
}
function passId(p){return p.sat+"-"+Math.round(p.s)}
function passInfoHtml(p){
  const ants=p.un?"not scheduled":"on "+p.ants.join(" + "), dur=Math.round(p.e-p.s);
  return `<b>${esc(p.name)}</b> <span style="color:var(--muted)">${esc(ants)}${p.orbit!==undefined?` · orbit ${p.orbit}`:""}</span>`+
    `<div>${ymd(p.s)} &nbsp; AOS ${hhmmss(p.s)} → LOS ${hhmmss(p.e)} UTC</div>`+
    `<div>${Math.floor(dur/60)} min ${dur%60} s · station ${esc(p.station)}${p.conflict?' · <span style="color:#E24B4A">overlaps another pass</span>':""}</div>`+
    (p.fs!==undefined?`<div style="color:var(--muted)">trimmed: visible ${hhmmss(p.fs)} → ${hhmmss(p.fe)}, ${Math.max(0,Math.round(p.s-p.fs))} s cut at start, ${Math.max(0,Math.round(p.fe-p.e))} s at end</div>`:"");
}
// ---- single-pass page (schedule.html?pass=<sat>-<unix AOS>)
function showPassPage(id){
  const p=passes.find(q=>passId(q)===id);
  document.body.innerHTML="";
  const el=document.createElement("div"); el.style.cssText="max-width:900px;margin:0 auto;padding:16px 24px;font-size:15px";
  if (!p){ el.innerHTML=`<p>No pass with id <code>${esc(id)}</code>.</p><p><a href="${location.pathname}">Back to the schedule</a></p>`; document.body.appendChild(el); return; }
  document.title=`${p.name} ${ymd(p.s)} ${hhmm(p.s)} UTC`;
  el.innerHTML=`<p><a href="${location.pathname}">← schedule</a></p><div style="font-size:16px">${passInfoHtml(p)}</div>`;
  const size=Math.min(760, window.innerWidth-48);
  if (p.cov){ const cv=document.createElement("canvas"); cv.width=cv.height=size; cv.style.cssText="display:block;margin:16px auto;border-radius:50%";
    el.appendChild(cv); setMapSize(size); drawPassMap(cv, p); }
  else el.insertAdjacentHTML("beforeend",`<p style="color:var(--muted)">No coverage available (no TLE).</p>`);
  document.body.appendChild(el);
}
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change",()=>{base=null});

const wanted=new URLSearchParams(location.search).get("pass");
if (wanted) showPassPage(wanted);
else {
  document.getElementById("today").click();
  if (!(Date.now()/1000>DATA.span[0] && Date.now()/1000<DATA.span[1])) document.getElementById("week").click();
}
