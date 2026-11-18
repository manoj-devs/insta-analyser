"use strict";
const PAGE_JS_BUILD="5.7";
/* ADMIN PORTAL: password + emailed code sign-in, then the control pages */
CFG={kind:"admin",base:"/api/admin/auth",pages:[
 {id:"overview",t:"Overview",i:"◈",g:"Control",r:overviewPlus},
 {id:"users",t:"Users",i:"☰",g:"Control",r:renderUsers},
 {id:"activity",t:"Activity & Alerts",i:"⚑",g:"Control",r:renderActivity},
 {id:"submissions",t:"Collected Data",i:"▤",g:"Control",r:renderSubmissions},
 {id:"dashboard",t:"Warehouse Dashboard",i:"▣",g:"Warehouse",r:renderDashboard},
 {id:"pipeline",t:"ETL & Full Dataset",i:"⇄",g:"Warehouse",r:renderPipeline},
 {id:"regions",t:"Regions & Directory",i:"◍",g:"Warehouse",r:renderRegions},
 {id:"lab",t:"Mining Lab",i:"✦",g:"Warehouse",r:renderLab},
 {id:"reports",t:"Reports",i:"▤",g:"Warehouse",r:()=>reportsPage($("#view"))},
 {id:"cube",t:"3D OLAP Cube",i:"◆",g:"Warehouse",r:()=>frame("cube","/static/modules/cube.html")},
 {id:"schema",t:"Star & Snowflake",i:"❄",g:"Warehouse",r:()=>frame("schema","/static/modules/schema.html?embed=1")},
 {id:"tcp",t:"TCP Link",i:"⇆",g:"System",r:()=>tcpPage($("#view"))},
 {id:"admins",t:"Admins & Security",i:"⛨",g:"System",r:adminsPlus}]};

/* ---------------- sign-in ---------------- */
function showAuth(msg){$("#app").classList.add("hidden");$("#auth").classList.remove("hidden");$("#fIn").classList.remove("hidden");$("#inErr").textContent=msg||""}
$("#fIn").onsubmit=async e=>{e.preventDefault();$("#inErr").textContent="";
  try{const r=await busy($("#inBtn"),()=>api("/api/admin/auth/login",{method:"POST",body:{email:$("#inEmail").value,password:$("#inPw").value}}));$("#inPw").value="";
    if(r.step==="done"){enter(r.user);return}
    otpPopup({title:"Confirm it is you",info:r,
      verify:(code,i)=>api("/api/admin/auth/verify",{method:"POST",body:{email:i.email,code,ticket:i.ticket}}),
      resend:i=>api("/api/admin/auth/resend",{method:"POST",body:{email:i.email,ticket:i.ticket}}),
      onDone:res=>enter(res.user),onCancel:()=>showAuth()})}
  catch(x){$("#inErr").textContent=x.message}};

/* first sign-in with the default password: nothing else works until it is changed */
function forceChange(){$("#title").textContent="Set a new password";$("#crumb").textContent="Required before you continue";
  $("#view").innerHTML=`<div class="glass card" style="max-width:480px"><h3>Change the default password</h3><p class="sub">This account still uses a password that is known to everyone who has this project. Choose your own.</p>
  <form id="cf"><label class="f">Current password<input id="cp" type="password" autocomplete="current-password" required></label>
  <label class="f">New password<input id="np" type="password" autocomplete="new-password" required></label><div class="meter" id="nm"></div>
  <label class="f">Repeat new password<input id="np2" type="password" autocomplete="new-password" required></label>
  <div class="err" id="ce"></div><button class="btn p">Save and continue</button></form></div>`;
  meter($("#np"),$("#nm"));
  $("#cf").onsubmit=async e=>{e.preventDefault();$("#ce").textContent="";
    if($("#np").value!==$("#np2").value){$("#ce").textContent="The two new passwords do not match.";return}
    try{await api("/api/admin/auth/password",{method:"POST",body:{current:$("#cp").value,new:$("#np").value}});toast("Password changed","good");const u=await api("/api/admin/auth/me");enter(u)}catch(x){$("#ce").textContent=x.message}}}

/* ---------------- overview ---------------- */
async function renderOverview(){const V=$("#view");
  const [O,A]=await Promise.all([api("/api/admin/overview"),api("/api/admin/alerts")]),k=O.kpi,d=O.dist;
  const K=(l,v,s,dec)=>`<div class="glass card kpi"><span class="sub">${l}</span><b data-c="${v}"${dec?` data-d="${dec}"`:""}>0</b><span class="sub">${s}</span></div>`;
  const B=(rows,fmt)=>rows.length?bars(rows,fmt):'<p class="sub">No data yet.</p>';
  V.innerHTML=`<div class="grid kpis">${K("Verified users",k.users,k.pending+" waiting to verify email")}${K("Online now",k.online,"active in the last 5 minutes")}
   ${K("New users, 7 days",k.signups_7d,k.blocked+" blocked · "+k.deleted+" removed")}${K("Sign-ins, 24 hours",k.logins_24h,k.failed_24h+" failed attempts")}
   ${K("Analyses submitted",k.analyses,k.analyses_7d+" in the last 7 days")}${K("Average health score",k.avg_score,"across all submissions",1)}
   ${K("Feedback received",k.feedback,k.feedback?"average rating "+k.avg_rating+" / 5":"none yet")}${K("Administrators",k.admins,"2-step sign-in")}</div>
  ${A.length?`<div class="glass card" style="margin-top:14px;border-color:var(--bad)"><h3>⚑ ${A.length} suspicious activity alert(s)</h3>${A.slice(0,3).map(a=>`<p class="sub"><b>${esc(a.type)}</b>: ${esc(a.detail)}</p>`).join("")}<a class="btn sm" href="#activity">Review alerts</a></div>`:""}
  <div class="grid" style="grid-template-columns:repeat(3,1fr);margin-top:14px">
   <div class="glass card"><h3>New users per day</h3><p class="sub">Last 14 days</p>${cols(O.series.signups,"var(--a2)")}</div>
   <div class="glass card"><h3>Sign-ins per day</h3><p class="sub">Last 14 days</p>${cols(O.series.logins,"var(--a1)")}</div>
   <div class="glass card"><h3>Analyses per day</h3><p class="sub">Last 14 days</p>${cols(O.series.analyses,"var(--a3)")}</div></div>
  <div class="grid eq" style="margin-top:14px"><div class="glass card"><h3>Who our users are</h3><p class="sub">Collected at sign-up</p>${B(d.user_type.map(r=>[r[0].replace(/_/g," "),r[1]]))}<h3 style="margin-top:14px">Top countries</h3>${B(d.country)}</div>
   <div class="glass card"><h3>Accounts analysed</h3><p class="sub">Follower tier and category of submitted accounts</p>${B(d.tier)}<h3 style="margin-top:14px">Top categories</h3>${B(d.category.map(r=>[r[0].replace(/_/g," "),r[1]]))}</div></div>
  <div class="grid eq" style="margin-top:14px"><div class="glass card"><h3>Most used pages</h3><p class="sub">Last 30 days, all signed-in people</p>${B(d.pages)}</div>
   <div class="glass card"><h3>Health score spread</h3><p class="sub">How submitted accounts score</p>${B(d.score)}</div></div>`;
  document.querySelectorAll("[data-c]").forEach(e=>countUp(e,+e.dataset.c,+e.dataset.d||0))}

/* ---------------- users ---------------- */
async function renderUsers(){const V=$("#view");
  V.innerHTML=`<div class="glass card"><div class="row" style="justify-content:space-between"><h3>Users</h3><a class="btn sm" href="/api/admin/users.csv">⬇ Export CSV</a></div>
  <p class="sub">People sign in right after verifying their email. Block or remove anyone at any time: they are signed out instantly and see your reason.</p>
  <div class="search"><input id="uq" placeholder="Search name, email or handle"><select id="us"><option value="">All statuses</option><option value="active">Active</option><option value="blocked">Blocked</option><option value="deleted">Removed</option><option value="pending">Not verified</option></select></div>
  <div class="wrap" style="max-height:none"><table id="ut"></table></div></div>`;
  async function load(){const U=await api(`/api/admin/users?q=${encodeURIComponent(V.querySelector("#uq").value)}&status=${V.querySelector("#us").value}`);
    V.querySelector("#ut").innerHTML=`<tr><th>Name</th><th>Email</th><th>Type</th><th>Country</th><th>Status</th><th class=n>Sign-ins</th><th>Last sign-in</th><th class=n>Analyses</th><th></th></tr>`+
    (U.length?U.map(u=>`<tr><td><a href="#" data-open="${u.id}">${esc(u.name)}</a><div class="sub">${esc(u.handle||"")}</div></td><td>${esc(u.email)}</td><td>${esc((u.user_type||"").replace(/_/g," "))}</td><td>${esc(u.country||"")}</td>
    <td><span class="pill ${u.verified?u.status:"pending"}">${u.verified?u.status:"not verified"}</span>${u.reason?`<div class="sub">${esc(u.reason)}</div>`:""}</td><td class=n>${n(u.login_count||0)}</td><td>${ago(u.last_login)}</td><td class=n>${u.analyses}</td>
    <td style="white-space:nowrap">${u.status==="active"?`<button class="btn sm d" data-a="block" data-id="${u.id}">Block</button> `:u.status==="blocked"?`<button class="btn sm" data-a="unblock" data-id="${u.id}">Unblock</button> `:""}${u.status!=="deleted"?`<button class="btn sm d" data-a="delete" data-id="${u.id}">Delete</button>`:""}</td></tr>`).join(""):`<tr><td colspan="9" class="sub">No users found.</td></tr>`)}
  await load();let tm;V.querySelector("#uq").oninput=()=>{clearTimeout(tm);tm=setTimeout(load,250)};V.querySelector("#us").onchange=load;
  V.onclick=async e=>{const o=e.target.closest("[data-open]");if(o){e.preventDefault();return openUser(+o.dataset.open,load)}
    const b=e.target.closest("[data-a]");if(b)act(b.dataset.a,b.dataset.id,load)}}
async function act(a,id,done){let body={};
  if(a==="block"||a==="delete"){const r=await ask(a==="block"?"Block this user":"Delete this user","Reason (required)");if(r===null)return;body={reason:r}}
  try{await api(`/api/admin/users/${id}/${a}`,{method:"POST",body});toast("Done","good");done&&done()}catch(x){toast(x.message,"bad")}}
async function openUser(id,reload){const D=await api("/api/admin/users/"+id),p=D.profile;
  const d=document.createElement("div");d.className="drawer";
  d.innerHTML=`<div class="panel"><div class="row" style="justify-content:space-between"><h3>${esc(p.name)} <span class="pill ${p.status}">${p.status}</span></h3><button class="btn sm" id="x">Close ✕</button></div>
  <div class="kv">${field("Email",p.email)}${field("Phone",p.phone)}${field("Country",p.country)}${field("Type",(p.user_type||"").replace(/_/g," "))}${field("Instagram handle",p.handle)}${field("Interests",p.interests)}
  ${field("Joined",when(p.created))}${field("Last sign-in",when(p.last_login))}${field("Sign-ins",p.login_count)}${field("Signed up from",p.signup_ip)}${field("Consent given",when(p.consent_at))}${field("Password changed",when(p.pw_changed))}</div>
  ${p.reason?`<div class="tip" style="border-color:var(--bad)"><b>Reason on file</b>${esc(p.reason)}</div>`:""}
  <div class="row" style="margin:10px 0"><button class="btn sm" data-x="logout">Sign out everywhere (${D.sessions.length})</button>${p.status==="active"?'<button class="btn sm d" data-x="block">Block</button>':p.status==="blocked"?'<button class="btn sm" data-x="unblock">Unblock</button>':""}${p.status!=="deleted"?'<button class="btn sm d" data-x="delete">Delete</button>':""}</div>
  <h3 style="margin-top:14px">Accounts analysed</h3>${D.analyses.length?`<table><tr><th>When</th><th>Handle</th><th class=n>Followers</th><th class=n>Score</th><th class=n>Est./month</th></tr>${D.analyses.map(a=>`<tr><td>${when(a.ts)}</td><td>${esc(a.handle)}</td><td class=n>${n(a.followers)}</td><td class=n>${a.score}</td><td class=n>${inr(a.income_monthly)}</td></tr>`).join("")}</table>`:'<p class="sub">None.</p>'}
  <h3 style="margin-top:14px">Pages used</h3>${D.pages.length?bars(D.pages):'<p class="sub">No visits recorded.</p>'}
  <h3 style="margin-top:14px">Recent activity</h3><table>${D.history.map(h=>`<tr><td>${when(h.ts)}</td><td>${esc(h.event)}</td><td>${esc(dev(h.ua))} ${esc(h.ip)}</td></tr>`).join("")}</table></div>`;
  document.body.appendChild(d);d.onclick=async e=>{if(e.target===d||e.target.id==="x")return d.remove();
    const b=e.target.closest("[data-x]");if(!b)return;
    if(b.dataset.x==="logout"){try{const r=await api(`/api/admin/users/${id}/logout`,{method:"POST"});toast(r.closed+" session(s) closed","good");d.remove();openUser(id,reload)}catch(x){toast(x.message,"bad")}return}
    await act(b.dataset.x,id,()=>{d.remove();reload&&reload()})}}

/* ---------------- activity ---------------- */
async function renderActivity(){const V=$("#view");let filt={event:"",email:""};
  V.innerHTML=`<div id="act"></div>`;const A=V.querySelector("#act");
  async function load(){const [on,al,au]=await Promise.all([api("/api/admin/online",{bg:true}),api("/api/admin/alerts",{bg:true}),api(`/api/admin/audit?limit=300&event=${filt.event}&email=${encodeURIComponent(filt.email)}`,{bg:true})]);
    const focus=document.activeElement&&document.activeElement.id;
    A.innerHTML=`<div class="grid eq"><div class="glass card"><h3><i class="pulse"></i>Online now (${on.length})</h3><p class="sub">Active in the last 5 minutes · refreshes every 15 seconds</p>${on.length?`<table><tr><th>Name</th><th>Portal</th><th>Device</th><th>Last seen</th></tr>${on.map(o=>`<tr><td>${esc(o.name)}</td><td>${o.kind}</td><td>${esc(dev(o.ua))} · ${esc(o.ip)}</td><td>${ago(o.last_seen)}</td></tr>`).join("")}</table>`:'<p class="sub">Nobody right now.</p>'}</div>
    <div class="glass card"><h3>Suspicious activity (${al.length})</h3><p class="sub">Failed sign-ins, repeated sign-ups from one device, very fast requests, admin account used on the user portal</p>${al.length?al.map(a=>`<div class="tip" style="border-color:${a.severity==="high"?"var(--bad)":"var(--warn)"}"><b>${esc(a.type)}</b>${esc(a.detail)}<div style="margin-top:6px">${a.user_ids.map(id=>`<button class="btn sm d" data-block="${id}">Block user ${id}</button> `).join("")}</div></div>`).join(""):'<p class="sub">Nothing suspicious.</p>'}</div></div>
    <div class="glass card" style="margin-top:14px"><div class="row" style="justify-content:space-between"><h3>Sign-in, sign-out and security history</h3><a class="btn sm" href="/api/admin/audit.csv">⬇ Download CSV</a></div>
    <div class="search"><input id="fe" placeholder="Filter by email" value="${esc(filt.email)}"><select id="fv"><option value="">All events</option>${["login_success","login_fail","login_denied","logout","signup","verify","password_changed","password_reset","reset_request","blocked","unblocked","deleted","forced_logout","admin_created","rate_limited","feedback","data_export"].map(x=>`<option${x===filt.event?" selected":""}>${x}</option>`).join("")}</select></div>
    <div class="wrap"><table><tr><th>Time</th><th>Email</th><th>Event</th><th>Device</th><th>Detail</th></tr>${au.map(a=>`<tr><td>${when(a.ts)}</td><td>${esc(a.email||"")}</td><td><span class="pill ${/fail|denied|blocked|deleted|rate/.test(a.event)?"blocked":"active"}">${a.event}</span></td><td>${esc(dev(a.ua))} · ${esc(a.ip)}</td><td>${esc(a.detail||"")}</td></tr>`).join("")}</table></div></div>`;
    A.querySelector("#fv").onchange=e=>{filt.event=e.target.value;load()};let t;A.querySelector("#fe").oninput=e=>{clearTimeout(t);t=setTimeout(()=>{filt.email=e.target.value;load().then(()=>{const f=A.querySelector("#fe");f.focus();f.setSelectionRange(f.value.length,f.value.length)})},400)};
    if(focus==="fe"){const f=A.querySelector("#fe");f.focus();f.setSelectionRange(f.value.length,f.value.length)}}
  await load();timers.push(setInterval(()=>{if(location.hash==="#activity"&&!document.querySelector(".modal"))load().catch(()=>{})},15000));
  V.onclick=async e=>{const b=e.target.closest("[data-block]");if(!b)return;act("block",b.dataset.block,load)}}

/* ---------------- collected data ---------------- */
async function renderSubmissions(){const V=$("#view");const [S,F,LK]=await Promise.all([api("/api/admin/analyses"),api("/api/admin/feedback"),api("/api/admin/lookups")]),g=S.agg;
  V.innerHTML=`<div class="grid kpis"><div class="glass card kpi"><span class="sub">Accounts analysed</span><b>${n(g.total)}</b><span class="sub">by ${g.unique_users} people</span></div>
   <div class="glass card kpi"><span class="sub">Average health score</span><b>${g.avg_score}</b></div><div class="glass card kpi"><span class="sub">Average followers</span><b>${n(g.avg_followers)}</b></div>
   <div class="glass card kpi"><span class="sub">Average monthly estimate</span><b>${inr(g.avg_monthly_income)}</b><span class="sub">illustrative rates</span></div></div>
  <div class="grid eq" style="margin-top:14px"><div class="glass card"><h3>By follower tier</h3>${g.by_tier.length?`<table><tr><th>Tier</th><th class=n>Accounts</th><th class=n>Avg score</th><th class=n>Avg ₹/month</th></tr>${g.by_tier.map(r=>`<tr><td>${esc(r[0])}</td><td class=n>${r[1]}</td><td class=n>${r[2]}</td><td class=n>${inr(r[3])}</td></tr>`).join("")}</table>`:'<p class="sub">No submissions yet.</p>'}</div>
   <div class="glass card"><h3>By category</h3>${g.by_category.length?`<table><tr><th>Category</th><th class=n>Accounts</th><th class=n>Avg score</th><th class=n>Avg likes</th></tr>${g.by_category.map(r=>`<tr><td>${esc(r[0].replace(/_/g," "))}</td><td class=n>${r[1]}</td><td class=n>${r[2]}</td><td class=n>${r[3]}</td></tr>`).join("")}</table>`:'<p class="sub">No submissions yet.</p>'}</div></div>
  <div class="glass card" style="margin-top:14px"><div class="row" style="justify-content:space-between"><h3>All submissions</h3><a class="btn sm" href="/api/admin/analyses.csv">⬇ Export CSV</a></div>
   <div class="wrap"><table><tr><th>When</th><th>User</th><th>Handle</th><th class=n>Followers</th><th>Tier</th><th>Category</th><th class=n>Likes</th><th class=n>Hashtags</th><th class=n>Score</th><th class=n>₹/month</th></tr>
   ${S.rows.map(r=>`<tr><td>${when(r.ts)}</td><td>${esc(r.name||"")}<div class="sub">${esc(r.email||"")}</div></td><td>${esc(r.handle)}</td><td class=n>${n(r.followers)}</td><td>${esc(r.tier)}</td><td>${esc(r.category.replace(/_/g," "))}</td><td class=n>${r.avg_likes}</td><td class=n>${r.hashtags}</td><td class=n>${r.score}</td><td class=n>${inr(r.income_monthly)}</td></tr>`).join("")||'<tr><td colspan="10" class="sub">No submissions yet.</td></tr>'}</table></div></div>
  <div class="glass card" style="margin-top:14px"><h3>Influencer and celebrity lookups (${LK.length})</h3><p class="sub">Public accounts users analysed in the Influencer Analyser, with the predicted fee.</p><div class="wrap"><table><tr><th>When</th><th>Looked up by</th><th>Name</th><th>Kind</th><th class=n>Followers</th><th>Category</th><th class=n>Next-post likes</th><th class=n>Fee (USD, low – mid – high)</th></tr>
   ${LK.map(l=>`<tr><td>${when(l.ts)}</td><td>${esc(l.email||"")}</td><td>${esc(l.name)}</td><td>${esc(l.kind)}</td><td class=n>${n(l.followers)}</td><td>${esc((l.category||"").replace(/_/g," "))}</td><td class=n>${n(l.next_likes)}</td><td class=n>${usd(l.fee_low_usd)} – ${usd(l.fee_mid_usd)} – ${usd(l.fee_high_usd)}</td></tr>`).join("")||'<tr><td colspan="8" class="sub">No lookups yet.</td></tr>'}</table></div></div>
  <div class="glass card" style="margin-top:14px"><h3>User feedback (${F.length})</h3>${F.length?F.map(f=>`<div class="tip"><b>${"★".repeat(f.rating)}${"☆".repeat(5-f.rating)} · ${esc(f.topic)}</b>${esc(f.message)}<br><small>${esc(f.name||"")} · ${when(f.ts)}</small></div>`).join(""):'<p class="sub">No feedback yet.</p>'}</div>`}

/* ---------------- mining lab ---------------- */
async function renderLab(){const V=$("#view");
  V.innerHTML=`<div class="glass card"><div class="row" style="justify-content:space-between"><div><h3>Train the mining models</h3><p class="sub">Retrains the engagement predictor, personas, caption model and breakout list from the warehouse (about a minute). Runs automatically after every ETL.</p></div><button class="btn p" id="tr">Train now</button></div><span class="sub" id="ts"></span><pre id="tl">Log appears here…</pre></div><div id="rep" style="margin-top:14px"></div><div id="brk" style="margin-top:14px"></div>`;
  async function body(){let R;try{R=await api("/api/mining/report")}catch(e){V.querySelector("#rep").innerHTML=`<div class="glass card"><p class="sub">${esc(e.message)}</p></div>`;return}
    V.querySelector("#rep").innerHTML=miningBody(R);const B=await api("/api/admin/mining/breakouts");
    V.querySelector("#brk").innerHTML=`<div class="glass card"><h3>Breakout posts (top ${B.items.length})</h3><p class="sub">Account names are masked. “Expected” is what the predictor forecast; ratios above 100× usually mean the post went viral far beyond the account's normal reach. Forecasts for accounts above 10 million followers are the least reliable because the data has few of them.</p>
    <div class="wrap" style="max-height:640px"><table><tr><th class=n>Ratio</th><th>Account</th><th class=n>Followers</th><th class=n>Likes</th><th class=n>Expected</th><th>Category</th><th>Caption and why it did well</th></tr>${B.items.map(b=>`<tr><td class=n><b>${b.ratio}×</b></td><td>${esc(b.account)}</td><td class=n>${n(b.followers)}</td><td class=n>${n(b.likes)}</td><td class=n>${n(b.expected)}</td><td>${esc(b.category)}</td><td><div class="t" style="white-space:normal;max-width:420px">${esc(b.caption)}</div><ul class="sub" style="margin:4px 0 0;padding-left:16px">${b.why.map(w=>`<li>${esc(w)}</li>`).join("")}</ul></td></tr>`).join("")}</table></div></div>`}
  async function poll(){try{const s=await api("/api/mining/status",{bg:true});V.querySelector("#tl").textContent=s.log.join("\n")||"Log appears here…";V.querySelector("#tl").scrollTop=1e9;
    V.querySelector("#ts").textContent=s.running?"Training…":s.error?"Failed: "+s.error:s.trained_at?"Last trained "+s.trained_at:"Not trained yet";V.querySelector("#tr").disabled=s.running;
    if(!s.running&&s.finished&&V.dataset.done!==s.finished){V.dataset.done=s.finished;body()}return s.running}catch(e){return false}}
  V.querySelector("#tr").onclick=async()=>{try{await api("/api/admin/mining/train",{method:"POST"});const t=setInterval(async()=>{if(!(await poll()))clearInterval(t)},2000);timers.push(t)}catch(e){toast(e.message,"bad")}};
  await poll();await body()}

/* ---------------- admins & security ---------------- */
async function renderAdmins(){const V=$("#view");const L=await api("/api/admin/admins");
  V.innerHTML=`<div class="grid eq"><div class="glass card"><h3>Administrators</h3><table><tr><th>Name</th><th>Email</th><th>Last sign-in</th><th></th></tr>${L.map(a=>`<tr><td>${esc(a.name)}</td><td>${esc(a.email)}</td><td>${ago(a.last_login)}</td><td>${a.must_change?'<span class="pill pending">must set password</span>':""}</td></tr>`).join("")}</table>
   <h3 style="margin-top:18px">Add an administrator</h3><p class="sub">They must choose their own password at first sign-in.</p>
   <form id="af"><label class="f">Name<input id="an" required maxlength="60"></label><label class="f">Email<input id="ae" type="email" required></label><label class="f">Temporary password<input id="ap" type="password" autocomplete="new-password" required></label><div class="meter" id="am"></div>
   <div class="err" id="aer"></div><button class="btn p">Create administrator</button></form></div>
  <div class="glass card"><h3>Change my password</h3><p class="sub">Other devices are signed out.</p>
   <form id="cf"><label class="f">Current password<input id="cp" type="password" autocomplete="current-password" required></label><label class="f">New password<input id="np" type="password" autocomplete="new-password" required></label><div class="meter" id="nm"></div>
   <label class="f">Repeat new password<input id="np2" type="password" autocomplete="new-password" required></label><div class="err" id="ce"></div><button class="btn p">Change password</button></form>
   <h3 style="margin-top:18px">How this portal is protected</h3>
   <div class="stat"><span>Sign-in</span><b>password + emailed 6-digit code</b></div><div class="stat"><span>Idle sign-out</span><b>30 minutes</b></div><div class="stat"><span>Session length</span><b>4 hours</b></div>
   <div class="stat"><span>Lock-out</span><b>5 wrong passwords → 10 minutes</b></div><div class="stat"><span>Separate from users</span><b>own cookie, own endpoints</b></div></div></div>`;
  meter(V.querySelector("#ap"),V.querySelector("#am"));meter(V.querySelector("#np"),V.querySelector("#nm"));
  V.querySelector("#af").onsubmit=async e=>{e.preventDefault();V.querySelector("#aer").textContent="";
    try{await api("/api/admin/admins",{method:"POST",body:{name:V.querySelector("#an").value,email:V.querySelector("#ae").value,password:V.querySelector("#ap").value}});toast("Administrator created","good");renderAdmins()}catch(x){V.querySelector("#aer").textContent=x.message}};
  V.querySelector("#cf").onsubmit=async e=>{e.preventDefault();V.querySelector("#ce").textContent="";
    if(V.querySelector("#np").value!==V.querySelector("#np2").value){V.querySelector("#ce").textContent="The two new passwords do not match.";return}
    try{await api("/api/admin/auth/password",{method:"POST",body:{current:V.querySelector("#cp").value,new:V.querySelector("#np").value}});toast("Password changed","good");renderAdmins()}catch(x){V.querySelector("#ce").textContent=x.message}}}

/* ---------------- start ---------------- */
(async()=>{try{enter(await api("/api/admin/auth/me"))}catch(e){showAuth()}})();



/* ---------------- regions & influencer directory (admin) ---------------- */
async function renderRegions(){const V=$("#view");const S=await api("/api/admin/directory/stats");
  V.innerHTML=`<div id="dirAdmin"></div><div id="regionMain" style="margin-top:14px"></div>`;const A=V.querySelector("#dirAdmin");
  const lu=S.last_upload;
  A.innerHTML=`<div class="grid eq"><div class="glass card"><h3>Influencer directory</h3><p class="sub">${n(S.total)} real public influencers loaded, each with the source and date of its follower count (see the source list below). The posts dataset has no region column, so regions come from this directory. Upload a CSV to add more.</p>
    <div class="row"><a class="btn sm" id="dtp">⬇ CSV template</a><label class="btn sm p" for="dfile">Upload CSV</label><input type="file" id="dfile" accept=".csv,text/csv" hidden>
    <label class="chk"><input type="checkbox" id="drep"> <span>Replace everything (remove current rows first)</span></label></div><div class="err" id="derr"></div>
    ${lu?`<p class="sub">Last upload: ${lu.accepted} accepted, ${lu.rejected} rejected.</p>${lu.rejected?`<div class="tbl" style="max-height:220px;overflow:auto"><table><tr><th>Line</th><th>Handle</th><th>Reason</th></tr>${lu.rejected_rows.map(r=>`<tr><td>${r.line}</td><td>${esc(r.handle)}</td><td>${esc(r.reason)}</td></tr>`).join("")}</table></div>`:""}`:""}
    <p class="sub">Required columns: handle, country, category, followers, avg_likes, avg_comments. Nothing is invented: rows you upload are used exactly as given, and marked with the source you write.</p></div>
   <div class="glass card"><h3>Coverage by country</h3><p class="sub">Countries with fewer than ${S.min_per_region} influencers are flagged: their statistics are thin.</p><div class="tbl" style="max-height:300px;overflow:auto"><table><tr><th>Country</th><th class="r">Influencers</th><th class="r">Avg followers</th><th>Data as of</th></tr>
    ${S.countries.map(c=>`<tr><td>${esc(c.country)} ${c.gap?'<span class="pill demo">thin</span>':""}</td><td class="r">${n(c.n)}</td><td class="r">${n(c.avg_followers)}</td><td>${esc(c.as_of||"")}</td></tr>`).join("")}</table></div></div></div>
   <div class="grid eq" style="margin-top:14px"><div class="glass card"><h3>Sources</h3>${bars(S.sources.map(s=>[s.source,s.n]))}</div><div class="glass card"><h3>Registered users by country</h3>${S.users_by_country.length?bars(S.users_by_country.map(s=>[s.country,s.n])):'<p class="sub">No users yet.</p>'}</div></div>`;
  A.querySelector("#dtp").onclick=async()=>{const r=await fetch("/api/admin/directory/template.csv",{credentials:"same-origin"});const b=await r.blob();const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="influencer_directory_template.csv";a.click()};
  A.querySelector("#dfile").onchange=async e=>{const f=e.target.files[0];if(!f)return;A.querySelector("#derr").textContent="";
    try{const r=await fetch("/api/admin/directory/upload?replace="+(A.querySelector("#drep").checked?"true":"false"),{method:"POST",headers:{"X-Requested-With":"fetch","Content-Type":"text/csv"},body:f,credentials:"same-origin"});
      const j=await r.json();if(!r.ok)throw new Error(j.detail||"Upload failed");toast(j.accepted+" accepted, "+j.rejected+" rejected","good");renderRegions()}catch(x){A.querySelector("#derr").textContent=x.message}};
  await regionPage(V.querySelector("#regionMain"),true)}


/* ---------------- recent admin sign-ins, public-mode badge, backup and restore ---------------- */
async function overviewPlus(){await renderOverview();const V=$("#view");let L;try{L=await api("/api/admin/logins")}catch(e){return}
  const card=document.createElement("div");card.className="glass card";card.style.marginTop="14px";
  card.innerHTML=`<div class="row" style="justify-content:space-between"><h3 style="margin:0">Last 20 administrator sign-ins</h3>${L.public?`<span class="pill active">Public mode ON${L.allowed_ips.length?" · admin limited to "+esc(L.allowed_ips.join(", ")):""}</span>`:'<span class="pill">Local mode</span>'}</div>
   <div class="tbl"><table><tr><th>When</th><th>Account</th><th>Result</th><th>Network</th><th>Device</th></tr>${L.rows.map(r=>`<tr><td>${when(r.ts)}</td><td>${esc(r.email||"")}</td><td>${r.event==="login_success"?'<span class="pill active">signed in</span>':'<span class="pill blocked">'+esc(r.event.replace("_"," "))+"</span>"}</td><td>${esc(r.ip||"")}</td><td>${esc(dev(r.ua||""))}</td></tr>`).join("")||'<tr><td colspan="5">No sign-ins yet.</td></tr>'}</table></div>`;
  V.appendChild(card);const b=$("#title");if(L.public&&b&&!document.querySelector(".pubbadge")){const x=document.createElement("span");x.className="pill active pubbadge";x.style.marginLeft="10px";x.textContent="Public mode ON";b.appendChild(x)}}
async function adminsPlus(){await renderAdmins();const V=$("#view");
  const card=document.createElement("div");card.className="glass card";card.style.marginTop="14px";
  card.innerHTML=`<h3>Backup and restore</h3><p class="sub">The backup holds users, sign-in devices, saved analyses and the influencer directory. It contains personal data and password hashes: keep the file private. The warehouse itself is rebuilt from the CSV files, so it is not part of this backup.</p>
   <div class="row"><a class="btn sm p" id="bkp" href="/api/admin/backup">⬇ Download backup</a><label class="btn sm d" for="rfile">Restore from backup file…</label><input type="file" id="rfile" accept=".db" hidden></div><div class="err" id="rerr"></div>`;
  V.appendChild(card);
  card.querySelector("#rfile").onchange=async e=>{const f=e.target.files[0];if(!f)return;
    const w=await ask("Restore from backup?","RESTORE","Type RESTORE to replace the current users and data with this backup. The current data is kept as a safety copy on the server.");if(w!=="RESTORE"){e.target.value="";return}
    try{const r=await fetch("/api/admin/restore?confirm=RESTORE",{method:"POST",headers:{"X-Requested-With":"fetch","Content-Type":"application/octet-stream"},body:f,credentials:"same-origin"});const j=await r.json();if(!r.ok)throw new Error(j.detail||"Restore failed");toast("Restored. Please sign in again.","good");setTimeout(()=>location.reload(),1200)}catch(x){card.querySelector("#rerr").textContent=x.message}}}
