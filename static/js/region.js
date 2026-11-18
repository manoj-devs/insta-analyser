"use strict";
/* Region-wise influencer analyser (used by the user portal and the admin portal). All money is an ESTIMATE. */
const RG={cur:(()=>{try{return localStorage.getItem("iw_cur")||"INR"}catch(e){return"INR"}})(),rate:88,f:{continent:"",country:"",state:"",category:"",tier:"",q:""},sort:"year",dir:"desc",page:1,meta:null};
function money(usd,short){const v=RG.cur==="INR"?usd*RG.rate:usd,s=RG.cur==="INR"?"₹":"$";
  if(short){const a=Math.abs(v);if(RG.cur==="INR"){if(a>=1e7)return s+(v/1e7).toFixed(2)+" Cr";if(a>=1e5)return s+(v/1e5).toFixed(2)+" L"}else{if(a>=1e6)return s+(v/1e6).toFixed(2)+"M";if(a>=1e4)return s+(v/1e3).toFixed(0)+"K"}}
  return s+Math.round(v).toLocaleString(RG.cur==="INR"?"en-IN":"en-US")}
const catName=c=>(c||"").replace(/_&_/g," & ").replace(/_/g," ");
const qs=(o)=>Object.entries(o).filter(([k,v])=>v!==""&&v!=null).map(([k,v])=>k+"="+encodeURIComponent(v)).join("&");
async function regionPage(V,admin){
  const M=RG.meta=await api("/api/regions");RG.rate=M.inr_per_usd;RG.page=1;
  V.innerHTML=`<div class="glass card"><div class="row" style="justify-content:space-between"><div><h3 style="margin:0">Influencers by region</h3>
    <p class="sub" style="margin:4px 0 0">${n(M.total)} influencers in the directory. Choose a region to see every influencer in it, what they are estimated to earn, and the steps to earn more.</p></div>
    <div class="seg" id="rgCur" role="group" aria-label="Currency"><button data-c="INR">₹ INR</button><button data-c="USD">$ USD</button></div></div>
   <div class="rgf"><label class="f">Continent<select id="rgCo"></select></label><label class="f">Country<select id="rgCy"></select></label><label class="f">State / region<select id="rgSt"></select></label>
   <label class="f">Category<select id="rgCa"></select></label><label class="f">Size band<select id="rgTi"></select></label><label class="f">Search handle or name<input id="rgQ" placeholder="type to search" maxlength="40"></label></div>
   <div class="row" style="margin-top:6px"><a class="btn sm" id="rgCsv">⬇ CSV</a><a class="btn sm" id="rgXls">⬇ Excel</a><button class="btn sm" id="rgCmp">⇄ Compare two regions</button><button class="btn sm" id="rgClr">Clear filters</button></div>
   <div class="warn" id="rgDemo" hidden style="margin-top:10px"></div><p class="sub" style="margin:10px 0 0">${esc(M.note)} Region price levels and the share of paid posts are assumptions shown at the bottom of this page.</p></div>
   <div id="rgKpi" class="grid kpis" style="margin-top:14px"></div><div id="rgCharts" class="grid eq" style="margin-top:14px"></div>
   <div class="glass card" style="margin-top:14px"><div id="rgTbl"></div></div><div id="rgCmpBox"></div>
   <div class="glass card" style="margin-top:14px"><h3>How the numbers are made</h3><p class="sub">Per-post fee = a published rate curve by follower count, scaled by engagement against the typical rate for that size, a category factor and a region price level. Yearly income = fee x paid posts a year (${M.assumptions.sponsored_share_pct}% of posts by default, at most 120). Projections assume ${M.assumptions.growth_pct_month}% follower growth a month. The directory only holds the influencers that were loaded into it, so it is not every influencer in the world.</p>
   <details><summary class="sub" style="cursor:pointer">Region price levels used (1.0 = global benchmark)</summary><div class="chips" style="margin-top:8px">${Object.entries(M.assumptions.region_factor).map(([k,v])=>`<span class="chip">${esc(k)} ${v}</span>`).join("")}<span class="chip">other countries 0.6</span></div></details></div>`;
  const q=s=>V.querySelector(s);
  const opt=(a,all)=>`<option value="">${all}</option>`+a.map(x=>`<option${Array.isArray(x)?` value="${esc(x[0])}"`:""}>${esc(Array.isArray(x)?x[1]:x)}</option>`).join("");
  const fill=()=>{const T=M.tree,f=RG.f;q("#rgCo").innerHTML=opt(Object.keys(T).sort(),"All continents");q("#rgCo").value=f.continent;
    const cs=Object.entries(T).filter(([k])=>!f.continent||k===f.continent).flatMap(([k,v])=>Object.entries(v).map(([c,x])=>[c,x.n])).sort((a,b)=>b[1]-a[1]);
    q("#rgCy").innerHTML=opt(cs.map(c=>[c[0],`${c[0]} (${c[1]})`]),"All countries");q("#rgCy").value=f.country;
    let ss=[];for(const ct of Object.values(T))if(ct[f.country])ss=Object.entries(ct[f.country].states).sort((a,b)=>b[1]-a[1]).map(s=>[s[0],`${s[0]} (${s[1]})`]);
    q("#rgSt").innerHTML=opt(ss,f.country?"All states / regions":"Choose a country first");q("#rgSt").disabled=!f.country;q("#rgSt").value=f.state;
    q("#rgCa").innerHTML=opt(M.categories.map(c=>[c,catName(c)]),"All categories");q("#rgCa").value=f.category;q("#rgTi").innerHTML=opt(M.tiers,"All sizes");q("#rgTi").value=f.tier};
  fill();
  const cur=()=>{V.querySelectorAll("#rgCur button").forEach(b=>b.classList.toggle("on",b.dataset.c===RG.cur))};cur();
  V.querySelectorAll("#rgCur button").forEach(b=>b.onclick=()=>{RG.cur=b.dataset.c;try{localStorage.setItem("iw_cur",RG.cur)}catch(e){}cur();load()});
  const chg=(id,key,reset)=>{q(id).onchange=e=>{RG.f[key]=e.target.value;(reset||[]).forEach(k=>RG.f[k]="");RG.page=1;fill();load()}};
  chg("#rgCo","continent",["country","state"]);chg("#rgCy","country",["state"]);chg("#rgSt","state");chg("#rgCa","category");chg("#rgTi","tier");
  let tm;q("#rgQ").oninput=e=>{clearTimeout(tm);tm=setTimeout(()=>{RG.f.q=e.target.value;RG.page=1;load(true)},300)};
  q("#rgClr").onclick=()=>{RG.f={continent:"",country:"",state:"",category:"",tier:"",q:""};q("#rgQ").value="";RG.page=1;fill();load()};
  q("#rgCmp").onclick=()=>compareBox(V);
  async function load(keepKpi){const f=RG.f;
    const [S,L]=await Promise.all([api("/api/region/summary?"+qs(f)),api("/api/region/influencers?"+qs({...f,sort:RG.sort,dir:RG.dir,page:RG.page,size:25}))]);
    q("#rgCsv").href="/api/region/export?"+qs({...f,fmt:"csv"});q("#rgXls").href="/api/region/export?"+qs({...f,fmt:"xlsx"});
    const dm=q("#rgDemo");dm.hidden=true;dm.innerHTML="";
    if(!S.n){q("#rgKpi").innerHTML="";q("#rgCharts").innerHTML="";q("#rgTbl").innerHTML='<p class="sub">No influencer matches these filters.</p>';return}
    q("#rgKpi").innerHTML=[["Influencers",n(S.n),"in this selection"],["Total followers",n(S.followers_total),"combined audience"],["Median engagement",S.er_median+"%","likes + comments / followers"],
      ["Median yearly income",money(S.year_median,1),"estimate per influencer"],["Top category",catName(S.top_category),"most common"],["Avg posts / week",S.ppw_avg,"posting habit"]].map(k=>`<div class="glass card kpi"><span class="sub">${k[0]}</span><b style="font-size:${k[1].length>10?18:26}px">${esc(String(k[1]))}</b><span class="sub">${k[2]}</span></div>`).join("");
    q("#rgCharts").innerHTML=`<div class="glass card"><h3>Top earners (yearly, estimate)</h3>${bars(S.top10.map(t=>["@"+t.handle,t.year]),v=>money(v,1))}</div>
      <div class="glass card"><h3>How yearly income is spread</h3><p class="sub">Number of influencers in each yearly income band</p>${bars(S.hist,n)}</div>
      <div class="glass card"><h3>Share by size band</h3>${pctBars(S.tiers.map(t=>[t[0],t[1]/S.n*100,t[1]]))}</div>
      <div class="glass card"><h3>Most common categories</h3>${bars(S.categories.map(c=>[catName(c[0]),c[1]]))}</div>`;
    table(L)}
  function table(L){const th=(k,t,r)=>`<th class="${r?"r":""}" data-s="${k}" tabindex="0" role="button" aria-label="Sort by ${t}">${t}${RG.sort===k?(RG.dir==="asc"?" ▲":" ▼"):""}</th>`;
    q("#rgTbl").innerHTML=`<div class="row" style="justify-content:space-between"><h3 style="margin:0">All influencers in this selection (${n(L.n)})</h3><span class="sub">Page ${L.page} of ${L.pages}. Tap a row for details.</span></div>
     <div class="tbl"><table class="rgt"><tr>${th("handle","Influencer")}<th>Location</th>${th("category","Category")}<th>Band</th>${th("followers","Followers",1)}${th("er","Eng.",1)}${th("fee","Per post",1)}${th("month","Monthly",1)}${th("year","Yearly (low - high)",1)}</tr>
     ${L.rows.map(r=>`<tr class="clk" data-id="${r.id}" tabindex="0"><td><b>@${esc(r.handle)}</b><div class="sub">${esc(r.display_name||"")} · followers as of ${esc(r.as_of||"")}</div></td><td>${esc(r.state_or_region||"")}<div class="sub">${esc(r.country)}</div></td>
      <td>${esc(catName(r.category))}</td><td>${esc(r.tier)}</td><td class="r">${n(r.followers)}</td><td class="r">${r.er_known?r.er_pct+"%":"n/a"}</td><td class="r">${money(r.fee)}</td><td class="r">${money(r.month)}</td>
      <td class="r"><b>${money(r.year,1)}</b><div class="sub">${money(r.year_low,1)} - ${money(r.year_high,1)}</div></td></tr>`).join("")}</table></div>
     <div class="row" style="justify-content:center;margin-top:10px"><button class="btn sm" id="pgP"${L.page<=1?" disabled":""}>← Previous</button><span class="sub">${L.page} / ${L.pages}</span><button class="btn sm" id="pgN"${L.page>=L.pages?" disabled":""}>Next →</button></div>`;
    q("#rgTbl").querySelectorAll("th[data-s]").forEach(h=>{const go=()=>{const k=h.dataset.s;RG.dir=RG.sort===k&&RG.dir==="desc"?"asc":"desc";RG.sort=k;RG.page=1;load()};h.onclick=go;h.onkeydown=e=>{if(e.key==="Enter")go()}});
    q("#rgTbl").querySelectorAll("tr.clk").forEach(t=>{const go=()=>detail(+t.dataset.id);t.onclick=go;t.onkeydown=e=>{if(e.key==="Enter")go()}});
    q("#pgP").onclick=()=>{RG.page--;load()};q("#pgN").onclick=()=>{RG.page++;load()}}
  load()}

async function compareBox(V){const M=RG.meta,box=V.querySelector("#rgCmpBox");
  const list=[];for(const ct of Object.values(M.tree))for(const [c,x] of Object.entries(ct)){list.push([c,c+" ("+x.n+")"]);for(const s of Object.keys(x.states))list.push([c+"|"+s,"   "+c+" / "+s])}
  list.sort((a,b)=>a[0].localeCompare(b[0]));const o=(v)=>list.map(l=>`<option value="${esc(l[0])}"${l[0]===v?" selected":""}>${esc(l[1])}</option>`).join("");
  box.innerHTML=`<div class="glass card" style="margin-top:14px"><h3>Compare two regions</h3><div class="rgf"><label class="f">Region A<select id="ca">${o(RG.f.country||"India")}</select></label><label class="f">Region B<select id="cb">${o("United States")}</select></label></div><div id="cmpOut"></div></div>`;
  const run=async()=>{const a=box.querySelector("#ca").value,b=box.querySelector("#cb").value;const R=await api("/api/region/compare?"+qs({a,b}));
    const row=(l,f)=>`<tr><td>${l}</td><td class="r">${f(R.a)}</td><td class="r">${f(R.b)}</td></tr>`,z=s=>s.n?1:0;
    box.querySelector("#cmpOut").innerHTML=`<div class="tbl"><table><tr><th></th><th class="r">${esc(R.a.label)}</th><th class="r">${esc(R.b.label)}</th></tr>
      ${row("Influencers",s=>n(s.n))}${row("Total followers",s=>z(s)?n(s.followers_total):"-")}${row("Median engagement",s=>z(s)?s.er_median+"%":"-")}${row("Median yearly income",s=>z(s)?money(s.year_median,1):"-")}
      ${row("Total yearly income (all)",s=>z(s)?money(s.year_total,1):"-")}${row("Posts per week",s=>z(s)?s.ppw_avg:"-")}${row("Top category",s=>z(s)?esc(catName(s.top_category)):"-")}</table></div><p class="sub">${esc(R.note)}</p>`};
  box.querySelector("#ca").onchange=run;box.querySelector("#cb").onchange=run;run();box.scrollIntoView({behavior:"smooth"})}

async function detail(id){
  const P=await api("/api/influencer/"+id),bk=document.createElement("div");bk.className="rgd-back";
  const st=P.steps.map(s=>`<div class="step"><div class="sn">${s.rank}</div><div><b>${esc(s.title)}</b>${s.uplift_usd?` <span class="pill active">+${money(s.uplift_usd.year,1)} / year</span>`:""}
     <p class="sub" style="margin:4px 0">${esc(s.why)}</p><ul>${s.todo.map(t=>`<li>${esc(t)}</li>`).join("")}</ul>${s.uplift_usd?`<div class="sub">Estimated extra income ${money(s.uplift_usd.year_low,1)} to ${money(s.uplift_usd.year_high,1)} a year.</div>`:""}${s.note?`<div class="sub"><i>${esc(s.note)}</i></div>`:""}</div></div>`).join("");
  bk.innerHTML=`<aside class="rgd glass" role="dialog" aria-modal="true" aria-label="Influencer details"><button class="otp-x" aria-label="Close">×</button>
   <h3 style="margin:0">@${esc(P.handle)}</h3><p class="sub" style="margin:2px 0 10px">${esc(P.display_name||"")} · ${esc([P.city,P.state_or_region,P.country].filter(Boolean).join(", "))} · ${esc(catName(P.category))} · ${esc(P.tier)} band${P.verified?" · verified":""}</p>
   <div class="grid kpis dk"><div class="glass card kpi"><span class="sub">Followers</span><b>${n(P.followers)}</b><span class="sub">as of ${esc(P.as_of||"")}</span></div>
   <div class="glass card kpi"><span class="sub">Per sponsored post</span><b>${money(P.fee)}</b><span class="sub">${money(P.fee_low)} - ${money(P.fee_high)}</span></div>
   <div class="glass card kpi"><span class="sub">Per month</span><b>${money(P.month,1)}</b><span class="sub">about ${P.sponsored_per_year} paid posts a year</span></div>
   <div class="glass card kpi"><span class="sub">Per year</span><b>${money(P.year,1)}</b><span class="sub">${money(P.year_low,1)} - ${money(P.year_high,1)}</span></div></div>
   <p class="sub">${esc(P.note)} ${P.er_known?`Engagement ${P.er_pct}% against about ${P.bench_pct}% typical for this size (${P.ratio}x).`:`Engagement is not published for this profile, so the typical ${P.bench_pct}% for this size is used.`} Followers: ${esc(P.source||"")}, as of ${esc(P.as_of||"")}.</p>
   <h4>Steps to earn more</h4>${st}
   <h4>If the steps are followed (projection)</h4><div class="tbl"><table><tr><th>In</th><th class="r">Followers</th><th class="r">Yearly income, no change</th><th class="r">Yearly income, with steps</th></tr>
   ${P.projection.map(p=>`<tr><td>${p.month?p.month+" months":"Today"}</td><td class="r">${n(p.followers)}</td><td class="r">${money(p.now,1)}</td><td class="r"><b>${money(p.with_steps,1)}</b></td></tr>`).join("")}</table></div>
   <p class="sub">A projection with ${P.assumptions.growth_pct_month}% follower growth a month. Not a promise.</p>
   <h4>What-if simulator</h4><div id="sim"></div></aside>`;
  document.body.appendChild(bk);const close=()=>bk.remove();bk.querySelector(".otp-x").onclick=close;bk.onclick=e=>{if(e.target===bk)close()};document.addEventListener("keydown",function k(e){if(e.key==="Escape"){close();document.removeEventListener("keydown",k)}});
  simulator(bk.querySelector("#sim"),P)}

function simulator(box,P){const v={er_pct:P.er_pct,posts_per_week:P.posts_per_week||4,sponsored_share_pct:RG.meta.assumptions.sponsored_share_pct,growth_pct_month:RG.meta.assumptions.growth_pct_month};
  const sl=(k,l,min,max,step)=>`<label class="slide"><label>${l}<b id="v_${k}"></b></label><input type="range" id="s_${k}" min="${min}" max="${max}" step="${step}" value="${v[k]}"></label>`;
  box.innerHTML=`<p class="sub">Move the sliders to see how monthly income could change over the next 12 months.</p>${sl("er_pct","Engagement rate (%)",0,Math.max(10,Math.ceil(P.er_pct*2)),.1)}${sl("posts_per_week","Posts per week",0,14,1)}${sl("sponsored_share_pct","Paid posts (% of posts)",0,60,1)}${sl("growth_pct_month","Follower growth per month (%)",0,15,.5)}<div id="simOut"></div>`;
  let tm;const run=async()=>{for(const k of Object.keys(v)){v[k]=+box.querySelector("#s_"+k).value;box.querySelector("#v_"+k).textContent=" "+v[k]}
    try{const R=await api("/api/influencer/simulate",{method:"POST",body:{...v,followers:P.followers,category:P.category,country:P.country}});
      const mx=Math.max(...R.months.map(m=>m.high),1);
      box.querySelector("#simOut").innerHTML=`<div class="simbars">${R.months.map(m=>`<div title="Month ${m.month}: ${money(m.mid)} (range ${money(m.low)} to ${money(m.high)})"><i style="height:${Math.max(m.mid/mx*100,2)}%"></i><span>${m.month}</span></div>`).join("")}</div>
       <p><b>Next 12 months: about ${money(R.year_total.mid,1)}</b> <span class="sub">(range ${money(R.year_total.low,1)} to ${money(R.year_total.high,1)}). Bars show income per month. ${esc(R.note)}</span></p>`}catch(e){box.querySelector("#simOut").textContent=e.message}};
  box.querySelectorAll("input[type=range]").forEach(i=>i.oninput=()=>{clearTimeout(tm);tm=setTimeout(run,150)});run()}
