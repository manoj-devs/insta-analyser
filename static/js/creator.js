"use strict";
/* CREATOR INCOME ANALYSER (organic income, no sponsorship). Three pages: Post Analyzer, Income Planner, My Progress.
   All money is an ESTIMATE. Money is computed in USD on the server and shown in the chosen currency (shared with the Region page). */
const CR={meta:null,prof:null,last:null,plan:null,fromShot:false};
async function crInit(){
  if(!CR.meta){CR.meta=await api("/api/creator/meta");if(CR.meta.inr_per_usd)RG.rate=CR.meta.inr_per_usd}
  if(!CR.prof){try{CR.prof=await api("/api/creator/profile")}catch(e){CR.prof={}}}
  return CR.meta}
const cm=u=>{if(RG.cur==="USD"&&Math.abs(u)<10)return "$"+u.toFixed(2);return money(u)};
const toUsd=v=>RG.cur==="INR"?v/RG.rate:v;
const fromUsd=u=>RG.cur==="INR"?u*RG.rate:u;
const cnum=(el)=>{const v=el.value.trim();return v===""?null:Math.max(0,Math.round(Number(v)))};
const crCountries=()=>typeof COUNTRIES!=="undefined"?COUNTRIES:["India","United States","United Kingdom"];
const curSeg=()=>`<div class="seg" id="crCur" role="group" aria-label="Currency"><button data-c="INR">₹ INR</button><button data-c="USD">$ USD</button></div>`;
function bindCur(V,again){const mark=()=>V.querySelectorAll("#crCur button").forEach(b=>b.classList.toggle("on",b.dataset.c===RG.cur));mark();
  V.querySelectorAll("#crCur button").forEach(b=>b.onclick=()=>{RG.cur=b.dataset.c;try{localStorage.setItem("iw_cur",RG.cur)}catch(e){}mark();again()})}
const badge=`<span class="pill" style="border-color:var(--good);color:var(--good)" title="Brand deals and sponsored posts are not part of this page">Organic income only · no sponsorship</span>`;
const cfield=(id,l,extra="")=>`<label class="f">${l}<input id="${id}" type="number" min="0" inputmode="numeric" ${extra}></label>`;
const pcBar=p=>`<div style="position:relative;height:14px;border-radius:99px;background:linear-gradient(90deg,var(--bad),var(--warn),var(--good));margin:14px 0 6px"><i style="position:absolute;left:calc(${Math.min(Math.max(p,1),99)}% - 7px);top:-4px;width:14px;height:22px;border-radius:6px;background:var(--text);border:2px solid var(--bg)"></i></div>
 <div class="row" style="justify-content:space-between"><span class="sub">weaker</span><span class="sub">stronger than other posts of your size</span></div>`;
const range3=(o,label)=>`<div class="grid" style="grid-template-columns:repeat(3,1fr);gap:8px">${[["Low","low"],["Likely","mid"],["High","high"]].map(([t,k])=>`<div class="glass card kpi" style="padding:10px;${k==="mid"?"border-color:var(--a2)":""}"><span class="sub">${t}</span><b style="font-size:${k==="mid"?24:19}px">${cm(o[k])}</b><span class="sub">${label}</span></div>`).join("")}</div>`;

/* ======================= PAGE 1: POST ANALYZER ======================= */
async function creatorPage(V){
  const M=await crInit(),P=CR.prof||{};CR.fromShot=false;
  V.innerHTML=`<div class="glass card"><div class="row" style="justify-content:space-between"><div><h3 style="margin:0">Post Analyzer</h3>
    <p class="sub" style="margin:4px 0 0">Enter one post's numbers, or upload a screenshot of its Insights. You get its engagement, how it compares with other posts of your size, and what it could earn on its own.</p></div>${curSeg()}</div>
    <div class="row" style="margin-top:8px">${badge}</div>
    <div class="glass card" style="margin-top:12px;border-style:dashed" id="crDrop">
      <div class="row" style="justify-content:space-between"><div><b>Read a screenshot</b><p class="sub" style="margin:2px 0 0">${M.ocr?"Upload a screenshot of the post's Insights (or a post or profile). The numbers are filled in for you to check. The picture is read and thrown away; it is never saved.":"Screenshot reading is not set up on this server, so please type the numbers below."}</p></div>
      <div><input id="crFile" type="file" accept="image/png,image/jpeg,image/webp" hidden><button class="btn p" id="crPick" ${M.ocr?"":"disabled"}>Upload screenshot</button></div></div><div id="crShotMsg" class="sub" style="margin-top:8px" aria-live="polite"></div></div>
    <div class="rgf" style="margin-top:14px">
      ${cfield("caFol","Followers","required")}${cfield("caLik","Likes")}${cfield("caCom","Comments")}${cfield("caSav","Saves")}${cfield("caSh","Shares")}${cfield("caRe","Reach (accounts reached)")}
      <label class="f">Post type<select id="caType">${M.post_types.map(t=>`<option>${t}</option>`).join("")}</select></label>
      <label class="f">Country<select id="caCy">${crCountries().map(c=>`<option>${esc(c)}</option>`).join("")}</select></label>
      ${cfield("caHash","Hashtags used")}${cfield("caCap","Caption length (characters)")}
      <label class="f">Name this post (optional)<input id="caLabel" maxlength="80" placeholder="e.g. Sunday reel"></label>
      <label class="f">Posted on (optional)<input id="caDate" type="date"></label></div>
    <details style="margin-top:6px" open><summary style="cursor:pointer"><b>What are you promoting in this post?</b> <span class="sub">(your own offer or affiliate link, not a brand deal)</span></summary>
      <div class="rgf" style="margin-top:10px"><label class="f">Offer<select id="caOffer"><option value="affiliate">Affiliate link</option><option value="product">My own product</option><option value="service">My service</option></select></label>
      ${cfield("caPrice","Price or order value","placeholder='default'")}${cfield("caEarn","You keep % (commission or margin)","placeholder='default' max='100'")}${cfield("caClk","Link clicks (if you know)")}${cfield("caOrd","Orders (if you know)")}</div></details>
    <div class="row" style="margin-top:8px"><button class="btn p" id="caGo">Analyze this post</button><span class="err" id="caErr" style="color:var(--bad)"></span></div></div>
    <div id="caOut" style="margin-top:14px"></div>`;
  const q=s=>V.querySelector(s);bindCur(V,()=>CR.last&&show(CR.last));
  if(P.followers)q("#caFol").value=P.followers;q("#caCy").value=P.country||(ME&&ME.country)||"India";
  q("#crPick").onclick=()=>q("#crFile").click();
  q("#crFile").onchange=async e=>{const f=e.target.files[0];e.target.value="";if(!f)return;const m=q("#crShotMsg");
    if(f.size>6e6){m.textContent="That picture is bigger than 6 MB. Please crop it.";return}
    m.textContent="Reading the picture…";q("#crPick").disabled=true;
    try{const r=await fetch("/api/creator/ocr",{method:"POST",credentials:"same-origin",headers:{"X-Requested-With":"fetch","Content-Type":f.type||"image/png"},body:f});
      const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(typeof d.detail==="string"?d.detail:"Could not read the picture.");
      const map={followers:"caFol",likes:"caLik",comments:"caCom",saves:"caSav",shares:"caSh",reach:"caRe"},got=[];
      V.querySelectorAll(".det").forEach(x=>{x.classList.remove("det");x.style.borderColor=""});
      for(const [k,id] of Object.entries(map)){const x=d.fields[k];if(!x)continue;const el=q("#"+id);el.value=x.value;el.classList.add("det");el.style.borderColor=x.check?"var(--warn)":"var(--good)";got.push(`${k} ${n(x.value)}${x.check?" (check)":""}`)}
      if(!d.fields.reach&&d.fields.views){q("#caRe").value=d.fields.views.value;q("#caRe").classList.add("det");q("#caRe").style.borderColor="var(--warn)";got.push(`views ${n(d.fields.views.value)} used as reach (check)`)}
      CR.fromShot=got.length>0;
      m.innerHTML=got.length?`<b style="color:var(--good)">Found ${got.length} number${got.length>1?"s":""}:</b> ${esc(got.join(", "))}. <b>Please check each highlighted box before you analyze</b> (green = clear, amber = please double-check). Anything not found you can type in.`
        :`I could not find any numbers. Try a clearer screenshot of the Insights screen, or type the numbers in.`}
    catch(x){m.innerHTML=`<span style="color:var(--bad)">${esc(x.message)}</span>`}
    q("#crPick").disabled=!M.ocr};
  const body=()=>{const o={followers:cnum(q("#caFol")),likes:cnum(q("#caLik"))||0,comments:cnum(q("#caCom"))||0,saves:cnum(q("#caSav"))||0,shares:cnum(q("#caSh"))||0,reach:cnum(q("#caRe")),
    post_type:q("#caType").value,country:q("#caCy").value,hashtags:cnum(q("#caHash")),caption_len:cnum(q("#caCap")),offer:q("#caOffer").value,link_clicks:cnum(q("#caClk")),orders:cnum(q("#caOrd")),
    label:q("#caLabel").value.trim(),posted_on:q("#caDate").value,source:CR.fromShot?"screenshot":"manual"};
    const pr=q("#caPrice").value.trim(),ep=q("#caEarn").value.trim();if(pr!=="")o.price_usd=toUsd(Number(pr));if(ep!=="")o.earn_pct=Math.min(100,Number(ep));
    Object.keys(o).forEach(k=>{if(o[k]===null)delete o[k]});return o};
  function show(r){CR.last=r;const o=q("#caOut");
    o.innerHTML=`<div class="grid kpis"><div class="glass card kpi"><span class="sub">Engagement rate</span><b>${r.er_pct}%</b><span class="sub">likes + comments ÷ followers. Typical for your size: ${r.band_median}%</span></div>
     <div class="glass card kpi"><span class="sub">Compared with other posts of your size</span><b>Ahead of ${r.percentile}%</b><span class="sub">${esc(r.band)} · ${n(r.posts_in_band)} posts</span></div>
     <div class="glass card kpi"><span class="sub">Verdict</span><b>${esc(r.verdict)}</b><span class="sub">${r.vs_my_average?`${r.vs_my_average.diff_pct>=0?"+":""}${r.vs_my_average.diff_pct}% vs your last ${r.vs_my_average.of_posts} saved posts`:"Save posts to compare with your own average"}</span></div>
     <div class="glass card kpi"><span class="sub">Reach ${r.reach_estimated?"(estimated)":""}</span><b>${n(r.reach)}</b><span class="sub">engagement on reach: ${r.er_on_reach_pct}%</span></div></div>
     <div class="glass card" style="margin-top:14px"><h3>Where this post sits</h3>${pcBar(r.percentile)}</div>
     <div class="glass card" style="margin-top:14px"><div class="row" style="justify-content:space-between"><h3 style="margin:0">What this post could earn on its own</h3>${badge}</div>
      <p class="sub">${esc({affiliate:"Affiliate link",product:"Your own product",service:"Your service"}[r.offer])} · price used ${cm(r.price_usd)} · you keep ${r.earn_pct}% · based on ${esc(r.basis)}. An estimate, not a payment.</p>${range3(r.income_usd,"this post")}</div>
     <div class="glass card" style="margin-top:14px"><h3>What to try next</h3>${r.tips.length?`<ul style="margin:6px 0 0 18px">${r.tips.map(t=>`<li>${esc(t)}</li>`).join("")}</ul>`:'<p class="sub">Add hashtags and caption length to get tips for this post.</p>'}
      <div class="row" style="margin-top:12px"><button class="btn p" id="caSave">Save to My Progress</button><a class="btn" href="#creator_plan">Plan my monthly income →</a></div></div>`;
    o.querySelector("#caSave").onclick=async()=>{try{await api("/api/creator/posts",{method:"POST",body:body()});toast("Saved to My Progress","good");o.querySelector("#caSave").disabled=true}catch(x){toast(x.message,"bad")}};
    o.scrollIntoView({behavior:"smooth",block:"start"})}
  q("#caGo").onclick=async()=>{const e=q("#caErr");e.textContent="";const b=body();if(!b.followers||b.followers<1){e.textContent="Please enter your follower count.";q("#caFol").focus();return}
    q("#caGo").disabled=true;try{show(await api("/api/creator/analyze",{method:"POST",body:b}))}catch(x){e.textContent=x.message}q("#caGo").disabled=false}}

/* ======================= PAGE 2: INCOME PLANNER ======================= */
function projChart(rows){const W=560,H=220,L=48,R=12,T=14,B=28,mx=Math.max(...rows.map(r=>r.high),.01)*1.1,X=i=>L+i*(W-L-R)/Math.max(rows.length-1,1),Y=v=>T+(H-T-B)*(1-v/mx);
  const path=k=>rows.map((r,i)=>(i?"L":"M")+X(i).toFixed(1)+" "+Y(r[k]).toFixed(1)).join(" ");
  let g="";[0,.5,1].forEach(f=>{g+=`<line x1="${L}" x2="${W-R}" y1="${Y(mx*f/1.0)}" y2="${Y(mx*f/1.0)}" stroke="var(--line)"/><text x="${L-6}" y="${Y(mx*f)+4}" text-anchor="end" font-size="10" fill="var(--muted)">${cm(mx*f).replace(/\.00$/,"")}</text>`});
  rows.forEach((r,i)=>{if(i%3===2||i===0)g+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle" font-size="10" fill="var(--muted)">M${r.month}</text>`});
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%" role="img" aria-label="Projected monthly income, low, likely and high">${g}<path d="${path("high")}" fill="none" stroke="var(--good)" stroke-width="2" stroke-dasharray="4 3"/><path d="${path("low")}" fill="none" stroke="var(--bad)" stroke-width="2" stroke-dasharray="4 3"/><path d="${path("mid")}" fill="none" stroke="var(--a2)" stroke-width="3"/></svg>
  <div class="chips"><span class="chip">━ likely</span><span class="chip up">┅ high</span><span class="chip dn">┅ low</span></div>`}
function ring(score,label){const c=2*Math.PI*44,d=c*score/100;return `<svg viewBox="0 0 110 110" style="width:130px" role="img" aria-label="Readiness ${score} out of 100"><circle cx="55" cy="55" r="44" fill="none" stroke="var(--line)" stroke-width="10"/><circle cx="55" cy="55" r="44" fill="none" stroke="var(--a2)" stroke-width="10" stroke-linecap="round" stroke-dasharray="${d} ${c}" transform="rotate(-90 55 55)"/><text x="55" y="54" text-anchor="middle" font-size="26" font-weight="700" fill="var(--text)">${score}</text><text x="55" y="72" text-anchor="middle" font-size="10" fill="var(--muted)">out of 100</text></svg>`}
async function planPage(V){
  const M=await crInit(),P=CR.prof||{},en=P.enabled||{affiliate:true},ck=P.checklist||{};
  const SK=Object.keys(M.streams);
  V.innerHTML=`<div class="glass card"><div class="row" style="justify-content:space-between"><div><h3 style="margin:0">Income Planner</h3>
    <p class="sub" style="margin:4px 0 0">Tell us about your account. We estimate what your own content could earn each month from the income streams you switch on, how ready you are, and the best next steps. Everything updates as you change a number.</p></div>${curSeg()}</div>
    <div class="row" style="margin-top:8px">${badge}</div>
    <div class="rgf" style="margin-top:12px">${cfield("plFol","Followers","required")}
      <label class="f">Posts per week<input id="plPpw" type="number" min="0" max="40" step="0.5" value="${P.posts_per_week??3}"></label>
      <label class="f">Country<select id="plCy">${crCountries().map(c=>`<option>${esc(c)}</option>`).join("")}</select></label>
      ${cfield("plEr","Your usual engagement % (optional)","step='0.1' placeholder='typical for your size'")}${cfield("plRe","Average reach per post (optional)")}${cfield("plSS","Saves + shares as % of reach (optional)","placeholder='e.g. 1.5'")}</div>
    <h4 style="margin:12px 0 6px">Income streams to include</h4><div class="grid eq" id="plStreams">${SK.map(k=>`<div class="glass card" style="padding:12px"><label class="row" style="gap:8px;cursor:pointer"><input type="checkbox" data-k="${k}" ${en[k]?"checked":""} style="width:auto"><b>${esc(M.streams[k].title)}</b></label>
      <p class="sub" style="margin:4px 0 6px">${esc(M.streams[k].how)}</p><label class="f" style="margin:0">${k==="affiliate"?"Average order value":"Price"} <small>(leave empty for the default)</small><input data-p="${k}" type="number" min="0" inputmode="decimal" placeholder="default"></label></div>`).join("")}</div>
    <h4 style="margin:12px 0 6px">Profile set-up</h4><div class="chips" id="plCk">${[["link","A link in my bio"],["niche","One clear topic"],["business","Creator or business account"],["contact","Contact email on profile"]].map(([k,l])=>`<label class="chip" style="cursor:pointer"><input type="checkbox" data-c="${k}" ${ck[k]?"checked":""} style="width:auto;margin-right:6px">${l}</label>`).join("")}</div>
    <div class="row" style="margin-top:8px"><button class="btn" id="plSave">Save my plan</button><button class="btn" id="plPdf">⬇ PDF report card</button><span class="err" id="plErr" style="color:var(--bad)"></span></div></div>
    <div id="plOut" style="margin-top:14px"></div>
    <div class="glass card" style="margin-top:14px"><h3>How the numbers are made</h3><div id="plAs"></div></div>`;
  const q=s=>V.querySelector(s);bindCur(V,()=>CR.plan&&paint(CR.plan));
  q("#plFol").value=P.followers||"";q("#plCy").value=P.country||(ME&&ME.country)||"India";if(P.er_pct)q("#plEr").value=P.er_pct;if(P.reach_per_post)q("#plRe").value=P.reach_per_post;if(P.save_share_pct)q("#plSS").value=P.save_share_pct;
  Object.entries(P.prices||{}).forEach(([k,v])=>{const el=q(`[data-p=${k}]`);if(el&&v)el.value=Math.round(fromUsd(v)*100)/100});
  const A=M.assumptions;q("#plAs").innerHTML=`<p class="sub">${esc(A.note)}</p><ul style="margin:6px 0 0 18px;font-size:13px">
    <li>One post reaches about ${Object.entries(A.reach_rate_of_followers).map(([b,v])=>`${Math.round(v*100)}% of followers (${esc(b)})`).join(", ")}. Reels reach ×${A.reach_by_post_type.reel}.</li>
    <li>Affiliate: ${(A.streams.affiliate.ctr[1]*100).toFixed(1)}% of reach clicks the link, ${(A.streams.affiliate.conv[1]*100).toFixed(1)}% of clickers buy, order value about $${A.streams.affiliate.aov_usd} scaled to your country, commission ${A.streams.affiliate.earn_pct}%.</li>
    <li>Own product: ${(A.streams.product.buyers[1]*100).toFixed(2)}% of followers buy each month at about $${A.streams.product.price_usd}. Service: ${(A.streams.service.leads[1]*100).toFixed(2)}% enquire, ${Math.round(A.streams.service.close*100)}% are won, about $${A.streams.service.price_usd} a job. Subscription: ${(A.streams.membership.subs[1]*100).toFixed(2)}% subscribe at about $${A.streams.membership.price_usd} a month.</li>
    <li>"Low" and "High" use the lower and upper rates for each step. Posting fewer than ${A.target_posts_per_week} times a week lowers own-product, service and subscription income.</li>
    <li>${esc(A.platform_programs)} ${esc(A.sponsorship)}</li><li>${esc(A.benchmark)}</li></ul>`;
  const read=()=>{const o={followers:cnum(q("#plFol")),posts_per_week:Number(q("#plPpw").value||0),country:q("#plCy").value,enabled:{},prices:{},checklist:{}};
    const er=q("#plEr").value.trim(),re=cnum(q("#plRe")),ss=q("#plSS").value.trim();if(er!=="")o.er_pct=Number(er);if(re)o.reach_per_post=re;if(ss!=="")o.save_share_pct=Math.min(100,Number(ss));
    V.querySelectorAll("[data-k]").forEach(c=>o.enabled[c.dataset.k]=c.checked);V.querySelectorAll("[data-c]").forEach(c=>o.checklist[c.dataset.c]=c.checked);
    V.querySelectorAll("[data-p]").forEach(c=>{const v=c.value.trim();if(v!=="")o.prices[c.dataset.p]=toUsd(Number(v))});
    if(CR.growth!=null)o.growth_pct=CR.growth;return o};
  function paint(R){CR.plan=R;const m=R.model,rd=R.readiness,o=q("#plOut"),T=m.total_usd,pr=R.projection;
    o.innerHTML=`<div class="grid kpis"><div class="glass card kpi"><span class="sub">Likely monthly income</span><b>${cm(T.mid)}</b><span class="sub">from the streams switched on</span></div>
      <div class="glass card kpi"><span class="sub">Range</span><b style="font-size:20px">${cm(T.low)} – ${cm(T.high)}</b><span class="sub">low to high</span></div>
      <div class="glass card kpi"><span class="sub">Likely in a year</span><b>${cm(T.mid*12)}</b><span class="sub">today's size, no growth</span></div>
      <div class="glass card kpi"><span class="sub">Engagement vs your size</span><b>Ahead of ${rd.percentile}%</b><span class="sub">${esc(m.band)} · ${m.er_pct}%</span></div></div>
     <div class="grid eq" style="margin-top:14px"><div class="glass card"><h3>Income by stream</h3><p class="sub">Likely per month. Switched-off streams show what you could add.</p>
       ${bars(Object.values(m.streams).map(s=>[s.title+(s.enabled?"":" (off)"),s.usd.mid]),cm)}</div>
      <div class="glass card"><h3>Readiness to earn</h3><div class="row" style="gap:16px;flex-wrap:nowrap">${ring(rd.score,rd.label)}<div><b style="font-size:18px">${esc(rd.label)}</b><div class="sub" style="margin-top:4px">${rd.items.map(i=>`${esc(i.name)} ${i.got}/${i.of}`).join(" · ")}</div></div></div>
       <ul style="margin:10px 0 0 18px;font-size:13px">${rd.items.map(i=>`<li>${esc(i.note)}</li>`).join("")}</ul>${rd.missing_setup.length?`<p class="sub" style="margin-top:8px">Still to do: ${esc(rd.missing_setup.join(", "))}.</p>`:""}</div></div>
     <div class="glass card" style="margin-top:14px"><h3>Steps to earn more</h3><p class="sub">Each step re-runs the same model with one change, so the gain shown is what that change alone adds per month (likely case).</p>
       ${R.steps.length?R.steps.map((s,i)=>`<div class="step"><div class="sn">${i+1}</div><div><b>${esc(s.title)}</b> <span class="chip up">+${cm(s.extra_usd_month)} / month${s.extra_pct!=null?` (+${s.extra_pct}%)`:""}</span><div class="sub">${esc(s.why)}</div><div style="font-size:13px;margin-top:2px">${esc(s.todo)}</div></div></div>`).join(""):'<p class="sub">Great: none of the single changes we test would add more.</p>'}</div>
     <div class="glass card" style="margin-top:14px"><h3>What-if simulator</h3><p class="sub">Drag to see how posting more and growing faster changes the next 12 months.</p>
       <div class="grid eq"><label class="f">Posts per week: <b id="wiP">${q("#plPpw").value}</b><input id="wiPpw" type="range" min="0" max="14" step="0.5" value="${q("#plPpw").value}"></label>
       <label class="f">Follower growth per month: <b id="wiG">${pr.growth_pct_month}%</b><input id="wiGr" type="range" min="0" max="15" step="0.5" value="${pr.growth_pct_month}"></label></div>
       <div class="grid eq"><div>${projChart(pr.rows)}</div><div class="wrap"><table><tr><th>Month</th><th class=n>Followers</th><th class=n>Likely / month</th><th class=n>Total so far</th></tr>
        ${[3,6,12].map(k=>pr.milestones[k]).map(r=>`<tr><td>${r.month}</td><td class=n>${n(r.followers)}</td><td class=n>${cm(r.mid)}</td><td class=n>${cm(r.cumulative_mid)}</td></tr>`).join("")}</table>
        <p class="sub">Growth rate is an assumption you can move. It is not a forecast.</p></div></div></div>`;
    const wi=()=>{q("#wiP").textContent=q("#wiPpw").value;q("#wiG").textContent=q("#wiGr").value+"%"};
    o.querySelector("#wiPpw").oninput=e=>{wi();q("#plPpw").value=e.target.value;sched()};o.querySelector("#wiGr").oninput=e=>{wi();CR.growth=Number(e.target.value);sched()}}
  let tm;const sched=()=>{clearTimeout(tm);tm=setTimeout(go,350)};
  async function go(){const e=q("#plErr");e.textContent="";const b=read();if(!b.followers){q("#plOut").innerHTML='<div class="glass card"><p class="sub">Enter your follower count above to see your plan.</p></div>';return}
    try{paint(await api("/api/creator/plan",{method:"POST",body:b}))}catch(x){e.textContent=x.message}}
  V.querySelectorAll("#plFol,#plPpw,#plCy,#plEr,#plRe,#plSS,[data-k],[data-p],[data-c]").forEach(el=>{el.oninput=sched;el.onchange=sched});
  q("#plSave").onclick=async()=>{try{const b=read();await api("/api/creator/profile",{method:"PUT",body:b});CR.prof=b;toast("Plan saved. It will be here on your other devices too.","good")}catch(x){toast(x.message,"bad")}};
  q("#plPdf").onclick=async()=>{const b=read();if(!b.followers){toast("Enter your follower count first","bad");return}
    try{const r=await fetch(`/api/creator/report?cur=${RG.cur}&handle=${encodeURIComponent((ME&&ME.name)||"")}`,{method:"POST",credentials:"same-origin",headers:{"X-Requested-With":"fetch","Content-Type":"application/json"},body:JSON.stringify(b)});
      if(!r.ok)throw new Error("Could not make the report");const u=URL.createObjectURL(await r.blob()),a=document.createElement("a");a.href=u;a.download="creator_report_card.pdf";document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),2000)}catch(x){toast(x.message,"bad")}};
  CR.growth=null;go()}

/* ======================= PAGE 3: MY PROGRESS ======================= */
async function histPage(V){
  const M=await crInit(),H=await api("/api/creator/posts"),rows=H.rows,S=H.summary;
  V.innerHTML=`<div class="glass card"><div class="row" style="justify-content:space-between"><div><h3 style="margin:0">My Progress</h3><p class="sub" style="margin:4px 0 0">Your saved posts, how your engagement is moving, and what worked best for accounts of your size in the warehouse.</p></div>${curSeg()}</div><div class="row" style="margin-top:8px">${badge}</div></div>
   <div id="hsMine" style="margin-top:14px"></div><div class="glass card" style="margin-top:14px"><div class="row" style="justify-content:space-between"><h3 style="margin:0">What worked for accounts like yours</h3>
    <label class="f" style="margin:0">Size band <select id="hsBand"><option value="">All sizes</option>${M.bands.map(b=>`<option>${esc(b)}</option>`).join("")}</select></label></div><div id="hsIns"></div></div>`;
  const q=s=>V.querySelector(s);bindCur(V,()=>mine());
  function mine(){const o=q("#hsMine");
    if(!rows.length){o.innerHTML='<div class="glass card"><h3>No saved posts yet</h3><p class="sub">Analyze a post and press "Save to My Progress". Your trend and your best posts show up here.</p><a class="btn p" href="#creator">Open the Post Analyzer</a></div>';return}
    const asc=rows.slice().reverse(),tr={up:"▲ improving",down:"▼ slipping",steady:"■ steady"}[S.trend]||"need 8+ posts";
    o.innerHTML=`<div class="grid kpis"><div class="glass card kpi"><span class="sub">Posts saved</span><b>${S.posts}</b></div><div class="glass card kpi"><span class="sub">Average engagement</span><b>${S.avg_er_pct}%</b><span class="sub">average rank: ahead of ${S.avg_percentile}%</span></div>
      <div class="glass card kpi"><span class="sub">Recent trend</span><b style="font-size:20px">${tr}</b><span class="sub">last 5 vs the 5 before</span></div><div class="glass card kpi"><span class="sub">Likely income, all saved posts</span><b>${cm(S.total_income_mid_usd)}</b><span class="sub">estimate</span></div></div>
     <div class="glass card" style="margin-top:14px"><h3>Engagement rate over time</h3><p class="sub">Oldest to newest, per saved post (%)</p>${asc.length>1?line(asc.map((_,i)=>String(i+1)),asc.map(r=>r.er_pct)):'<p class="sub">Save one more post to see a trend.</p>'}</div>
     <div class="glass card" style="margin-top:14px"><h3>Saved posts</h3><div class="wrap"><table><tr><th>Date</th><th>Post</th><th>Type</th><th class=n>Followers</th><th class=n>Engagement</th><th class=n>Rank</th><th class=n>Likely income</th><th></th></tr>
      ${rows.map(r=>`<tr><td>${when(r.ts).split(",")[0]}</td><td>${esc(r.label||"—")}${r.id===S.best?' <span class="chip up">best</span>':""}${r.source==="screenshot"?' <span class="chip">screenshot</span>':""}</td><td>${esc(r.post_type)}</td><td class=n>${n(r.followers)}</td><td class=n>${r.er_pct}%</td><td class=n>${r.percentile}%</td><td class=n>${cm(r.income_mid)}</td><td><button class="btn sm d" data-del="${r.id}" aria-label="Delete this post">Delete</button></td></tr>`).join("")}</table></div></div>`;
    o.onclick=async e=>{const b=e.target.closest("[data-del]");if(!b)return;try{await api("/api/creator/posts/"+b.dataset.del,{method:"DELETE"});toast("Deleted","good");histPage(V)}catch(x){toast(x.message,"bad")}}}
  mine();
  async function ins(){const I=await api("/api/creator/insights?band="+encodeURIComponent(q("#hsBand").value)),f=v=>v+"%";
    const blk=(t,rs)=>rs.length?`<div><h4 style="margin:12px 0 4px">${t}</h4>${bars(rs.map(r=>[r.label,r.median_er]),f)}</div>`:"";
    q("#hsIns").innerHTML=`<p class="sub">${n(I.posts)} posts · typical engagement ${I.median_er}% · top quarter starts at ${I.p75}% · top 10% start at ${I.p90}%. ${esc(I.note)}</p>
     <div class="grid eq">${blk("By number of hashtags",I.hashtags)}${blk("By caption length",I.caption)}${blk("By weekday",I.weekday)}${blk("By hour of day (top 8)",I.hour.slice().sort((a,b)=>b.median_er-a.median_er).slice(0,8))}</div>
     <p class="sub" style="margin-top:8px">Bars show the median engagement rate of posts in that group. These are patterns from older posts, so treat them as ideas to test rather than rules.</p>`}
  q("#hsBand").onchange=ins;ins()}
