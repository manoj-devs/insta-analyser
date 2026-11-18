"use strict";
const $=s=>document.querySelector(s), esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const n=x=>isNaN(Number(x))?x:Number(x).toLocaleString(), inr=x=>"₹"+Math.round(x).toLocaleString("en-IN");
let ME=null, timers=[], CFG=null;

async function api(url,opt={}){
  const o={credentials:"same-origin",...opt,headers:{...(opt.headers||{})}};
  if(opt.body&&typeof opt.body!=="string"){o.body=JSON.stringify(opt.body);o.headers["Content-Type"]="application/json"}
  if((o.method||"GET")!=="GET")o.headers["X-Requested-With"]="fetch";
  if(opt.bg){o.headers["X-Background"]="1";delete o.bg}
  const r=await fetch(url,o);let d=null;try{d=await r.json()}catch(e){}
  if(!r.ok){
    if(r.status===401&&ME&&!/\/auth\/(login|verify)/.test(url)){ME=null;showAuth("Your session has ended. Please sign in again.")}
    const er=new Error((d&&(typeof d.detail==="string"?d.detail:"Invalid input"))||"Request failed ("+r.status+")");
    er.status=r.status;er.state=r.headers.get("X-Otp-State")||"";er.retry=+(r.headers.get("Retry-After")||0);throw er}
  return d}
function toast(m,k){const t=document.createElement("div");t.className="toast "+(k||"");t.textContent=m;$("#toasts").appendChild(t);setTimeout(()=>t.remove(),4200)}
function ask(title,placeholder,note){return new Promise(res=>{const m=document.createElement("div");m.className="modal";
  m.innerHTML=`<div class="glass box"><h3>${esc(title)}</h3><p class="sub">${esc(note===undefined?"The user will see this reason when they try to sign in.":note)}</p><input id="mr" placeholder="${esc(placeholder)}" maxlength="200"><div class="row" style="margin-top:12px;justify-content:flex-end"><button class="btn" id="mc">Cancel</button><button class="btn d" id="mo">Confirm</button></div></div>`;
  document.body.appendChild(m);const i=m.querySelector("#mr");i.focus();const done=v=>{m.remove();res(v)};
  m.querySelector("#mc").onclick=()=>done(null);m.querySelector("#mo").onclick=()=>done(i.value.trim());i.onkeydown=e=>{if(e.key==="Enter")done(i.value.trim())}})}
const ago=t=>{if(!t)return "never";const s=Math.max(0,Date.now()/1000-t);return s<60?"just now":s<3600?Math.floor(s/60)+" min ago":s<86400?Math.floor(s/3600)+" h ago":new Date(t*1000).toLocaleDateString()};
const dev=ua=>/Edg\//.test(ua)?"Edge":/Chrome\//.test(ua)?"Chrome":/Firefox\//.test(ua)?"Firefox":/Safari\//.test(ua)?"Safari":(ua||"").slice(0,24)||"unknown";

/* ---------------- theme ---------------- */
function setTheme(t){document.documentElement.setAttribute("data-theme",t);try{localStorage.setItem("iw_theme",t)}catch(e){}
  document.querySelectorAll("iframe.mod").forEach(f=>f.contentWindow&&f.contentWindow.postMessage({type:"theme",value:t},"*"))}
try{setTheme(localStorage.getItem("iw_theme")||"dark")}catch(e){}
$("#theme")&&($("#theme").onclick=()=>setTheme(document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark"));

/* ---------------- charts ---------------- */
function bars(rows,fmt){const mx=Math.max(...rows.map(r=>r[1]),1);return rows.map(r=>`<div class="bar"><span title="${esc(r[0])}">${esc(r[0])}</span><div class="t"><i style="width:${Math.max(r[1]/mx*100,1.5)}%"></i></div><em>${fmt?fmt(r[1]):n(r[1])}</em></div>`).join("")}
function line(xs,ys){const W=560,H=210,L=40,R=12,T=12,B=26,mx=Math.max(...ys)*1.1,P=ys.map((y,i)=>[L+i*(W-L-R)/Math.max(ys.length-1,1),T+(H-T-B)*(1-y/mx)]);
  let s="";[0,.25,.5,.75,1].forEach(f=>{const y=T+(H-T-B)*(1-f),v=Math.round(mx*f);s+=`<line x1="${L}" x2="${W-R}" y1="${y}" y2="${y}" stroke="var(--line)"/><text x="${L-6}" y="${y+4}" text-anchor="end" font-size="11" fill="var(--muted)">${v}</text>`});
  xs.forEach((x,i)=>s+=`<text x="${P[i][0]}" y="${H-8}" text-anchor="middle" font-size="11" fill="var(--muted)">${x}</text>`);
  s+=`<defs><linearGradient id="lg" x1="0" x2="1"><stop offset="0" stop-color="var(--a3)"/><stop offset=".6" stop-color="var(--a1)"/><stop offset="1" stop-color="var(--a2)"/></linearGradient></defs><polyline fill="none" stroke="url(#lg)" stroke-width="3" stroke-linejoin="round" points="${P.map(p=>p.join(",")).join(" ")}"/>`;
  P.forEach((p,i)=>s+=`<circle cx="${p[0]}" cy="${p[1]}" r="4.5" fill="var(--a2)"><title>${xs[i]}: ${ys[i]} average likes</title></circle>`);
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%" role="img" aria-label="Average likes per post by year">${s}</svg>`}
function heat(rows){const days=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],g={};let mx=0;
  rows.forEach(r=>{if(r[2]>=30){g[r[0]+r[1]]=r[3];mx=Math.max(mx,r[3])}});let h='<div class="heat"><span></span>'+[...Array(24).keys()].map(i=>`<span style="text-align:center">${i%3?"":i}</span>`).join("");
  days.forEach(d=>{h+=`<span>${d.slice(0,3)}</span>`;for(let i=0;i<24;i++){const v=g[d+i];h+=v==null?`<div style="background:var(--line);opacity:.25" title="${d} ${i}:00 · too few posts"></div>`:`<div style="background:rgb(255,${Math.round(77+120*(1-v/mx))},${Math.round(141-60*(v/mx))});opacity:${.25+.75*v/mx}" title="${d} ${i}:00 · ${v} average likes"></div>`}});return h+"</div>"}

/* ---- v5 dashboard charts: yearly trend with projection, percent-of-accounts bars, best-time columns ---- */
const fmtPct=v=>(v<1?v.toFixed(2):v.toFixed(1))+"%";
function pctBars(rows){ /* rows: [label, percent, count] */
  const mx=Math.max(...rows.map(r=>r[1]),1);
  return rows.map(r=>`<div class="bar" title="${esc(r[0])}: ${fmtPct(r[1])} of accounts (${n(r[2])})"><span>${esc(r[0])}</span><div class="t"><i style="width:${Math.max(r[1]/mx*100,1.2)}%"></i></div><em>${fmtPct(r[1])}</em></div>`).join("")}
function trendChart(rows,endYear){
  const yrs=rows.map(r=>+r[0]),val=rows.map(r=>+r[4]),first=yrs[0],last=yrs[yrs.length-1],END=Math.max(endYear||2026,last+1);
  const fy=yrs.map((y,i)=>[y,val[i]]).filter(p=>p[0]>=last-5&&p[0]<last);       /* five full calendar years before the partial last year */
  const mx_=fy.reduce((a,p)=>a+p[0],0)/fy.length,my=fy.reduce((a,p)=>a+p[1],0)/fy.length;
  const b=fy.reduce((a,p)=>a+(p[0]-mx_)*(p[1]-my),0)/Math.max(fy.reduce((a,p)=>a+(p[0]-mx_)**2,0),1e-9),a0=my-b*mx_;
  const sd=Math.sqrt(fy.reduce((a,p)=>a+(p[1]-(a0+b*p[0]))**2,0)/Math.max(fy.length-2,1));
  const proj=[];for(let y=last+1;y<=END;y++){const v=Math.max(a0+b*y,my*.2),w=sd*1.5+.04*v*(y-last);proj.push([y,v,Math.max(v-w,0),v+w])}
  const W=600,H=250,L=44,R=14,T=14,B=30,N=END-first,X=y=>L+(y-first)*(W-L-R)/N,top=Math.ceil(Math.max(...val,...proj.map(p=>p[3]))*1.05/200)*200,Y=v=>T+(H-T-B)*(1-v/top);
  let s="";[0,.25,.5,.75,1].forEach(f=>{const y=T+(H-T-B)*(1-f);s+=`<line x1="${L}" x2="${W-R}" y1="${y}" y2="${y}" stroke="var(--line)"/><text x="${L-6}" y="${y+4}" text-anchor="end" font-size="11" fill="var(--muted)">${Math.round(top*f)}</text>`});
  for(let y=first;y<=END;y++)s+=`<text x="${X(y)}" y="${H-10}" text-anchor="middle" font-size="10" fill="var(--muted)">${y}</text>`;
  s+=`<rect x="${X(last)+4}" y="${T}" width="${X(END)-X(last)-4}" height="${H-T-B}" fill="var(--glass)" rx="6"/><text x="${(X(last)+X(END))/2}" y="${T+14}" text-anchor="middle" font-size="10" fill="var(--muted)">no data in this dataset (ends Aug ${last})</text>`;
  s+=`<polygon fill="var(--a3)" opacity=".16" points="${proj.map(p=>X(p[0])+","+Y(p[3])).join(" ")} ${[...proj].reverse().map(p=>X(p[0])+","+Y(p[2])).join(" ")}"/>`;
  s+=`<polyline fill="none" stroke="var(--a3)" stroke-width="2.4" stroke-dasharray="6 5" points="${proj.map(p=>X(p[0])+","+Y(p[1])).join(" ")}"/>`;
  s+=`<polyline fill="none" stroke="var(--a1)" stroke-width="3" stroke-linejoin="round" points="${yrs.map((y,i)=>X(y)+","+Y(val[i])).join(" ")}"/>`;
  yrs.forEach((y,i)=>{const part=y===last;s+=`<circle cx="${X(y)}" cy="${Y(val[i])}" r="5" fill="${part?"var(--bg2)":"var(--a1)"}" stroke="var(--a1)" stroke-width="2"><title>${y}${part?" (partial year, data ends in August)":""}: ${val[i]} average likes</title></circle>`});
  proj.forEach(p=>s+=`<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="4" fill="var(--a3)"><title>${p[0]} projection: about ${Math.round(p[1])} likes (range ${Math.round(p[2])} to ${Math.round(p[3])}). Not real data.</title></circle>`);
  const lg=`<div class="row" style="gap:16px;margin-top:6px;font-size:12px;color:var(--muted)"><span><b style="color:var(--a1)">●</b> Data</span><span><b style="color:var(--a1)">○</b> ${last} is a partial year</span><span><b style="color:var(--a3)">┅</b> Projection ${last+1} to ${END}: straight-line trend of ${last-5} to ${last-1}, with a range. Not real data.</span></div>`;
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%" role="img" aria-label="Average likes per post by year with a projection to ${END}">${s}</svg>${lg}`}
function timeChart(rows){ /* rows: [weekday,hour,posts,avg_likes] -> engagement index by hour and by weekday */
  const H={},D={};let tp=0,tl=0;
  rows.forEach(r=>{const[d,h,p,a]=[r[0],+r[1],+r[2],+r[3]];tp+=p;tl+=p*a;(H[h]=H[h]||[0,0]);H[h][0]+=p;H[h][1]+=p*a;(D[d]=D[d]||[0,0]);D[d][0]+=p;D[d][1]+=p*a});
  const avg=tl/tp,hr=[...Array(24).keys()].map(h=>{const v=H[h]||[0,0];return{h,p:v[0],a:v[0]?v[1]/v[0]:0,idx:v[0]?v[1]/v[0]/avg*100:0,share:v[0]/tp*100}});
  const best=[...hr].sort((a,b)=>b.idx-a.idx).slice(0,3).map(x=>x.h),mx=Math.max(...hr.map(x=>x.idx),100)*1.1;
  const W=900,Ht=210,L=36,R=8,T=10,B=24,bw=(W-L-R)/24,Y=v=>T+(Ht-T-B)*(1-v/mx);let s="";
  [0,.5,1].forEach(f=>{const v=mx*f,y=Y(v);s+=`<line x1="${L}" x2="${W-R}" y1="${y}" y2="${y}" stroke="var(--line)"/><text x="${L-6}" y="${y+4}" text-anchor="end" font-size="10" fill="var(--muted)">${Math.round(v)}</text>`});
  hr.forEach(x=>{const bx=L+x.h*bw+2,top=Y(x.idx),isb=best.includes(x.h);s+=`<rect x="${bx}" y="${top}" width="${bw-4}" height="${Math.max(Ht-B-top,1)}" rx="3" fill="${isb?"var(--a1)":"var(--a3)"}" opacity="${isb?1:.55}"><title>${String(x.h).padStart(2,"0")}:00 · engagement index ${x.idx.toFixed(0)} · ${x.a.toFixed(0)} average likes · ${x.share.toFixed(1)}% of all posts (${n(x.p)})</title></rect>`;
    if(x.h%3===0)s+=`<text x="${bx+(bw-4)/2}" y="${Ht-8}" text-anchor="middle" font-size="10" fill="var(--muted)">${String(x.h).padStart(2,"0")}h</text>`});
  s+=`<line x1="${L}" x2="${W-R}" y1="${Y(100)}" y2="${Y(100)}" stroke="var(--text)" stroke-dasharray="4 4" opacity=".55"/><text x="${W-R}" y="${Y(100)-4}" text-anchor="end" font-size="10" fill="var(--muted)">typical = 100</text>`;
  const days=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],wd=days.map(d=>{const v=D[d]||[0,0];return[d.slice(0,3),v[0]?v[1]/v[0]/avg*100:0,v[0]/tp*100]});
  const wmx=Math.max(...wd.map(w=>w[1]),100);
  return `<svg viewBox="0 0 ${W} ${Ht}" style="width:100%" role="img" aria-label="Engagement index by hour of day">${s}</svg>
  <div class="chips" style="margin:6px 0 10px"><span class="sub">Best hours:</span>${best.map(h=>`<span class="chip up">${String(h).padStart(2,"0")}:00</span>`).join("")}</div>
  <h3 style="font-size:14px;margin:8px 0 8px">By weekday</h3><div class="wk">${(()=>{const bi=wd.reduce((a,w,k)=>w[1]>wd[a][1]?k:a,0);return wd.map((w,k)=>`<div class="${k===bi?"best":""}" title="${w[0]}: engagement index ${w[1].toFixed(0)}, ${w[2].toFixed(1)}% of all posts"><span>${w[0]}</span><b>${w[1].toFixed(0)}</b><small>${w[2].toFixed(1)}% of posts</small></div>`).join("")})()}</div>`}

/* ---------------- OTP pop-up (used by sign-up, new-device sign-in, password reset and the admin sign-in) ----------------
   otpPopup({title, info, verify(code, info), resend(info), onDone(result), onCancel()})
   info = answer of the server: {email, ticket, ttl, cooldown, max_tries, sent_to[], dev_outbox, remaining, already_sent, retry}   (the code itself is never sent to the page) */
function otpPopup(o){
  let info=o.info,left=info.remaining||info.ttl||300,cool=info.already_sent?(info.retry||info.cooldown||30):(info.cooldown||30),lockLeft=0,busyNow=false,closed=false,last=document.activeElement;
  const back=document.createElement("div");back.className="otp-back";
  back.innerHTML=`<div class="otp glass" role="dialog" aria-modal="true" aria-labelledby="otpT"><button type="button" class="otp-x" aria-label="Close">×</button>
   <h3 id="otpT">${esc(o.title||"Enter your code")}</h3><p class="sub otp-to"></p>
   <div class="otp-boxes" role="group" aria-label="6-digit code">${[0,1,2,3,4,5].map(i=>`<input inputmode="numeric" pattern="[0-9]*" maxlength="1" autocomplete="${i?"off":"one-time-code"}" aria-label="Digit ${i+1}">`).join("")}</div>
   <div class="otp-msg" role="status" aria-live="polite"></div><div class="otp-timer sub"></div>
   <button type="button" class="btn p otp-go" disabled>Verify</button>
   <div class="otp-row"><button type="button" class="linkbtn otp-re" disabled>Resend code</button><span class="sub">Check your spam folder too.</span></div>
   <p class="sub otp-dev hidden"></p></div>`;
  document.body.appendChild(back);document.body.classList.add("noscroll");
  const $q=s=>back.querySelector(s),boxes=[...back.querySelectorAll(".otp-boxes input")],go=$q(".otp-go"),re=$q(".otp-re"),msg=$q(".otp-msg"),tm=$q(".otp-timer");
  const code=()=>boxes.map(b=>b.value).join(""),fmt=t=>Math.floor(t/60)+":"+String(t%60).padStart(2,"0");
  const say=(t,k)=>{msg.textContent=t||"";msg.className="otp-msg "+(k||"")};
  function paint(){
    $q(".otp-to").innerHTML=(info.sent_to&&info.sent_to.length?"We sent a 6-digit code to <b>"+info.sent_to.map(esc).join(" and ")+"</b>.":"A code was sent a moment ago. Use that code, or resend a new one.")+" Enter it below.";
    const d=$q(".otp-dev");if(info.dev_outbox){d.classList.remove("hidden");d.innerHTML='Development mode: no email service is set up, so the message is in the <a href="/dev/outbox" target="_blank" rel="noopener">local inbox</a> on this computer.'}else d.classList.add("hidden")}
  function tick(){
    if(closed)return;
    if(lockLeft>0){lockLeft--;tm.textContent="Try again in "+fmt(lockLeft);if(lockLeft===0){say("You can ask for a new code now.","");re.disabled=cool>0;boxes.forEach(b=>b.disabled=false);tm.textContent=""}}
    else if(left>0){left--;tm.innerHTML="This code expires in <b>"+fmt(left)+"</b>";if(left===0){say("This code has expired. Tap Resend to get a new one.","bad");go.disabled=true}}
    if(cool>0)cool--;
    re.textContent=cool>0?"Resend code in "+cool+"s":"Resend code";re.disabled=cool>0||busyNow||lockLeft>0&&false}
  const iv=setInterval(tick,1000);
  function close(why){if(closed)return;closed=true;clearInterval(iv);back.remove();document.body.classList.remove("noscroll");document.removeEventListener("keydown",key,true);try{last&&last.focus()}catch(e){}if(why==="cancel"&&o.onCancel)o.onCancel()}
  function key(e){if(e.key==="Escape"){e.preventDefault();close("cancel")}
    if(e.key==="Tab"){const f=[...back.querySelectorAll("button:not([disabled]),input:not([disabled]),a")];if(!f.length)return;const a=f[0],z=f[f.length-1];
      if(e.shiftKey&&document.activeElement===a){e.preventDefault();z.focus()}else if(!e.shiftKey&&document.activeElement===z){e.preventDefault();a.focus()}}}
  document.addEventListener("keydown",key,true);
  const sync=()=>{go.disabled=code().length<6||busyNow||left===0||boxes[0].disabled};
  boxes.forEach((b,i)=>{
    b.oninput=()=>{b.value=b.value.replace(/\D/g,"").slice(-1);if(b.value&&i<5)boxes[i+1].focus();sync();if(code().length===6&&!go.disabled)submit()};
    b.onkeydown=e=>{if(e.key==="Backspace"&&!b.value&&i>0){boxes[i-1].focus();boxes[i-1].value=""}else if(e.key==="ArrowLeft"&&i>0)boxes[i-1].focus();else if(e.key==="ArrowRight"&&i<5)boxes[i+1].focus();else if(e.key==="Enter"&&!go.disabled)submit()};
    b.onpaste=e=>{const t=((e.clipboardData||window.clipboardData).getData("text")||"").replace(/\D/g,"").slice(0,6);if(!t)return;e.preventDefault();[...t].forEach((c,k)=>boxes[k].value=c);boxes[Math.min(t.length,5)].focus();sync();if(t.length===6)submit()};
    b.onfocus=()=>b.select()});
  async function submit(){
    if(busyNow||code().length<6)return;busyNow=true;go.disabled=true;go.textContent="Checking…";say("");
    try{const r=await o.verify(code(),info);say("Code verified. Please wait…","good");setTimeout(()=>{close("done");o.onDone&&o.onDone(r,info)},350)}
    catch(x){busyNow=false;go.textContent="Verify";
      if(x.state==="locked"){lockLeft=Math.max(x.retry||300,1);boxes.forEach(b=>{b.value="";b.disabled=true});say(x.message,"bad");go.disabled=true}
      else if(x.state==="expired"){left=0;boxes.forEach(b=>b.value="");say(x.message,"bad");go.disabled=true;boxes[0].focus()}
      else if(x.state==="wrong"){say(x.message,"bad");boxes.forEach(b=>b.value="");boxes[0].focus();sync()}
      else{say(x.message,"bad");sync()}}}
  go.onclick=submit;$q(".otp-x").onclick=()=>close("cancel");
  re.onclick=async()=>{if(cool>0||busyNow)return;busyNow=true;re.disabled=true;say("");
    try{info=await o.resend(info);left=info.remaining||info.ttl||300;cool=info.cooldown||30;lockLeft=0;boxes.forEach(b=>{b.value="";b.disabled=false});paint();say("A new code was sent. The older code no longer works.","good");busyNow=false;sync();boxes[0].focus()}
    catch(x){busyNow=false;if(x.state==="cooldown")cool=x.retry||30;say(x.message,"bad");if(x.state==="locked"){lockLeft=Math.max(x.retry||300,1);boxes.forEach(b=>{b.value="";b.disabled=true})}}
    sync();tick()};
  paint();tick();boxes[0].focus();if(info.already_sent)say("A code was sent a moment ago. Please use it, or wait to resend.","");
  return {close:()=>close("done")}}
function countUp(el,to,dec){const t0=performance.now();const f=t=>{const k=Math.min(1,(t-t0)/900),v=to*(1-Math.pow(1-k,3));el.textContent=dec?v.toFixed(dec):n(Math.round(v));if(k<1)requestAnimationFrame(f)};requestAnimationFrame(f)}


function cols(data,color){const W=300,H=110,L=4,B=18,mx=Math.max(...data.map(d=>d[1]),1),bw=(W-L)/data.length;
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%" role="img">${data.map((d,i)=>{const h=(H-B-6)*d[1]/mx,x=L+i*bw+2;return `<rect x="${x}" y="${H-B-h}" width="${bw-4}" height="${Math.max(h,d[1]?2:0)}" rx="3" fill="${color||"var(--a1)"}" opacity=".85"><title>${d[0]}: ${d[1]}</title></rect>${i%3===0?`<text x="${x+bw/2-2}" y="${H-4}" text-anchor="middle" font-size="8" fill="var(--muted)">${d[0]}</text>`:""}`}).join("")}</svg>`}
const when=t=>t?new Date(t*1000).toLocaleString():"never";
function field(l,v){return `<div><span class="sub">${esc(l)}</span><div>${v==null||v===""?"—":esc(v)}</div></div>`}
/* ---------------- dashboard ---------------- */
async function renderDashboard(){const V=$("#view");
  const [o,y,t,c,h,hd]=await Promise.all([api("/api/overview"),api("/api/summary/summary_year"),api("/api/summary/summary_tier"),api("/api/summary/summary_category"),api("/api/summary/summary_hashtags"),api("/api/summary/summary_hour_weekday")]);
  const order=["Nano (<1K)","Micro (1K-10K)","Mid (10K-100K)","Macro (100K-1M)","Mega (1M+)"],tr=t.rows.sort((a,b)=>order.indexOf(a[0])-order.indexOf(b[0])),totAcc=tr.reduce((a,r)=>a+r[1],0),pctSmall=tr.filter(r=>/Nano|Micro/.test(r[0])).reduce((a,r)=>a+r[1],0)/totAcc*100;
  V.innerHTML=`<div class="grid kpis">
   <div class="glass card kpi"><span class="sub">Posts in the combined dataset</span><b data-c="${o.posts}">0</b><span class="sub"><i class="pulse"></i>2 datasets, 1 warehouse</span></div>
   <div class="glass card kpi"><span class="sub">Average likes per post</span><b data-c="${o.avg_likes}" data-d="1">0</b><span class="sub">${o.years[0]} to ${o.years[1]}</span></div>
   <div class="glass card kpi"><span class="sub">Unique accounts</span><b data-c="${o.accounts}">0</b><span class="sub">5 follower tiers</span></div>
   <div class="glass card kpi"><span class="sub">Content categories</span><b data-c="${o.categories}">0</b><span class="sub">in the posts dataset</span></div></div>
  <div class="grid two" style="margin-top:14px"><div class="glass card"><h3>Average likes per post by year, 2012 to 2026</h3><p class="sub">Real data runs to August ${o.years[1]}. The dotted part is a projection, not data.</p>${trendChart(y.rows,2026)}</div>
   <div class="glass card"><h3>Share of accounts by follower tier</h3><p class="sub">Percent of the ${n(totAcc)} accounts in each tier. ${pctSmall.toFixed(1)}% of accounts have fewer than 10,000 followers.</p>${pctBars(tr.map(r=>[r[0],r[1]/totAcc*100,r[1]]))}<div class="wrap" style="margin-top:14px"><table><tr><th>Follower tier</th><th class=n>Accounts</th><th class=n>Share</th></tr>${tr.map(r=>`<tr><td>${esc(r[0])}</td><td class=n>${n(r[1])}</td><td class=n>${fmtPct(r[1]/totAcc*100)}</td></tr>`).join("")}<tr><td><b>Total</b></td><td class=n><b>${n(totAcc)}</b></td><td class=n><b>100%</b></td></tr></table></div></div></div>
  <div class="grid eq" style="margin-top:14px"><div class="glass card"><h3>Top categories by average likes</h3>${bars(c.rows.slice(0,8).map(r=>[r[0].replace(/_/g," "),r[2]]),v=>v.toFixed(1))}</div>
   <div class="glass card"><h3>Hashtags per post vs average likes</h3><p class="sub">Combined dataset, 5 means 5 or more</p>${bars(h.rows.map(r=>[r[0]+(r[0]==5?"+":"")+" hashtags",r[2]]),v=>v.toFixed(1))}</div></div>
  <div class="glass card" style="margin-top:14px"><h3>Best time to post</h3><p class="sub">Engagement index = average likes at that hour (or weekday) divided by the average of all posts, times 100. Above 100 is better than typical. Hover a bar for details.</p>${timeChart(hd.rows)}</div>`;
  document.querySelectorAll("[data-c]").forEach(e=>countUp(e,+e.dataset.c,+e.dataset.d||0))}

/* ---------------- pipeline ---------------- */
async function renderPipeline(){const V=$("#view");
  const admin=CFG.kind==="admin";
  V.innerHTML=`<div class="glass card"><h3>Data lineage</h3><p class="sub">Two raw datasets → two clean datasets → one combined dataset → warehouse</p><div id="flow"><div class="skel"></div></div></div>
  <div class="grid eq" style="margin-top:14px"><div class="glass card"><h3>Reconciliation checks</h3><div class="wrap" id="checks"></div></div><div class="glass card"><h3>Processing steps</h3><div class="wrap" id="steps"></div></div></div>
  ${admin?`<div class="glass card" style="margin-top:14px"><h3>Run the pipeline <span class="badge">admin</span></h3><p class="sub">Replays the ETL from your clean files in data/raw (about 30 seconds), or cleans the raw files from scratch if the clean files are missing.</p><button class="btn p" id="run">Run ETL now</button> <span class="sub" id="st"></span><pre id="log">Log appears here…</pre></div>`:""}
  <div class="glass card" style="margin-top:14px"><h3>Combined dataset <span class="sub" id="mode"></span></h3>
  ${admin?`<div class="row" style="margin:8px 0"><input id="q" placeholder="Search text or hashtags" style="max-width:260px"><select id="src" style="max-width:180px"><option value="">Both sources</option><option value="posts_dataset">Posts dataset</option><option value="reach_dataset">Reach dataset</option></select><button class="btn" id="go">Search</button></div>`:""}
  <div class="wrap"><table id="grid"></table></div>${admin?`<div class="row" style="margin-top:10px"><button class="btn sm" id="pv">‹ Prev</button><span class="sub" id="pg"></span><button class="btn sm" id="nx">Next ›</button></div>`:""}</div>`;
  const pg={p:1,pages:1};
  async function lineage(){try{const L=await api("/api/etl/lineage"),d=L.datasets,B=(l,v,s)=>`<div class="node"><span>${l}</span><b>${n(v)}</b><span>${s}</span></div>`;
    V.querySelector("#flow").innerHTML=`<div class="flow"><div>${(d.raw_reach.rows==null?B("Raw dataset 1 (reach)","—","cleaned earlier"):B("Raw dataset 1 (reach)",d.raw_reach.rows,"rows"))}${(d.raw_posts.rows==null?B("Raw dataset 2 (posts)","—","cleaned earlier"):B("Raw dataset 2 (posts)",d.raw_posts.rows,"rows"))}</div><div class="wire"></div><div>${B("Clean dataset 1",d.clean_reach.rows,d.clean_reach.columns+" columns")}${B("Clean dataset 2",d.clean_posts.rows,d.clean_posts.columns+" columns")}</div><div class="wire"></div><div>${B("Combined dataset",d.combined.rows,d.combined.columns+" columns")}</div></div>`;
    V.querySelector("#checks").innerHTML=`<table><tr><th>Check</th><th class=n>Expected</th><th class=n>Actual</th><th></th></tr>${L.checks.map(c=>`<tr><td>${esc(c.name)}</td><td class=n>${n(c.expected)}</td><td class=n>${n(c.actual)}</td><td class="${c.ok?"ok":"no"}">${c.ok?"✓":"✗"}</td></tr>`).join("")}</table><p class="sub">Last run ${esc(L.generated)} · ${L.all_ok?"nothing was lost between steps":"mismatch found"}</p>`;
    V.querySelector("#steps").innerHTML=`<table><tr><th>Dataset</th><th>Step</th><th class=n>Before</th><th class=n>After</th><th class=n>Removed</th></tr>${L.steps.map(s=>`<tr><td>${s.dataset}</td><td>${esc(s.step)}</td><td class=n>${n(s.before)}</td><td class=n>${n(s.after)}</td><td class=n>${n(s.removed)}</td></tr>`).join("")}</table>`}
   catch(e){V.querySelector("#flow").innerHTML=`<p class="sub">${esc(e.message)}${admin?" Click “Run ETL now” below.":" Ask an admin to run the ETL."}</p>`}}
  async function grid(){V.querySelector("#mode").textContent=admin?"· full dataset":"· sample of 100 random rows";
    try{const D=await api(admin?`/api/data/combined?page=${pg.p}&size=50&q=${encodeURIComponent(V.querySelector("#q").value)}&source=${V.querySelector("#src").value}`:"/api/data/sample");
      V.querySelector("#grid").innerHTML=`<tr>${D.columns.map(c=>`<th>${c}</th>`).join("")}</tr>`+D.rows.map(r=>`<tr>${r.map((v,i)=>`<td class="${D.columns[i]==="text"?"t":""}" title="${esc(v)}">${esc(v)}</td>`).join("")}</tr>`).join("");
      if(admin){pg.pages=D.pages;V.querySelector("#pg").textContent=`Page ${D.page} of ${n(D.pages)} · ${n(D.total)} rows`}}catch(e){V.querySelector("#grid").innerHTML=`<tr><td class="sub">${esc(e.message)}</td></tr>`}}
  async function poll(){try{const s=await api("/api/etl/status");V.querySelector("#log").textContent=s.log.join("\n")||"Log appears here…";V.querySelector("#log").scrollTop=1e9;
    V.querySelector("#st").textContent=s.running?"Running…":s.error?"Failed: "+s.error:s.finished?"Finished "+s.finished:"";V.querySelector("#run").disabled=s.running;
    if(!s.running&&s.finished){lineage();grid()}return s.running}catch(e){return false}}
  if(admin){V.querySelector("#run").onclick=async()=>{try{await api("/api/etl/run",{method:"POST"});const t=setInterval(async()=>{if(!(await poll()))clearInterval(t)},1500);timers.push(t)}catch(e){toast(e.message,"bad")}};
    V.querySelector("#go").onclick=()=>{pg.p=1;grid()};V.querySelector("#pv").onclick=()=>{if(pg.p>1){pg.p--;grid()}};V.querySelector("#nx").onclick=()=>{if(pg.p<pg.pages){pg.p++;grid()}};V.querySelector("#q").onkeydown=e=>{if(e.key==="Enter"){pg.p=1;grid()}};poll()}
  lineage();grid()}


/* ---------------- data mining report (shared: user "Data Mining" page and admin "Mining Lab") ---------------- */
function usd(x){return "$"+Math.round(x).toLocaleString("en-US")}
function liftRows(rows){return rows.map(r=>{const w=Math.min(Math.abs(r.lift-1)*100,50)*2,pos=r.lift>=1;return `<div class="lift"><span>${esc(r.label)}</span><div class="t"><i style="left:50%;width:${w/2}%;${pos?"":"transform:translateX(-100%);"}background:${pos?"var(--good)":"var(--bad)"}"></i></div><em>${r.lift}× · ${n(r.posts)} posts</em></div>`}).join("")}
function chipsOf(ws,cls){return `<div class="chips">${ws.map(w=>`<span class="chip ${cls}" title="beat the model in ${w.pct_beat}% of captions with it, fell short in ${w.pct_short}%">${esc(w.word)}<small>${w.pct_beat}% / ${w.pct_short}%</small></span>`).join("")}</div>`}
function miningBody(R,mine){const P=R.predictor,L=P.likes,C=P.comments,T=R.text,pe=R.personas;
  const top=P.importance[0],post=P.importance.filter(i=>["hashtags","mentions","caption_len","hour","weekday"].includes(i.feature)).reduce((a,i)=>a+i.pct,0);
  return `<div class="grid kpis"><div class="glass card kpi"><span class="sub">Posts mined</span><b>${n(R.rows)}</b><span class="sub">trained ${esc(R.trained_at)} in ${R.seconds}s</span></div>
   <div class="glass card kpi"><span class="sub">Likes model accuracy (R²)</span><b>${L.r2}</b><span class="sub">simple baseline ${L.baseline_r2}</span></div>
   <div class="glass card kpi"><span class="sub">Comments model accuracy (R²)</span><b>${C.r2}</b><span class="sub">simple baseline ${C.baseline_r2}</span></div>
   <div class="glass card kpi"><span class="sub">Caption model AUC</span><b>${T.auc}</b><span class="sub">0.5 = guessing, ${n(T.docs)} captions</span></div></div>
  <div class="glass card" style="margin-top:14px"><h3>1 · Engagement predictor <span class="badge">gradient boosting</span></h3>
   <p class="sub">Predicts likes and comments from audience size, posts so far, hashtags, mentions, caption length, hour, weekday, category and account type. It was trained on ${n(P.n_train)} posts and tested on ${n(P.n_test)} posts it had never seen.</p>
   <div class="grid eq"><div><table><tr><th>Hold-out test</th><th class=n>Likes</th><th class=n>Comments</th></tr>
    <tr><td>R² (1 = perfect)</td><td class=n>${L.r2}</td><td class=n>${C.r2}</td></tr><tr><td>R² of a simple "tier median" guess</td><td class=n>${L.baseline_r2}</td><td class=n>${C.baseline_r2}</td></tr>
    <tr><td>Average miss</td><td class=n>${L.mae} likes</td><td class=n>${C.mae} comments</td></tr><tr><td>Within a factor of 2 of the real number</td><td class=n>${L.within_2x_pct}%</td><td class=n>${C.within_2x_pct}%</td></tr></table>
    <div class="warn">${esc(top.label)} explains most of the prediction (${top.pct}%). The choices you control in a single post (hashtags, caption length, hour, weekday, mentions) add up to about ${post.toFixed(1)}%, so expect modest gains from them.</div></div>
   <div><h3>What drives engagement</h3><p class="sub">Share of the model's accuracy that depends on each feature</p>${bars(P.importance.map(i=>[i.label,i.pct]),v=>v+"%")}</div></div></div>
  <div class="glass card" style="margin-top:14px"><h3>2 · Creator personas <span class="badge">k-means</span></h3>
   <p class="sub">${n(pe.accounts)} accounts grouped by audience size, engagement rate and hashtag habit into ${pe.k} types (silhouette score ${pe.silhouette}; tested k = ${Object.entries(pe.silhouettes).map(([k,v])=>k+": "+v).join(", ")}).</p>
   <div class="pcards">${pe.items.map(p=>`<div class="pcard${mine&&mine.id===p.id?" me":""}"><h4>${esc(p.name)}${mine&&mine.id===p.id?' <span class="badge">you</span>':""}</h4><span class="sub">${n(p.accounts)} accounts · ${p.share_pct}%</span>
     <div class="big">${n(p.median_followers)} <span class="sub">median followers</span></div><div class="sub">${p.median_engagement_pct}% median engagement · ${p.mean_likes} avg likes</div>
     <ul><li>${p.hashtags} hashtags per post, ${p.caption_len}-character captions</li><li>${p.business_pct}% business accounts</li><li>Best hour: ${p.best_hour==null?"n/a":String(p.best_hour).padStart(2,"0")+":00"}</li>
     <li>Mostly: ${p.top_categories.map(c=>esc(c.name)+" "+c.pct+"%").join(", ")}</li><li>Their top performers use about ${p.top_performers.hashtags} hashtags and ${p.top_performers.caption_len}-character captions</li></ul></div>`).join("")}</div></div>
  <div class="glass card" style="margin-top:14px"><h3>3 · Caption text mining <span class="badge">TF-IDF + logistic regression</span></h3>
   <p class="sub">${esc(T.note)}</p><div class="grid eq"><div><h3>Words linked to beating the model</h3>${chipsOf(T.beat_words,"up")}<p class="sub">Percentages: share of over-performing / under-performing captions containing the word.</p></div>
   <div><h3>Words linked to falling short</h3>${chipsOf(T.short_words,"dn")}</div></div>
   <h3 style="margin-top:12px">Caption structure (lift 1.0 = average, base rate ${T.base_rate_pct}%)</h3>${liftRows(T.structure)}
   <p class="sub">The caption model's AUC of ${T.auc} means wording is only a weak signal. That is a real finding, not a fault: audience size matters far more than words.</p></div>
  <div class="glass card" style="margin-top:14px"><h3>4 · Breakout detector</h3><p class="sub">Posts that got far more likes than the model expected (at least 30 likes). Of ${n(R.breakouts.eligible_posts)} such posts, <b>${n(R.breakouts.counts.ge3)}</b> reached 3× the expectation, <b>${n(R.breakouts.counts.ge5)}</b> reached 5× and <b>${n(R.breakouts.counts.ge10)}</b> reached 10×.${R.breakouts.items?"":" The list of individual posts is available to administrators."}</p></div>`}

/* ---------------- shell (shared by both portals) ---------------- */
function enter(u){ME=u;$("#auth").classList.add("hidden");$("#app").classList.remove("hidden");
  $("#meName").textContent=u.name;$("#meRole").textContent=u.role;$("#meEmail").textContent=u.email;
  if(u.must_change&&typeof forceChange==="function"){$("#menu").innerHTML="";forceChange();return}
  let h="",g="";CFG.pages.forEach(p=>{if(p.g!==g){g=p.g;h+=`<small>${g}</small>`}h+=`<a class="item" data-p="${p.id}" tabindex="0" role="link"><span>${p.i}</span>${p.t}</a>`});
  $("#menu").innerHTML=h;route()}
$("#menu").onclick=e=>{const a=e.target.closest("[data-p]");if(a)location.hash=a.dataset.p};
$("#menu").onkeydown=e=>{if(e.key==="Enter"){const a=e.target.closest("[data-p]");if(a)location.hash=a.dataset.p}};
window.onhashchange=()=>ME&&!ME.must_change&&route();
function route(){timers.forEach(clearInterval);timers=[];
  let id=location.hash.slice(1);let p=CFG.pages.find(x=>x.id===id)||CFG.pages[0];
  document.querySelectorAll("#menu .item").forEach(a=>a.classList.toggle("on",a.dataset.p===p.id));
  const ov=$("#view"),nv=document.createElement("div");nv.id="view";ov.replaceWith(nv);   // each page draws into its own container
  $("#title").textContent=p.t;$("#crumb").textContent=p.g+" / "+p.t;$("#view").innerHTML='<div class="glass card"><div class="skel" style="width:40%"></div><div class="skel"></div><div class="skel" style="width:80%"></div></div>';
  api("/api/track",{method:"POST",body:{page:p.id}}).catch(()=>{});
  Promise.resolve(p.r()).catch(e=>{$("#view").innerHTML=`<div class="glass card"><h3>Could not load this page</h3><p class="sub">${esc(e.message)}</p></div>`})}
function frame(id,src){$("#view").innerHTML=`<iframe class="mod" title="${id}" src="${src}"></iframe>`;
  const f=$("iframe.mod");f.onload=()=>f.contentWindow.postMessage({type:"theme",value:document.documentElement.getAttribute("data-theme")},"*")}
async function busy(btn,fn){btn.disabled=true;try{return await fn()}finally{btn.disabled=false}}
async function doLogout(){try{await api(CFG.base+"/logout",{method:"POST"})}catch(e){}ME=null;location.hash="";showAuth()}
$("#logout").onclick=doLogout;
/* phone menu: the side menu slides in over the page instead of pushing the content down */
(()=>{const b=$("#navBtn"),k=$("#navBack");if(!b)return;const set=o=>{document.body.classList.toggle("navopen",o);b.setAttribute("aria-expanded",o?"true":"false")};
  b.onclick=()=>set(!document.body.classList.contains("navopen"));k.onclick=()=>set(false);addEventListener("hashchange",()=>set(false));addEventListener("keydown",e=>{if(e.key==="Escape")set(false)})})();

/* password strength meter, used on sign-up, reset and change forms */
function strength(pw){let s=0;if(pw.length>=8)s++;if(pw.length>=12)s++;if(/[a-z]/.test(pw)&&/[A-Z]/.test(pw))s++;if(/\d/.test(pw))s++;if(/[^A-Za-z0-9]/.test(pw))s++;return s}
function meter(input,out){const f=()=>{const s=strength(input.value),L=["Too weak","Weak","Fair","Good","Strong","Very strong"];out.innerHTML=input.value?`<i style="width:${s*20}%;background:${s<3?"var(--bad)":s<4?"var(--warn)":"var(--good)"}"></i><span>${L[s]}</span>`:""};input.addEventListener("input",f)}
/* ---------------- command palette ---------------- */
function openPal(){if($("#pal")||!ME)return;const items=CFG.pages;const d=document.createElement("div");d.id="pal";
  d.innerHTML=`<div class="glass box"><input id="pi" placeholder="Jump to a page…"><div id="pl"></div></div>`;document.body.appendChild(d);const i=$("#pi");i.focus();
  const draw=()=>{const q=i.value.toLowerCase();$("#pl").innerHTML=items.filter(p=>p.t.toLowerCase().includes(q)).map(p=>`<a data-p="${p.id}">${p.i} ${p.t}</a>`).join("")};draw();i.oninput=draw;
  d.onclick=e=>{const a=e.target.closest("[data-p]");if(a){location.hash=a.dataset.p;d.remove()}else if(e.target===d)d.remove()};
  i.onkeydown=e=>{if(e.key==="Escape")d.remove();if(e.key==="Enter"){const a=$("#pl a");if(a){location.hash=a.dataset.p;d.remove()}}}}
$("#palBtn")&&($("#palBtn").onclick=openPal);document.addEventListener("keydown",e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="k"){e.preventDefault();openPal()}});


/* ---- build check: warns when the folder mixes files from different zips (e.g. an old index.html with new scripts) ---- */
const BUILD="5.7";
(async function checkBuild(){
  let srv=null;try{srv=(await(await fetch("/api/version",{cache:"no-store"})).json()).build}catch(e){}
  const meta=(document.querySelector('meta[name="iw-build"]')||{}).content||"old";
  const css=(getComputedStyle(document.documentElement).getPropertyValue("--iw-build")||"").replace(/["' ]/g,"")||"old";
  const js=typeof PAGE_JS_BUILD!=="undefined"?PAGE_JS_BUILD:"old";
  const bad=[];if(srv!==null&&srv!==BUILD)bad.push("main.py or common.js");if(meta!==BUILD)bad.push("the page (index.html / admin.html)");if(css!==BUILD)bad.push("app.css");if(js!==BUILD)bad.push("user.js / admin.js");
  if(!bad.length)return;
  const d=document.createElement("div");d.className="buildwarn";
  d.innerHTML="Some files in your project folder are from an older version ("+bad.join(", ")+"). Delete the old folder, unzip the newest <b>instawarehouse.zip</b> completely, restart the server and press Ctrl+F5.";
  document.body.appendChild(d);
})();
