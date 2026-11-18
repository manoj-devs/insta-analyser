"use strict";
/* Reports page (user and admin): choose what goes into the report from a drop-down list, get a visual PDF, and find old reports again. */
async function reportsPage(V){
  const cat=await api("/api/reports/catalog");let picked=new Set(),tab="new";
  const all=cat.groups.flatMap(g=>g.items.map(i=>i.id));
  const fmtSize=b=>b>1048576?(b/1048576).toFixed(1)+" MB":Math.max(1,Math.round(b/1024))+" KB";
  function draw(){
    V.innerHTML=`<div class="rtabs"><button class="btn ${tab==="new"?"p":""}" data-t="new">Generate report</button><button class="btn ${tab==="old"?"p":""}" data-t="old">Previous reports</button></div><div id="rbody"></div>`;
    V.querySelector(".rtabs").onclick=e=>{const b=e.target.closest("[data-t]");if(b){tab=b.dataset.t;draw()}};
    tab==="new"?drawNew():drawOld()}
  function drawNew(){
    const B=V.querySelector("#rbody");
    B.innerHTML=`<div class="glass card" style="max-width:720px"><h3>Build your report</h3>
      <p class="sub">Pick everything you want in it. The report is mostly charts and diagrams, with very little text.</p>
      <label class="f">Report title (optional)<input id="rt" maxlength="80" placeholder="InstaWarehouse report"></label>
      <div class="rdrop"><button type="button" class="btn rdbtn" id="rdb"><span id="rdl"></span><span>▾</span></button>
        <div class="rpanel hidden" id="rpn"><div class="rtools"><button type="button" class="btn sm" id="rall">Select all</button><button type="button" class="btn sm" id="rnone">Clear</button></div>
          ${cat.groups.map(g=>`<div class="rgroup"><b>${esc(g.name)}</b>${g.items.map(i=>`<label class="chk"><input type="checkbox" value="${i.id}"> <span>${esc(i.title)}</span></label>`).join("")}</div>`).join("")}</div></div>
      <div class="chips" id="rchips" style="margin:10px 0"></div><div class="err" id="rerr"></div>
      <button class="btn p" id="rgo">Generate PDF report</button></div><div id="rdone"></div>`;
    const pn=B.querySelector("#rpn"),sync=()=>{B.querySelectorAll("#rpn input").forEach(c=>c.checked=picked.has(c.value));
      B.querySelector("#rdl").textContent=picked.size?picked.size+" of "+all.length+" selected":"Choose what to include";
      B.querySelector("#rchips").innerHTML=[...picked].map(id=>{const t=cat.groups.flatMap(g=>g.items).find(i=>i.id===id);return `<span class="chip">${esc(t.title)}</span>`}).join("")};
    B.querySelector("#rdb").onclick=()=>pn.classList.toggle("hidden");
    B.querySelector("#rpn").onchange=e=>{const c=e.target;if(c.type==="checkbox"){c.checked?picked.add(c.value):picked.delete(c.value);sync()}};
    B.querySelector("#rall").onclick=()=>{all.forEach(i=>picked.add(i));sync()};B.querySelector("#rnone").onclick=()=>{picked.clear();sync()};
    sync();
    B.querySelector("#rgo").onclick=async e=>{B.querySelector("#rerr").textContent="";
      if(!picked.size){B.querySelector("#rerr").textContent="Choose at least one item from the list.";return}
      const btn=e.target;btn.disabled=true;btn.textContent="Building the report…";
      try{const r=await api("/api/reports/generate",{method:"POST",body:{sections:[...picked],title:B.querySelector("#rt").value}});
        toast("Report ready","good");B.querySelector("#rdone").innerHTML=`<div class="glass card" style="max-width:720px;margin-top:14px"><h3>${esc(r.title)}</h3><p class="sub">${r.pages} page${r.pages>1?"s":""} · ${fmtSize(r.bytes)}</p>
          <a class="btn p" href="/api/reports/${r.id}/download" target="_blank" rel="noopener">Open / download PDF</a></div>`}
      catch(x){B.querySelector("#rerr").textContent=x.message}finally{btn.disabled=false;btn.textContent="Generate PDF report"}}}
  async function drawOld(){
    const B=V.querySelector("#rbody");B.innerHTML='<div class="glass card"><p class="sub">Loading…</p></div>';
    let H;try{H=await api("/api/reports/history")}catch(x){B.innerHTML=`<div class="glass card"><p class="err">${esc(x.message)}</p></div>`;return}
    if(!H.length){B.innerHTML='<div class="glass card"><h3>No reports yet</h3><p class="sub">Reports you generate are saved here so you can open them again.</p></div>';return}
    B.innerHTML=`<div class="glass card"><div class="tbl"><table><tr><th>Date</th><th>Title</th><th>Included</th><th class="r">Pages</th><th class="r">Size</th><th></th></tr>
      ${H.map(h=>`<tr><td>${new Date(h.ts*1000).toLocaleString()}</td><td>${esc(h.title)}</td><td class="sub">${esc(h.sections.slice(0,4).join(", "))}${h.sections.length>4?" +"+(h.sections.length-4)+" more":""}</td><td class="r">${h.pages}</td><td class="r">${fmtSize(h.bytes)}</td>
      <td><a class="btn sm p" href="/api/reports/${h.id}/download" target="_blank" rel="noopener">Open</a> <button class="btn sm d" data-del="${h.id}">Delete</button></td></tr>`).join("")}</table></div></div>`;
    B.onclick=async e=>{const b=e.target.closest("[data-del]");if(!b)return;try{await api("/api/reports/"+b.dataset.del,{method:"DELETE"});toast("Deleted","good");drawOld()}catch(x){toast(x.message,"bad")}}}
  draw()}

/* ---------------- TCP link page (admin): the two-laptop TCP connection, live ---------------- */
async function tcpPage(V){
  V.innerHTML=`<div id="tcpbody"></div>`;const B=V.querySelector("#tcpbody");let last="";
  async function load(){let S;try{S=await api("/api/admin/tcp/status",{bg:true})}catch(x){return}
    const host=S.host&&!["0.0.0.0","127.0.0.1"].includes(S.host)?S.host:"<this laptop's IP>";
    const sig=JSON.stringify([S.running,S.connections.map(c=>[c.id,c.last,c.bytes_in]),S.log[0]&&S.log[0].ts]);if(sig===last)return;last=sig;
    B.innerHTML=`<div class="grid eq"><div class="glass card"><h3>TCP link</h3>
      <p class="sub">A plain TCP connection between two laptops, separate from the website. The other laptop connects to this laptop's IP address and port, proves it knows the password, and then both sides send messages.</p>
      <div class="stat"><span>Listening</span><b>${S.running?esc(S.host+":"+S.port):"not running"}</b></div>
      <div class="stat"><span>Password</span><b>${esc(S.password)}</b></div><div class="stat"><span>Connections so far</span><b>${S.total}</b></div>
      ${S.error?`<p class="err">${esc(S.error)}</p>`:""}
      <p class="sub" style="margin-top:10px">On the other laptop, in the project folder, run:</p><pre class="code">py tcp_client.py ${esc(host)} ${S.port||9000}</pre>
      ${["127.0.0.1"].includes(S.host)?'<p class="sub">This server listens on this laptop only (127.0.0.1). Start it with run_network.bat so it listens on the Tailscale IP, then the other laptop can connect.</p>':""}</div>
     <div class="glass card"><h3>Connected laptops</h3>${S.connections.length?`<div class="tbl"><table><tr><th>#</th><th>Name</th><th>From</th><th class="r">Ping</th><th class="r">In / out</th><th></th></tr>
      ${S.connections.map(c=>`<tr><td>${c.id}</td><td>${esc(c.name)}</td><td>${esc(c.peer)}</td><td class="r">${c.rtt_ms==null?"–":c.rtt_ms+" ms"}</td><td class="r">${n(c.bytes_in)} / ${n(c.bytes_out)} B</td>
      <td><button class="btn sm" data-msg="${c.id}">Message</button> <button class="btn sm d" data-drop="${c.id}">Disconnect</button></td></tr>`).join("")}</table></div>`:'<p class="sub">No laptop is connected yet.</p>'}</div></div>
     <div class="glass card" style="margin-top:14px"><h3>Live log</h3>${S.log.length?`<div class="tbl" style="max-height:320px;overflow:auto"><table>${S.log.map(l=>`<tr><td class="sub">${new Date(l.ts*1000).toLocaleTimeString()}</td><td><span class="pill">${esc(l.kind)}</span></td><td>${esc(l.text)}</td></tr>`).join("")}</table></div>`:'<p class="sub">Nothing yet.</p>'}</div>`}
  B.onclick=async e=>{const m=e.target.closest("[data-msg]"),d=e.target.closest("[data-drop]");
    try{if(m){const t=await ask("Message to this laptop","Type a short message","It appears in the terminal on that laptop.");if(t){await api("/api/admin/tcp/send",{method:"POST",body:{session:+m.dataset.msg,text:t}});toast("Sent over TCP","good");last=""}}
      if(d){await api("/api/admin/tcp/disconnect/"+d.dataset.drop,{method:"POST"});toast("Disconnected","good");last=""}}catch(x){toast(x.message,"bad")}};
  await load();timers.push(setInterval(load,2500))}
