"use strict";
const PAGE_JS_BUILD="5.7";
/* USER PORTAL: sign in / sign up / verify / forgot / reset, then the pages for ordinary users */
CFG={kind:"user",base:"/api/auth",pages:[
 {id:"dashboard",t:"Dashboard",i:"▣",g:"Explore",r:renderDashboard},
 {id:"cube",t:"3D OLAP Cube",i:"◆",g:"Explore",r:()=>frame("cube","/static/modules/cube.html")},
 {id:"schema",t:"Star & Snowflake",i:"❄",g:"Explore",r:()=>frame("schema","/static/modules/schema.html?embed=1")},
 {id:"pipeline",t:"ETL & Dataset",i:"⇄",g:"Data",r:renderPipeline},
 {id:"mining",t:"Data Mining",i:"✦",g:"Mining",r:renderMining},
 {id:"caption",t:"Caption Checker",i:"✎",g:"Mining",r:renderCaption},
 {id:"analyser",t:"My Account Analyser",i:"◎",g:"Insights",r:renderAnalyser},
 {id:"influencer",t:"Influencer Analyser",i:"★",g:"Insights",r:renderInfluencer},
 {id:"region",t:"Region Influencers",i:"◍",g:"Insights",r:()=>regionPage($("#view"))},
 {id:"history",t:"My History",i:"◷",g:"Insights",r:renderHistory},
 {id:"reports",t:"Reports",i:"▤",g:"Insights",r:()=>reportsPage($("#view"))},
 {id:"creator",t:"Post Analyzer",i:"✚",g:"Creator Income",r:()=>creatorPage($("#view"))},
 {id:"creator_plan",t:"Income Planner",i:"₹",g:"Creator Income",r:()=>planPage($("#view"))},
 {id:"creator_hist",t:"My Progress",i:"↗",g:"Creator Income",r:()=>histPage($("#view"))},
 {id:"account",t:"Profile & Security",i:"☺",g:"Account",r:renderAccount}]};
const COUNTRIES=["India","United States","United Kingdom","Canada","Australia","New Zealand","Singapore","United Arab Emirates","Saudi Arabia","Qatar","Kuwait","Oman","Bahrain","Pakistan","Bangladesh","Sri Lanka","Nepal","Bhutan","Maldives","Malaysia","Indonesia","Thailand","Vietnam","Philippines","Japan","South Korea","China","Hong Kong","Taiwan","Germany","France","Italy","Spain","Portugal","Netherlands","Belgium","Switzerland","Austria","Sweden","Norway","Denmark","Finland","Ireland","Poland","Turkey","Russia","Ukraine","Greece","Israel","Egypt","South Africa","Nigeria","Kenya","Ghana","Ethiopia","Brazil","Argentina","Mexico","Colombia","Chile","Peru","Other"];
const TYPES=[["creator","Content creator"],["influencer","Influencer"],["business","Business owner"],["brand_manager","Brand or marketing manager"],["social_media_manager","Social media manager"],["agency","Agency or consultant"],["photographer","Photographer / videographer"],["celebrity","Celebrity or public figure"],["athlete","Athlete / sports person"],["musician","Musician / artist"],["journalist","Journalist / blogger"],["student","Student"],["researcher","Researcher / academic"],["teacher","Teacher / trainer"],["developer","Developer / engineer"],["analyst","Data analyst / scientist"],["freelancer","Freelancer"],["ngo","NGO / community group"],["other","Other"]];
const INTERESTS=["Food","Travel","Fitness","Fashion","Beauty","Music","Gaming","Technology","Business","Education","Sports","Cricket","Football","Movies","Art","Photography","Comedy","Family","News","Health"];
$("#upCountry").innerHTML='<option value="">Choose…</option>'+COUNTRIES.map(c=>`<option>${c}</option>`).join("");
$("#upType").innerHTML=TYPES.map(t=>`<option value="${t[0]}">${t[1]}</option>`).join("");
meter($("#upPw"),$("#upMeter"));
$("#upPick").innerHTML=INTERESTS.map(i=>`<button type="button" data-i="${i}">${i}</button>`).join("");
$("#upPick").onclick=e=>{const b=e.target.closest("button");if(!b)return;const cur=$("#upInt").value.split(",").map(x=>x.trim()).filter(Boolean),k=b.dataset.i,at=cur.findIndex(x=>x.toLowerCase()===k.toLowerCase());
  if(at>=0)cur.splice(at,1);else cur.push(k);$("#upInt").value=cur.join(", ");b.classList.toggle("on",at<0)};meter($("#rsPw"),$("#rsMeter"));

/* ---------------- auth screens ---------------- */
const FORMS={in:"#fIn",up:"#fUp",for:"#fFor",rs:"#fRes"};
function tab(w){Object.entries(FORMS).forEach(([k,s])=>$(s).classList.toggle("hidden",k!==w));
  $("#tabIn").classList.toggle("on",w==="in"||w==="for"||w==="rs"||w==="ver");$("#tabUp").classList.toggle("on",w==="up");
  document.querySelectorAll(".err").forEach(e=>e.textContent="");if(w==="up")upStep(1)}
function upStep(k){$("#upS1").classList.toggle("hidden",k!==1);$("#upS2").classList.toggle("hidden",k!==2);$("#st2").classList.toggle("on",k===2);$("#upErr").textContent=""}
function upNext(){const e=$("#upErr");e.textContent="";
  if($("#upName").value.trim().length<2){e.textContent="Please enter your full name.";$("#upName").focus();return false}
  if(!$("#upEmail").checkValidity()||!$("#upEmail").value){e.textContent="Please enter a valid email address.";$("#upEmail").focus();return false}
  if($("#upPw").value.length<8){e.textContent="The password needs at least 8 characters.";$("#upPw").focus();return false}
  if($("#upPw").value!==$("#upPw2").value){e.textContent="The two passwords do not match.";$("#upPw2").focus();return false}
  upStep(2);return true}
$("#upNext").onclick=upNext;$("#upBack").onclick=()=>upStep(1);
function showAuth(msg){$("#app").classList.add("hidden");$("#auth").classList.remove("hidden");tab("in");$("#inErr").textContent=msg||""}
$("#tabIn").onclick=()=>tab("in");$("#tabUp").onclick=()=>tab("up");
document.querySelectorAll("[data-go]").forEach(a=>a.onclick=e=>{e.preventDefault();tab(a.dataset.go)});
let pend="",rsTicket="";
/* the pop-up: kind = signup | login | reset */
function showOtp(info,kind){
  const reset=kind==="reset";pend=info.email;
  otpPopup({title:reset?"Enter your reset code":kind==="login"?"Confirm it is you":"Verify your email",info,
    verify:(code,i)=>api(reset?"/api/auth/reset/verify":"/api/auth/verify",{method:"POST",body:{email:i.email,code,ticket:i.ticket}}),
    resend:i=>reset?api("/api/auth/forgot",{method:"POST",body:{email:i.email}}):api("/api/auth/resend",{method:"POST",body:{email:i.email,ticket:i.ticket}}),
    onDone:(r,i)=>{if(reset){rsTicket=i.ticket;$("#rsEmail").textContent=pend;tab("rs")}else enter(r.user)},
    onCancel:()=>{tab(reset?"for":kind==="signup"?"up":"in")}});
}
$("#fIn").onsubmit=async e=>{e.preventDefault();$("#inErr").textContent="";
  try{const r=await busy($("#inBtn"),()=>api("/api/auth/login",{method:"POST",body:{email:$("#inEmail").value,password:$("#inPw").value}}));$("#inPw").value="";
    if(r.needs_otp){showOtp(r,r.needs_verification?"signup":"login");return}enter(r.user)}
  catch(x){$("#inErr").textContent=x.message}};
$("#fUp").onsubmit=async e=>{e.preventDefault();$("#upErr").textContent="";
  if(!$("#upS1").classList.contains("hidden")){upNext();return}
  if(!$("#upCountry").value){$("#upErr").textContent="Please choose your country.";$("#upCountry").focus();return}
  if(!$("#upConsent").checked){$("#upErr").textContent="Please tick the box to agree to the terms.";return}
  try{showOtp(await busy($("#upBtn"),()=>api("/api/auth/signup",{method:"POST",body:{name:$("#upName").value,email:$("#upEmail").value,password:$("#upPw").value,phone:$("#upPhone").value,country:$("#upCountry").value,user_type:$("#upType").value,handle:$("#upHandle").value,interests:$("#upInt").value,consent:$("#upConsent").checked}})),"signup")}catch(x){$("#upErr").textContent=x.message;if(/password|email|name/i.test(x.message))upStep(1),$("#upErr").textContent=x.message}};
$("#fFor").onsubmit=async e=>{e.preventDefault();$("#forErr").textContent="";
  try{const r=await busy($("#forBtn"),()=>api("/api/auth/forgot",{method:"POST",body:{email:$("#forEmail").value}}));showOtp(r,"reset")}catch(x){$("#forErr").textContent=x.message}};
$("#fRes").onsubmit=async e=>{e.preventDefault();$("#rsErr").textContent="";
  if($("#rsPw").value!==$("#rsPw2").value){$("#rsErr").textContent="The two passwords do not match.";return}
  try{await busy($("#rsBtn"),()=>api("/api/auth/reset",{method:"POST",body:{email:pend,ticket:rsTicket,password:$("#rsPw").value}}));
    $("#rsPw").value=$("#rsPw2").value="";tab("in");$("#inEmail").value=pend;toast("Password changed. Please sign in.","good")}catch(x){$("#rsErr").textContent=x.message}};

/* ---------------- user pages ---------------- */
/* ---------------- shared pieces for the two analysers ---------------- */
const HOURS=[...Array(24).keys()].map(h=>`<option value="${h}">${String(h).padStart(2,"0")}:00</option>`).join("");
const WDAYS=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"].map((d,i)=>`<option value="${i}">${d}</option>`).join("");
const catLabel=c=>c.replace(/_/g," ");
function predCard(P,fee,feeB,persona){if(!P)return `<div class="glass card"><h3>Engagement forecast</h3><p class="sub">The mining models are not trained yet. An administrator can train them from the Mining Lab.</p></div>`;
  const lo=P.likes_range[0],hi=P.likes_range[1];
  return `<div class="glass card"><h3>Your next post <span class="badge">predicted</span></h3>
   <div class="row" style="gap:28px"><div><div class="fee">${n(P.next_likes)}</div><span class="sub">likes (${n(lo)} to ${n(hi)})</span></div><div><div class="fee">${n(P.next_comments)}</div><span class="sub">comments</span></div></div>
   <p class="sub">${esc(P.interval_note)} ${P.peers?`Accounts of your size and category typically get about ${n(P.peers.likes)} likes and ${n(P.peers.comments)} comments.`:"Your audience is larger than almost any account in the data, so no peer figure is shown."}
   ${P.post_effect_pct?` This post's settings are expected to give ${P.post_effect_pct>0?"+":""}${P.post_effect_pct}% versus a typical post.`:""}</p>
   ${P.hide_levers?'<p class="sub">Tips on hashtags, caption length and posting time are not shown for audiences this large, because the model learned them from much smaller accounts.</p>':P.changes.length?`<h3 style="margin-top:12px">Change these to get more</h3>${P.changes.map(c=>`<div class="tip"><b>${esc(c.text)}</b>about +${c.gain_pct}% likes</div>`).join("")}<div class="tip" style="border-color:var(--good)"><b>All ${P.changes.length} together</b>about +${P.combined_gain_pct}% → roughly ${n(P.improved_likes)} likes</div>`:'<p class="sub">Your planned post is already close to the best settings the model found.</p>'}</div>`}
function feeCard(f,fb,title){const lo=f.usd.low,hi=f.usd.high,mid=f.usd.mid,pct=(mid-lo)/(hi-lo)*100;
  return `<div class="glass card"><h3>${title||"Estimated fee per sponsored post"} <span class="badge">estimate</span></h3>
   <div class="fee">${usd(mid)} <span class="sub" style="-webkit-text-fill-color:var(--muted)">≈ ${inr(f.inr.mid)}</span></div>
   <div class="rangebar"><i style="left:0;right:0"></i><b style="left:${pct}%"></b></div><div class="row" style="justify-content:space-between"><span class="sub">${usd(lo)} · ${inr(f.inr.low)}</span><span class="sub">${usd(hi)} · ${inr(f.inr.high)}</span></div>
   <p class="sub" style="margin-top:8px">Market tier: <b>${esc(f.market_tier)}</b>. Price curve ${usd(f.base_usd)} × engagement factor ${f.engagement_factor} × category factor ${f.category_factor}. Exchange rate used: ₹${f.inr_per_usd} per US$.</p>
   <div class="stat"><span>${f.posts_per_month} sponsored post${f.posts_per_month===1?"":"s"} a month</span><b>${usd(f.monthly_usd)} · ${inr(f.monthly_inr)}</b></div>
   <div class="stat"><span>Per year</span><b>${inr(f.yearly_inr)}</b></div>
   ${fb&&fb.usd.mid>f.usd.mid?`<div class="tip" style="border-color:var(--good);margin-top:8px"><b>If you apply the suggested changes</b>about ${usd(fb.usd.mid)} (${inr(fb.inr.mid)}) per post</div>`:""}
   ${f.extrapolated?'<div class="warn">This audience is larger than any account on the public rich lists, so the figure is extrapolated and much less certain.</div>':f.celebrity_reference?'<div class="warn">Celebrity range: priced from the Hopper HQ Instagram Rich List (agency-rate estimates, about $5 to $6 per 1,000 followers). Real deals vary a lot, so treat it as a ballpark.</div>':""}</div>`}
function personaCard(p){if(!p)return "";return `<div class="glass card"><h3>Your persona: ${esc(p.name)}</h3><p class="sub">${n(p.accounts)} accounts in the data (${p.share_pct}%) behave like this one.</p>
  <div class="stat"><span>Typical hashtags</span><b>${p.hashtags} per post</b></div><div class="stat"><span>Typical caption</span><b>${p.caption_len} characters</b></div>
  <div class="stat"><span>Best hour for them</span><b>${p.best_hour==null?"n/a":String(p.best_hour).padStart(2,"0")+":00"}</b></div>
  <div class="tip" style="margin-top:8px"><b>What the best accounts in this persona do</b>About ${p.top_performers.hashtags} hashtags and ${p.top_performers.caption_len}-character captions.</div></div>`}

/* ---------------- account analyser ---------------- */
async function renderAnalyser(){const V=$("#view");
  const cats=await api("/api/meta/categories");
  V.innerHTML=`<div class="grid two"><div class="glass card"><h3>Your account</h3><p class="sub">Compared with the warehouse and saved to your history (My History). Administrators can see submissions to improve the system. Slider what-ifs are not saved.</p>
  <form id="af"><label class="f">Handle<input id="h" value="@myaccount" maxlength="40" required></label>
  <div class="row"><label class="f" style="flex:1">Followers<input id="fo" type="number" min="0" value="5000" required></label><label class="f" style="flex:1">Account type<select id="ty"><option value="personal">Personal</option><option value="business">Business</option></select></label></div>
  <label class="f">Main category<select id="ca">${cats.map(c=>`<option value="${esc(c)}">${esc(catLabel(c))}</option>`).join("")}</select></label>
  <div class="row"><label class="f" style="flex:1">Average likes per post<input id="al" type="number" min="0" step="any" value="80" required></label><label class="f" style="flex:1">Average comments per post<input id="ac" type="number" min="0" step="any" value="3" required></label></div>
  <div class="slide"><label><span>Hashtags you usually use</span><b id="hv">8</b></label><input id="hs" type="range" min="0" max="30" value="8"></div>
  <div class="slide"><label><span>Posts per week</span><b id="pv">3</b></label><input id="pw" type="range" min="0" max="21" step="1" value="3"></div>
  <label class="f">Sponsored posts per month (for the income estimate)<input id="sp" type="number" min="0" max="60" value="4"></label>
  <details class="more" open><summary>Plan your next post (the prediction uses this)</summary>
   <div class="slide" style="margin-top:8px"><label><span>Hashtags in the next post</span><b id="phv">8</b></label><input id="phs" type="range" min="0" max="30" value="8"></div>
   <div class="row"><label class="f" style="flex:1">Caption length (characters)<input id="cl" type="number" min="0" max="2200" placeholder="typical"></label><label class="f" style="flex:1">@mentions<input id="mn" type="number" min="0" max="20" value="0"></label></div>
   <div class="row"><label class="f" style="flex:1">Hour<select id="hr"><option value="">typical</option>${HOURS}</select></label><label class="f" style="flex:1">Day<select id="wd"><option value="">typical</option>${WDAYS}</select></label></div></details>
  <details class="more"><summary>Optional details</summary><div class="row" style="margin-top:8px"><label class="f" style="flex:1">Accounts you follow<input id="fg" type="number" min="0" placeholder="typical for your size"></label><label class="f" style="flex:1">Posts published so far<input id="np" type="number" min="0" placeholder="typical for your size"></label></div></details>
  <div class="err" id="ae"></div><button class="btn p" style="width:100%" id="ab">Analyse my account</button></form></div>
  <div id="res"><div class="glass card"><h3>Results</h3><p class="sub">Fill in the form and press Analyse. The forecast, your persona and the fee estimate come from models trained on 605,665 posts. Move the "next post" settings afterwards to see a what-if.</p></div></div></div>`;
  let ran=false,tm,touched=false;const q=s=>V.querySelector(s);
  const num=s=>q(s).value===""?null:+q(s).value;
  async function go(save=true){q("#ae").textContent="";
    try{const r=await api("/api/analyse",{method:"POST",body:{handle:q("#h").value,followers:+q("#fo").value,category:q("#ca").value,account_type:q("#ty").value,avg_likes:+q("#al").value,avg_comments:+q("#ac").value,hashtags_per_post:+q("#hs").value,posts_per_week:+q("#pw").value,
      sponsored_per_month:+q("#sp").value||0,planned_hashtags:touched?+q("#phs").value:null,mentions:+q("#mn").value||0,caption_len:num("#cl"),hour:num("#hr"),weekday:num("#wd"),following:num("#fg"),num_posts:num("#np"),save}});ran=true;if(save)toast("Saved to your history","good");show(r)}
    catch(e){q("#ae").textContent=e.message}}
  function show(r){const col=r.score>=70?"var(--good)":r.score>=45?"var(--warn)":"var(--bad)";
    q("#res").innerHTML=`<div class="glass card"><div class="row" style="gap:20px"><div class="ring" style="--v:${r.score}"><div><span><b style="color:${col}">${r.score}</b><span class="sub">health score</span></span></div></div>
    <div style="flex:1;min-width:200px"><h3>${esc(r.handle)} <span class="badge">${esc(r.tier)}</span></h3><p class="sub">Compared with ${esc(r.level)}. Benchmark: ${r.benchmark.likes} likes and ${r.benchmark.comments} comments per post.</p>
    <p class="sub" style="color:${r.low_confidence?"var(--warn)":"var(--muted)"}">${r.low_confidence?"⚠ Small sample: ":"Based on "}${n(r.sample)} similar posts.</p></div></div></div>
    <div style="margin-top:14px">${predCard(r.prediction)}</div><div style="margin-top:14px">${feeCard(r.fee,r.fee_improved)}</div><div style="margin-top:14px">${personaCard(r.persona)}</div>
    <div class="glass card" style="margin-top:14px"><h3>Rule-based suggestions</h3>${r.suggestions.length?r.suggestions.map(t=>`<div class="tip"><b>${esc(t.title)}</b>${esc(t.text)}<br><small>${esc(t.evidence)}</small></div>`).join(""):'<p class="sub">Your account already matches the best pattern in the data.</p>'}<p class="sub">${esc(r.disclaimer)}</p></div>`}
  q("#af").onsubmit=e=>{e.preventDefault();busy(q("#ab"),()=>go(true))};
  const again=()=>{if(ran){clearTimeout(tm);tm=setTimeout(()=>go(false),300)}};
  q("#hs").oninput=()=>{q("#hv").textContent=q("#hs").value;if(!touched){q("#phs").value=q("#hs").value;q("#phv").textContent=q("#hs").value}again()};
  q("#pw").oninput=()=>{q("#pv").textContent=q("#pw").value;again()};
  q("#phs").oninput=()=>{touched=true;q("#phv").textContent=q("#phs").value;again()};
  ["#cl","#mn","#hr","#wd","#sp"].forEach(s=>q(s).onchange=again)}

/* ---------------- influencer / celebrity analyser ---------------- */
/* quick-pick public figures: followers are approximate (Wikipedia list, Sept 2026; tennis from a May 2023 article) - always editable */
const PRESETS=[["Cristiano Ronaldo","athlete","sports",679e6],["Lionel Messi","athlete","sports",517e6],["Virat Kohli","athlete","sports",271e6],["Neymar Jr","athlete","sports",241e6],["LeBron James","athlete","sports",153e6],
["Rafael Nadal (tennis)","athlete","sports",18e6],["Novak Djokovic (tennis)","athlete","sports",13e6],["Roger Federer (tennis)","athlete","sports",12e6],
["Selena Gomez","celebrity","music",403e6],["Dwayne Johnson","celebrity","film_tv_&_video",381e6],["Kylie Jenner","celebrity","fashion_&_style",380e6],["Beyoncé","celebrity","music",299e6],["Taylor Swift","celebrity","music",272e6]];
async function renderInfluencer(){const V=$("#view");const cats=await api("/api/meta/categories");const q=s=>V.querySelector(s);
  V.innerHTML=`<div class="grid two"><div class="glass card"><h3>Analyse any public account</h3><p class="sub">Type in the public numbers you can see on the account (followers, and the likes and comments on its recent posts). This tool never contacts Instagram. It forecasts the account's next post and estimates what a brand would pay for one sponsored post.</p>
  <label class="f">Quick pick (fills the form, then edit anything)<select id="ipre"><option value="">Choose a famous account or type your own below</option>${PRESETS.map((p,i)=>`<option value="${i}">${esc(p[0])} - ${n(p[3])} followers</option>`).join("")}</select></label>
  <form id="if"><div class="row"><label class="f" style="flex:2">Name or handle<input id="in" required maxlength="60" placeholder="e.g. @someone"></label><label class="f" style="flex:1">This is a<select id="ik"><option value="celebrity">Celebrity</option><option value="athlete">Sports person</option><option value="influencer" selected>Influencer</option><option value="brand">Brand</option><option value="other">Other</option></select></label></div>
  <div class="row"><label class="f" style="flex:1">Followers<input id="if2" type="number" min="100" required placeholder="e.g. 12500000"></label><label class="f" style="flex:1">Category<select id="ic">${cats.map(c=>`<option value="${esc(c)}">${esc(catLabel(c))}</option>`).join("")}</select></label></div>
  <div class="row"><label class="f" style="flex:1">Average likes per post (optional)<input id="il" type="number" min="0" step="any" placeholder="leave empty if unknown"></label><label class="f" style="flex:1">Average comments per post (optional)<input id="icm" type="number" min="0" step="any" placeholder="leave empty if unknown"></label></div>
  <label class="chk"><input type="checkbox" id="ib"> <span>It is a business / creator account</span></label>
  <details class="more" open><summary>The post you want priced (optional)</summary>
   <label class="f" style="margin-top:8px">Caption (hashtags and @mentions are counted)<textarea id="icp" rows="3" maxlength="2200" placeholder="Paste the caption of the post, or leave empty to use a typical post"></textarea></label>
   <div class="row"><label class="f" style="flex:1">Hour<select id="ih"><option value="">typical</option>${HOURS}</select></label><label class="f" style="flex:1">Day<select id="iw"><option value="">typical</option>${WDAYS}</select></label></div>
   <div class="row"><label class="f" style="flex:1">If already published: its likes<input id="ipl" type="number" min="0" step="any"></label><label class="f" style="flex:1">its comments<input id="ipc" type="number" min="0" step="any"></label></div></details>
  <label class="f">Sponsored posts per month (for monthly and yearly figures)<input id="isp" type="number" min="0" max="60" value="4"></label>
  <div class="err" id="ie"></div><button class="btn p" style="width:100%" id="ib2">Analyse and estimate the fee</button></form></div>
  <div id="ires"><div class="glass card"><h3>Results</h3><p class="sub">You will get: the account's engagement compared with similar audiences, a forecast for its next post, which persona it matches, and the estimated fee per sponsored post (in US dollars and rupees).</p></div></div></div>`;
  const num=s=>q(s).value===""?null:+q(s).value;
  q("#ipre").onchange=e=>{const p=PRESETS[e.target.value];if(!p)return;q("#in").value=p[0].replace(/ \(.*\)/,"");q("#ik").value=p[1];q("#if2").value=p[3];q("#ic").value=p[2];q("#il").value="";q("#icm").value="";q("#ib").checked=true};
  q("#if").onsubmit=e=>{e.preventDefault();busy(q("#ib2"),async()=>{q("#ie").textContent="";
    try{const r=await api("/api/influencer/analyse",{method:"POST",body:{name:q("#in").value,kind:q("#ik").value,followers:+q("#if2").value,category:q("#ic").value,business:q("#ib").checked,avg_likes:num("#il"),avg_comments:num("#icm"),caption:q("#icp").value,hour:num("#ih"),weekday:num("#iw"),post_likes:num("#ipl"),post_comments:num("#ipc"),sponsored_per_month:+q("#isp").value||0}});toast("Saved to your lookups","good");show(r)}
    catch(x){q("#ie").textContent=x.message}})};
  function show(r){const colr=/above/.test(r.engagement_vs_benchmark)?"var(--good)":/below/.test(r.engagement_vs_benchmark)?"var(--bad)":"var(--warn)";
    q("#ires").innerHTML=`<div class="glass card"><h3>${esc(r.name)} <span class="badge">${esc(r.kind)}</span> <span class="badge">${esc(r.tier)}</span></h3>
    <div class="grid" style="grid-template-columns:1fr 1fr;margin-top:8px"><div><span class="sub">Engagement rate</span><div style="font-size:24px;font-weight:700">${r.engagement_pct}%</div></div><div><span class="sub">Typical for this audience size</span><div style="font-size:24px;font-weight:700">${r.benchmark_pct}%</div></div></div>
    <p style="color:${colr};margin:6px 0 0"><b>Engagement is ${esc(r.engagement_vs_benchmark)} what is typical for accounts of this size.</b></p>
    ${r.engagement_assumed?`<div class="warn">No likes or comments were entered, so the typical engagement for this audience size was assumed (${n(r.avg_likes_used)} likes, ${n(r.avg_comments_used)} comments per post). Type the real averages from the profile for a sharper estimate.</div>`:""}
    ${r.model_in_range?"":'<div class="warn">This audience is larger than almost every account in the data, so forecasts rely mostly on the numbers you typed in; the model only supplies the effect of the post settings.</div>'}</div>
    <div style="margin-top:14px">${feeCard(r.fee_next,r.model_in_range?r.fee_if_improved:null,"Estimated fee for the next sponsored post")}</div>
    ${r.this_post?`<div class="glass card" style="margin-top:14px"><h3>The published post you entered</h3><p class="sub">Its engagement was ${r.this_post.engagement_pct}% of followers, ${r.this_post.vs_average_pct>=0?"+":""}${r.this_post.vs_average_pct}% versus this account's average.</p><div class="fee">${usd(r.this_post.fee.usd.mid)} <span class="sub" style="-webkit-text-fill-color:var(--muted)">≈ ${inr(r.this_post.fee.inr.mid)}</span></div><p class="sub">Range ${usd(r.this_post.fee.usd.low)} to ${usd(r.this_post.fee.usd.high)} if a brand had paid for exactly this post's performance.</p></div>`:""}
    <div style="margin-top:14px">${predCard(r.model_in_range?r.prediction:{...r.prediction,hide_levers:true})}</div>
    ${r.caption?`<div class="glass card" style="margin-top:14px"><h3>Caption wording score: ${r.caption.score} / 100</h3><p class="sub">Percentile among captions in the data (weak signal, see Data Mining).</p>${r.caption.helped.length?`<div class="chips">${r.caption.helped.map(w=>`<span class="chip up">${esc(w.word)}</span>`).join("")}</div>`:""}${r.caption.hurt.length?`<div class="chips">${r.caption.hurt.map(w=>`<span class="chip dn">${esc(w.word)}</span>`).join("")}</div>`:""}</div>`:""}
    <div style="margin-top:14px">${personaCard(r.persona)}</div>
    <div class="glass card" style="margin-top:14px"><p class="sub">${esc(r.disclaimer)}</p></div>`}}

/* ---------------- caption checker ---------------- */
async function renderCaption(){const V=$("#view");const q=s=>V.querySelector(s);
  V.innerHTML=`<div class="grid eq"><div class="glass card"><h3>Caption checker</h3><p class="sub">Paste a draft caption. The text-mining model compares its wording with posts that beat, and posts that fell short of, what the engagement model expected.</p>
  <form id="cf2"><label class="f">Draft caption<textarea id="ct" rows="8" maxlength="2200" required minlength="3"></textarea></label><div class="err" id="ce2"></div><button class="btn p" id="cb">Check caption</button></form></div>
  <div id="cres"><div class="glass card"><h3>Result</h3><p class="sub">The score is a percentile: 80 means the wording looks more like over-performing captions than 80% of captions in the data. Wording is a weak signal, so treat it as a hint.</p></div></div></div>`;
  q("#cf2").onsubmit=e=>{e.preventDefault();busy(q("#cb"),async()=>{q("#ce2").textContent="";
    try{const r=await api("/api/caption/check",{method:"POST",body:{caption:q("#ct").value}});const col=r.score>=65?"var(--good)":r.score>=35?"var(--warn)":"var(--bad)";
      q("#cres").innerHTML=`<div class="glass card"><div class="row" style="gap:20px"><div class="ring" style="--v:${r.score}"><div><span><b style="color:${col}">${r.score}</b><span class="sub">of 100</span></span></div></div>
      <div style="flex:1;min-width:180px"><p class="sub">${r.words} words · ${r.emoji} emoji · ${r.question?"asks a question":"no question"}</p><p class="sub">Chance of beating the model's expectation: ${r.probability_pct}%</p></div></div>
      ${r.helped.length?`<h3 style="margin-top:12px">Wording that helps</h3><div class="chips">${r.helped.map(w=>`<span class="chip up">${esc(w.word)}<small>+${w.weight}</small></span>`).join("")}</div>`:""}
      ${r.hurt.length?`<h3>Wording that hurts</h3><div class="chips">${r.hurt.map(w=>`<span class="chip dn">${esc(w.word)}<small>${w.weight}</small></span>`).join("")}</div>`:""}
      ${r.tips.map(t=>`<div class="tip">${esc(t)}</div>`).join("")}</div>`}catch(x){q("#ce2").textContent=x.message}})}}

/* ---------------- data mining report ---------------- */
async function renderMining(){const V=$("#view");const R=await api("/api/mining/report");V.innerHTML=miningBody(R)}

/* ---------------- my history ---------------- */
async function renderHistory(){const V=$("#view");const H=await api("/api/account/history");
  if(!H.length){V.innerHTML='<div class="glass card"><h3>No analyses yet</h3><p class="sub">Run the Account Analyser and each result is saved here, so you can see your progress over time.</p><a class="btn p" href="#analyser">Open the Account Analyser</a></div>';return}
  const sc=H.map(h=>h.score).reverse(),first=sc[0],last=sc[sc.length-1];
  V.innerHTML=`<div class="grid kpis"><div class="glass card kpi"><span class="sub">Analyses saved</span><b>${H.length}</b></div>
   <div class="glass card kpi"><span class="sub">Latest score</span><b>${last}</b></div>
   <div class="glass card kpi"><span class="sub">Change since first</span><b>${last-first>0?"+":""}${last-first}</b></div>
   <div class="glass card kpi"><span class="sub">Latest monthly estimate</span><b>${inr(H[0].income_monthly)}</b><span class="sub">illustrative</span></div></div>
  <div class="glass card" style="margin-top:14px"><h3>Health score over time</h3><p class="sub">Oldest to newest</p>${cols(H.slice().reverse().map((h,i)=>[String(i+1),h.score]),"var(--a3)")}</div>
  <div class="glass card" style="margin-top:14px"><h3>Saved analyses</h3><div class="wrap"><table><tr><th>Date</th><th>Handle</th><th class=n>Followers</th><th>Tier</th><th>Category</th><th class=n>Score</th><th class=n>Est. per post</th><th></th></tr>
  ${H.map(h=>`<tr><td>${when(h.ts)}</td><td>${esc(h.handle)}</td><td class=n>${n(h.followers)}</td><td>${esc(h.tier)}</td><td>${esc(h.category.replace(/_/g," "))}</td><td class=n>${h.score}</td><td class=n>${inr(h.income_per_post)}</td><td><button class="btn sm d" data-del="${h.id}">Delete</button></td></tr>`).join("")}</table></div></div>`;
  V.onclick=async e=>{const b=e.target.closest("[data-del]");if(!b)return;try{await api("/api/account/history/"+b.dataset.del,{method:"DELETE"});toast("Deleted","good");renderHistory()}catch(x){toast(x.message,"bad")}}}

/* ---------------- profile & security ---------------- */
function setAvatar(v){document.querySelectorAll("#avImg,#meAv").forEach(i=>{i.src="/api/account/avatar?v="+encodeURIComponent(v);i.hidden=false})}
async function renderAccount(){const V=$("#view");const [P,S,D]=await Promise.all([api("/api/account/profile"),api("/api/account/sessions"),api("/api/account/devices")]);
  V.innerHTML=`<div class="grid eq"><div class="glass card"><h3>Your profile</h3><p class="sub">Member since ${when(P.created)} · ${n(P.login_count)} sign-ins · last ${ago(P.last_login)}</p>
   <div class="avrow"><img id="avImg" class="av big" alt="" ${P.avatar?`src="/api/account/avatar?v=${encodeURIComponent(P.avatar)}"`:"hidden"}><div><label class="btn sm" for="avFile">Upload profile picture</label><input id="avFile" type="file" accept="image/png,image/jpeg,image/webp" hidden><div class="sub">PNG, JPG or WebP, up to 1 MB. Stored on the server, so it shows on every device you sign in from.</div><div class="err" id="ae"></div></div></div>
   <form id="pf"><label class="f">Email (cannot be changed)<input value="${esc(P.email)}" disabled></label>
   <label class="f">Full name<input id="pn" value="${esc(P.name)}" required maxlength="60"></label>
   <div class="row"><label class="f" style="flex:1">Phone (optional)<input id="pp" value="${esc(P.phone||"")}" placeholder="+919876543210"></label>
   <label class="f" style="flex:1">Country<select id="pc">${COUNTRIES.map(c=>`<option${c===P.country?" selected":""}>${c}</option>`).join("")}</select></label></div>
   <div class="row"><label class="f" style="flex:1">I am a<select id="pt">${TYPES.map(t=>`<option value="${t[0]}"${t[0]===P.user_type?" selected":""}>${t[1]}</option>`).join("")}</select></label>
   <label class="f" style="flex:1">Instagram handle<input id="ph" value="${esc(P.handle||"")}" placeholder="@yourhandle"></label></div>
   <label class="f">Interests (optional)<input id="pi2" value="${esc(P.interests||"")}" maxlength="120" placeholder="food, travel, fitness"></label>
   <div class="err" id="pe"></div><button class="btn p">Save profile</button></form></div>
  <div class="glass card"><h3>Change password</h3><p class="sub">Changing it signs out every other device.</p>
   <form id="cf"><label class="f">Current password<input id="cp" type="password" autocomplete="current-password" required></label>
   <label class="f">New password<input id="np" type="password" autocomplete="new-password" required></label><div class="meter" id="nm"></div>
   <label class="f">Repeat new password<input id="np2" type="password" autocomplete="new-password" required></label>
   <div class="err" id="ce"></div><button class="btn p">Change password</button></form></div></div>
  <div class="grid eq" style="margin-top:14px"><div class="glass card"><h3>Signed-in devices (${S.length})</h3><p class="sub">If you do not recognise one, change your password.</p>
   <table><tr><th>Device</th><th>Network</th><th>Last active</th></tr>${S.map(s=>`<tr><td>${esc(dev(s.ua))}${s.current?' <span class="pill active">this device</span>':""}</td><td>${esc(s.ip)}</td><td>${ago(s.last_seen)}</td></tr>`).join("")}</table>
   <button class="btn sm d" id="ro" style="margin-top:10px"${S.length<2?" disabled":""}>Sign out all other devices</button></div>
  <div class="glass card"><h3>Trusted devices (${D.length})</h3><p class="sub">Browsers that were verified with a code. Sign-in from any other browser asks for a new code first. Remove one you no longer use.</p>
   <div class="tbl"><table><tr><th>Device</th><th>Network</th><th>Last used</th><th></th></tr>${D.map(d=>`<tr><td>${esc(d.label||"Browser")}${d.current?' <span class="pill active">this device</span>':""}</td><td>${esc(d.ip||"")}</td><td>${ago(d.last_seen)}</td><td><button class="btn sm d" data-fd="${d.id}">Remove</button></td></tr>`).join("")||'<tr><td colspan="4">No trusted devices yet.</td></tr>'}</table></div></div>
  <div class="glass card"><h3>Your data</h3><p class="sub">What this system stores about you: your profile, the accounts you analysed and their results, which pages you open, your feedback and your sign-in history. Administrators use it to run and improve the system. You can download everything, or delete saved analyses in My History.</p>
   <a class="btn" href="/api/account/export">⬇ Download my data (JSON)</a>
   <h3 style="margin-top:18px">Send feedback</h3><form id="ff"><div class="row"><label class="f" style="flex:1">Rating<select id="fr"><option value="5">5 - great</option><option value="4">4</option><option value="3">3</option><option value="2">2</option><option value="1">1 - poor</option></select></label>
   <label class="f" style="flex:1">About<select id="ft"><option value="general">General</option><option value="analyser">Account Analyser</option><option value="cube">3D cube</option><option value="dashboard">Dashboard</option><option value="login">Sign-in</option><option value="other">Other</option></select></label></div>
   <label class="f">Message<textarea id="fm" rows="3" minlength="3" maxlength="1000" required></textarea></label><div class="err" id="fe"></div><button class="btn">Send</button></form></div></div>`;
  meter(V.querySelector("#np"),V.querySelector("#nm"));
  V.querySelectorAll("[data-fd]").forEach(b=>b.onclick=async()=>{try{await api("/api/account/devices/"+b.dataset.fd,{method:"DELETE"});toast("Device removed","good");renderAccount()}catch(x){toast(x.message,"bad")}});
  V.querySelector("#avFile").onchange=async e=>{const f=e.target.files[0];if(!f)return;V.querySelector("#ae").textContent="";
    try{const r=await fetch("/api/account/avatar",{method:"POST",headers:{"X-Requested-With":"fetch","Content-Type":"application/octet-stream"},body:f,credentials:"same-origin"});
      if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||"Upload failed");
      const j=await r.json();ME.avatar=j.avatar;setAvatar(j.avatar);toast("Picture saved","good")}catch(x){V.querySelector("#ae").textContent=x.message}};
  V.querySelector("#pf").onsubmit=async e=>{e.preventDefault();V.querySelector("#pe").textContent="";
    try{const r=await api("/api/account/profile",{method:"PUT",body:{name:V.querySelector("#pn").value,phone:V.querySelector("#pp").value,country:V.querySelector("#pc").value,user_type:V.querySelector("#pt").value,handle:V.querySelector("#ph").value,interests:V.querySelector("#pi2").value}});
      ME.name=r.name;$("#meName").textContent=r.name;toast("Profile saved","good")}catch(x){V.querySelector("#pe").textContent=x.message}};
  V.querySelector("#cf").onsubmit=async e=>{e.preventDefault();V.querySelector("#ce").textContent="";
    if(V.querySelector("#np").value!==V.querySelector("#np2").value){V.querySelector("#ce").textContent="The two new passwords do not match.";return}
    try{await api("/api/account/password",{method:"POST",body:{current:V.querySelector("#cp").value,new:V.querySelector("#np").value}});toast("Password changed. Other devices were signed out.","good");renderAccount()}catch(x){V.querySelector("#ce").textContent=x.message}};
  V.querySelector("#ro").onclick=async()=>{try{const r=await api("/api/account/sessions/revoke-others",{method:"POST"});toast(r.closed+" device(s) signed out","good");renderAccount()}catch(x){toast(x.message,"bad")}};
  V.querySelector("#ff").onsubmit=async e=>{e.preventDefault();V.querySelector("#fe").textContent="";
    try{await api("/api/account/feedback",{method:"POST",body:{rating:+V.querySelector("#fr").value,topic:V.querySelector("#ft").value,message:V.querySelector("#fm").value}});V.querySelector("#fm").value="";toast("Thank you for your feedback","good")}catch(x){V.querySelector("#fe").textContent=x.message}}}

/* ---------------- start ---------------- */
(async()=>{try{enter(await api("/api/auth/me"));api("/api/account/profile").then(p=>{if(p.avatar)setAvatar(p.avatar)}).catch(()=>{})}catch(e){showAuth()}})();
