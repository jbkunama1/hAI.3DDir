"use strict";
const $=id=>document.getElementById(id.replace(/^#/,""));
const CFG={}; let cwd="",editing=null,rolls=[];
const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function loginStatus(text,error=false){$("loginStatus").textContent=text;$("loginStatus").dataset.error=String(error);}
function toast(text){$("toast").textContent=text;$("toast").hidden=false;}
function showLogin(){ $("login").hidden=false;$("app").hidden=true;$("mk").textContent="";$("mk").hidden=true; }
async function api(path,options={}){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000),headers=new Headers(options.headers);
  if(typeof options.body==="string")headers.set("Content-Type","application/json");
  try{
    const response=await fetch("/api"+path,{...options,headers,credentials:"include",cache:"no-store",signal:controller.signal});
    const data=await response.json().catch(()=>({}));
    if(!response.ok){if(response.status===401&&path!=="/login")showLogin();throw new Error(typeof data.detail==="string"?data.detail:"HTTP "+response.status);}
    return data;
  }catch(error){if(error.name==="AbortError")throw new Error("Keine Serverantwort innerhalb von 12 Sekunden.");throw error;}
  finally{clearTimeout(timer);}
}
const json=(method,body)=>({method,body:JSON.stringify(body)});
const guard=fn=>async event=>{event?.preventDefault();try{await fn(event);}catch(error){toast(error.message);}};
function theme(value){document.documentElement.dataset.theme=value;$("th").value=value;try{localStorage.setItem("hai-theme",value);}catch{}}
async function start(){
  $("login").hidden=true;$("app").hidden=false;
  try{Object.assign(CFG,await api("/config"));$("title").textContent=CFG.title;document.title=CFG.title;let saved;try{saved=localStorage.getItem("hai-theme");}catch{}theme(saved||CFG.default_theme||"modern");}
  catch(error){toast("Angemeldet; Konfiguration: "+error.message);}
  const results=await Promise.allSettled([loadFiles(),loadFil(),loadAdm(),loadMcp()]);
  for(const result of results)if(result.status==="rejected")toast("Angemeldet; Ladefehler: "+result.reason.message);
}
// Bind login before any optional application features are initialized.
$("lf").addEventListener("submit",async event=>{
  event.preventDefault();const button=$("loginButton");if(button.disabled)return;
  button.disabled=true;button.textContent="Anmeldung läuft …";loginStatus("Passwort wird geprüft …");
  try{
    const result=await api("/login",json("POST",{password:$("pw").value}));
    if(result.auth!==true)throw new Error("Server hat die Anmeldung nicht bestätigt.");
    loginStatus("Session wird geprüft …");
    if((await api("/me")).auth!==true)throw new Error("Passwort akzeptiert, aber Session-Cookie fehlt. Cookie-Einstellungen prüfen.");
    $("pw").value="";loginStatus("Angemeldet.");await start();
  }catch(error){showLogin();loginStatus(error.message,true);}
  finally{button.disabled=false;button.textContent="Anmelden";}
});
$("loginButton").disabled=false;loginStatus("Bereit zur Anmeldung.");
$("lo").onclick=guard(async()=>{await api("/logout",{method:"POST"});showLogin();loginStatus("Abgemeldet.");});
$("th").onchange=()=>theme($("th").value);
for(const button of document.querySelectorAll("nav [data-t]"))button.onclick=()=>{for(const tab of ["files","fil","adm"])$("t-"+tab).hidden=tab!==button.dataset.t;};
const fmt=n=>n>1e9?(n/1e9).toFixed(1)+" GB":n>1e6?(n/1e6).toFixed(1)+" MB":n>1e3?(n/1e3).toFixed(1)+" KB":n+" B";
async function loadFiles(){
  const q=$("q").value.trim(),result=q.length>=2?{items:await api("/search?q="+encodeURIComponent(q))}:await api("/list?path="+encodeURIComponent(cwd));
  $("cwd").textContent="/"+cwd;$("gr").innerHTML="";
  let items=result.items.slice();const sort=CFG.sort_by||"name",sign=CFG.sort_order==="desc"?-1:1;
  items.sort((a,b)=>Number(b.dir)-Number(a.dir)||sign*(sort==="size"?a.size-b.size:sort==="date"?a.mtime-b.mtime:a.name.localeCompare(b.name)));
  for(const item of items){
    const path=item.path??[cwd,item.name].filter(Boolean).join("/"),card=document.createElement("div");card.className="card";
    card.innerHTML='<button type="button">'+(item.dir?"📁 ":"📄 ")+esc(item.name)+"</button><p>"+(item.dir?"":fmt(item.size))+'</p><div class="preview"></div>';$("gr").append(card);
    card.querySelector("button").onclick=guard(async()=>{if(item.dir){cwd=path;$("q").value="";await loadFiles();}else location.href="/api/file?dl=1&path="+encodeURIComponent(path);});
    if(!item.dir&&CFG.file_view!=="icons"&&/\.(3mf|gcode|gco)$/i.test(path))api("/slicer?path="+encodeURIComponent(path)).then(info=>{
      const target=card.querySelector(".preview");target.textContent=[info.data.time_s?Math.round(info.data.time_s/60)+" min":"",info.data.grams?info.data.grams+" g":""].filter(Boolean).join(" · ");
      if(info.image){const image=document.createElement("img");image.alt="Slicer-Vorschau";image.loading="lazy";image.src="/api/slicer/image?path="+encodeURIComponent(path);target.append(image);}
    }).catch(()=>{});
  }
}
$("up").onclick=guard(async()=>{cwd=cwd.split("/").slice(0,-1).join("/");$("q").value="";await loadFiles();});
let searchTimer;$("q").oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>loadFiles().catch(e=>toast(e.message)),250);};
$("ub").onclick=()=>$("fi").click();$("fi").onchange=guard(async()=>{const body=new FormData();for(const file of $("fi").files)body.append("files",file);await api("/upload?path="+encodeURIComponent(cwd),{method:"POST",body});$("fi").value="";await loadFiles();toast("Hochgeladen.");});
const fields={brand:"Marke",material:"Material",color_name:"Farbname",color_hex:"Farbe (#RRGGBB)",weight_total:"Gesamtgewicht (g)",weight_remaining:"Restgewicht (g)",barcode:"Barcode",price_per_kg:"Preis pro kg",purchase_date:"Anschaffungsdatum",notes:"Notizen"};
$("filamentFields").innerHTML=Object.entries(fields).map(([key,label])=>"<label>"+label+'<input id="f_'+key+'" '+(["weight_total","weight_remaining","price_per_kg"].includes(key)?'type="number" min="0" step="any"':key==="purchase_date"?'type="date"':"")+"></label>").join("");
function edit(row=null){editing=row?.id??null;for(const key of Object.keys(fields))$("f_"+key).value=row?.[key]??(key==="color_hex"?"#888888":"");$("fm").showModal();}
async function loadFil(){
  rolls=await api("/filaments");const q=$("fq").value.toLowerCase();$("ft").innerHTML="";
  for(const row of rolls.filter(r=>[r.brand,r.material,r.color_name,r.barcode].join(" ").toLowerCase().includes(q))){
    const tr=document.createElement("tr");tr.innerHTML="<td>"+esc(row.brand)+"</td><td>"+esc(row.material)+"</td><td>"+esc(row.color_name)+"</td><td>"+esc(row.weight_remaining)+"/"+esc(row.weight_total)+' g</td><td><button type="button">Bearbeiten</button></td>';$("ft").append(tr);tr.querySelector("button").onclick=()=>edit(row);
  }
}
$("fa").onclick=()=>edit();$("fx").onclick=()=>$("fm").close();$("fq").oninput=guard(loadFil);
$("ff").onsubmit=guard(async()=>{const body={};for(const key of Object.keys(fields))body[key]=$("f_"+key).value;await api("/filaments"+(editing?"/"+encodeURIComponent(editing):""),json(editing?"PUT":"POST",body));$("fm").close();await loadFil();});
const settingFields={a_ti:"title",a_th:"default_theme",a_sb:"sort_by",a_so:"sort_order",a_view:"file_view",a_mb:"max_upload_mb",a_ext:"allowed_ext",a_tr:"trash_enabled",a_td:"trash_days",a_me:"mcp_enabled"};
async function loadAdm(){const[s,t]=await Promise.all([api("/settings"),api("/stats")]);Object.assign(CFG,s);for(const[id,key]of Object.entries(settingFields))$(id)[$(id).type==="checkbox"?"checked":"value"]=s[key];$("as").textContent=t.files+" Dateien · "+fmt(t.bytes)+" belegt · "+fmt(t.free)+" frei · "+t.filaments+" Rollen";}
if(!$("sf").querySelector('[type="submit"]')){const save=document.createElement("button");save.type="submit";save.className="pri";save.textContent="Speichern";$("sf").append(save);}
$("sf").onsubmit=guard(async()=>{const body={};for(const[id,key]of Object.entries(settingFields)){const el=$(id);body[key]=el.type==="checkbox"?el.checked:el.type==="number"?Number(el.value):el.value;}await api("/settings",json("PUT",body));Object.assign(CFG,body);await loadFiles();toast("Gespeichert.");});
$("pf").onsubmit=guard(async()=>{await api("/password",json("POST",{password:$("a_pw").value}));$("a_pw").value="";await api("/logout",{method:"POST"});showLogin();loginStatus("Passwort geändert; erneut anmelden.");});
if(!$("cc")){const clear=document.createElement("button");clear.id="cc";clear.type="button";clear.textContent="Cache leeren";$("t-adm").append(clear);}
$("cc").onclick=guard(async()=>{await api("/cache",{method:"DELETE"});toast("Cache geleert.");});
$("backupRestore").onclick=()=>$("backupFile").click();$("backupFile").onchange=guard(async()=>{if(!$("backupFile").files[0]||!confirm("Backup einspielen? Vorhandene Daten werden überschrieben."))return;const body=new FormData();body.append("file",$("backupFile").files[0]);await api("/backup/restore",{method:"POST",body});showLogin();loginStatus("Backup eingespielt; erneut anmelden.");});
async function loadMcp(){const result=await api("/mcp");$("mt").innerHTML="";for(const token of result.tokens){const div=document.createElement("div");div.textContent=token.name+" · "+(token.ro?"nur lesen":"Vollzugriff")+" ";const button=document.createElement("button");button.type="button";button.textContent="Widerrufen";button.onclick=guard(async()=>{await api("/mcp/tokens/"+encodeURIComponent(token.id),{method:"DELETE"});await loadMcp();});div.append(button);$("mt").append(div);}}
$("mf").onsubmit=guard(async()=>{const result=await api("/mcp/tokens",json("POST",{name:$("mn").value,ro:$("mr").checked}));$("mk").hidden=false;$("mk").textContent="Jetzt sicher kopieren (einmalig): "+result.token;await loadMcp();});
window.addEventListener("error",()=>{if(!$("login").hidden)loginStatus("Oberflächenfehler. Bitte Build-Kennung und Browserkonsole prüfen.",true);});
fetch("/build.json",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(build=>{if(build?.revision)$("build").textContent="UI login-v2 · "+build.revision.slice(0,12);}).catch(()=>{});
(async()=>{try{if((await api("/me")).auth)await start();}catch(error){loginStatus("Serverprüfung fehlgeschlagen: "+error.message,true);}})();
