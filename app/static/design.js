/* Optional presentation layer. Login-v2 and backend authentication remain unchanged. */
(()=>{
"use strict";
const THEMES={modern:{name:"Modern",icons:["📁","🧊","📄"]},nacht:{name:"Nacht",icons:["📁","🧊","📄"]},bunt:{name:"Bunt",icons:["🌈","🦄","🎈"]},werkstatt:{name:"Werkstatt",icons:["🧰","⚙️","📎"]},galaxie:{name:"Galaxie",icons:["🪐","🛸","⭐"]}};
const optionHTML=Object.entries(THEMES).map(([key,value])=>'<option value="'+key+'">'+value.name+'</option>').join("");
$("th").innerHTML=optionHTML;$("a_th").innerHTML=optionHTML;
const oldTheme=theme;
theme=value=>{oldTheme(THEMES[value]?value:"modern");for(const icon of document.querySelectorAll("[data-kind]"))icon.textContent=THEMES[document.documentElement.dataset.theme].icons[Number(icon.dataset.kind)];};
let saved;try{saved=localStorage.getItem("hai-theme");}catch{}theme(saved||CFG.default_theme||"modern");
for(const id of ["title"]){$(id).classList.add("logo");}
const loginHeading=document.querySelector("#login h1");loginHeading.classList.add("logo");loginHeading.innerHTML='hAI.<b>3DDir</b>';
const titleObserver=new MutationObserver(()=>{const value=$("title").textContent;if(value==="hAI.3DDir"){titleObserver.disconnect();$("title").innerHTML='hAI.<b>3DDir</b>';}});titleObserver.observe($("title"),{childList:true});if($("title").textContent==="hAI.3DDir")$("title").innerHTML='hAI.<b>3DDir</b>';
const crumbs=document.createElement("div");crumbs.id="breadcrumbs";crumbs.className="crumbs";$("cwd").before(crumbs);$("cwd").hidden=true;
const viewer=document.createElement("dialog");viewer.id="viewer";viewer.innerHTML='<div class="bar"><b id="viewerTitle"></b><span id="viewerInfo" role="status"></span><button id="viewerClose" type="button">Schließen</button></div><div id="viewerCanvas"></div>';document.body.append(viewer);
let modelModule;
const models=()=>modelModule||(modelModule=import("/viewer.mjs?v=restore-v1").catch(error=>{modelModule=null;throw error;}));
let stopViewer=()=>{},viewGeneration=0;
async function openViewer(path,name){
  const generation=++viewGeneration;stopViewer();$("viewerTitle").textContent=name;$("viewerInfo").textContent="Lade 3D-Modell …";$("viewerCanvas").replaceChildren();if(!viewer.open)viewer.showModal();
  try{const module=await models();if(generation!==viewGeneration)return;const close=await module.showModel(path,$("viewerCanvas"),$("viewerInfo"));if(generation!==viewGeneration){close();return;}stopViewer=close;}
  catch(error){if(generation===viewGeneration)$("viewerInfo").textContent="Vorschau nicht verfügbar: "+error.message;}
}
$("viewerClose").onclick=()=>viewer.close();viewer.addEventListener("close",()=>{viewGeneration++;stopViewer();stopViewer=()=>{};});
const is3d=name=>/\.(stl|obj|3mf)$/i.test(name);
let renderGeneration=0,thumbnailQueue=Promise.resolve();
loadFiles=async()=>{
  const generation=++renderGeneration,q=$("q").value.trim();
  const result=q.length>=2?{items:await api("/search?q="+encodeURIComponent(q))}:await api("/list?path="+encodeURIComponent(cwd));
  if(generation!==renderGeneration)return;
  crumbs.replaceChildren();const parts=cwd.split("/").filter(Boolean);
  for(let index=-1;index<parts.length;index++){const button=document.createElement("button");button.textContent=index<0?"Share":parts[index];button.onclick=guard(async()=>{cwd=parts.slice(0,index+1).join("/");$("q").value="";await loadFiles();});crumbs.append(button);if(index<parts.length-1)crumbs.append(" / ");}
  if(q.length>=2)crumbs.append(" · Suchergebnisse");
  const sort=CFG.sort_by||"name",sign=CFG.sort_order==="desc"?-1:1;
  const items=result.items.slice().sort((a,b)=>Number(b.dir)-Number(a.dir)||sign*(sort==="size"?a.size-b.size:sort==="date"?a.mtime-b.mtime:a.name.localeCompare(b.name)));
  $("gr").replaceChildren();
  for(const item of items){
    const path=item.path??[cwd,item.name].filter(Boolean).join("/"),kind=item.dir?0:is3d(item.name)?1:2;
    const card=document.createElement("article");card.className="card";card.dataset.path=path;
    card.innerHTML='<button class="open" type="button"><span class="ic" data-kind="'+kind+'">'+THEMES[document.documentElement.dataset.theme||"modern"].icons[kind]+'</span><span class="nm">'+esc(item.name)+'</span></button><div class="sz">'+(item.dir?"Ordner":fmt(item.size))+'</div><div class="preview"></div><div class="acts"><button class="download" type="button">⬇</button><button class="rename" type="button">✎</button><button class="remove" type="button">✕</button></div>';
    $("gr").append(card);
    const download=()=>{location.href="/api/file?dl=1&path="+encodeURIComponent(path);};
    card.querySelector(".open").onclick=guard(async()=>{if(item.dir){cwd=path;$("q").value="";await loadFiles();}else if(is3d(item.name))await openViewer(path,item.name);else download();});
    card.querySelector(".download").hidden=item.dir;card.querySelector(".download").title="Herunterladen";card.querySelector(".download").onclick=download;
    card.querySelector(".rename").title="Umbenennen";card.querySelector(".rename").onclick=guard(async()=>{const name=prompt("Neuer Name",item.name);if(name&&name!==item.name){await api("/rename",json("POST",{path,name}));await loadFiles();}});
    card.querySelector(".remove").title="Löschen";card.querySelector(".remove").onclick=guard(async()=>{if(confirm(item.name+" löschen?")){await api("/delete",json("POST",{path}));await loadFiles();}});
    const mode=CFG.file_view||"icons";
    if(!item.dir&&mode==="thumbs"&&is3d(item.name)&&Number(CFG.thumb_max_mb??20)>0&&item.size<=Number(CFG.thumb_max_mb??20)*1048576){
      thumbnailQueue=thumbnailQueue.catch(()=>{}).then(async()=>{if(!card.isConnected)return;try{const module=await models();const url=await module.thumbnail(path,item.mtime,item.size);if(!card.isConnected)return;const image=document.createElement("img");image.alt="3D-Vorschau "+item.name;image.src=url;card.querySelector(".ic").replaceChildren(image);card.querySelector(".ic").removeAttribute("data-kind");}catch{}});
    }else if(!item.dir&&mode==="slicer"&&/\.(3mf|gcode|gco)$/i.test(item.name)){
      api("/slicer?path="+encodeURIComponent(path)).then(info=>{if(!card.isConnected)return;const target=card.querySelector(".preview");target.textContent=[info.data.time_s?Math.round(info.data.time_s/60)+" min":"",info.data.grams?info.data.grams+" g":""].filter(Boolean).join(" · ");if(info.image){const image=document.createElement("img");image.alt="Slicer-Vorschau";image.src="/api/slicer/image?path="+encodeURIComponent(path);target.append(image);}}).catch(()=>{});
    }
  }
  if(!items.length){const empty=document.createElement("p");empty.className="sz";empty.textContent="Nichts gefunden. Dateien hierher ziehen oder Hochladen wählen.";$("gr").append(empty);}
};
// Reuse the existing form/edit handlers and add the original visual spool indicators.
const oldFil=loadFil;
loadFil=async()=>{await oldFil();
  const q=$("fq").value.toLowerCase(),filtered=rolls.filter(r=>[r.brand,r.material,r.color_name,r.barcode].join(" ").toLowerCase().includes(q));
  
  if(currentView==="list"){
    const table=$("#filTable");
    [...table.rows].forEach((tr,index)=>{
      if(index===0)return;
      const row=filtered[index-1];
      if(!row)return;
      const cell=tr.insertCell(0),spool=document.createElement("span");
      spool.className="spool";spool.title=row.color_name||"Filamentfarbe";spool.style.setProperty("--c",/^#[0-9a-f]{6}$/i.test(row.color_hex)?row.color_hex:"#888888");
      cell.append(spool);
      if(row.image){const image=document.createElement("img");image.className="roll-photo";image.alt="Rollenfoto";image.loading="lazy";image.src="/api/filaments/"+encodeURIComponent(row.id)+"/image?v="+encodeURIComponent(row.img_ts||0);cell.append(image);}
      const meter=document.createElement("div"),bar=document.createElement("i");meter.className="meter";bar.style.width=(row.weight_total?Math.max(0,Math.min(100,row.weight_remaining/row.weight_total*100)):0)+"%";meter.append(bar);tr.cells[4].prepend(meter);
    });
  }
};
const heading=document.createElement("th");heading.setAttribute("aria-label","Rollenfarbe");document.querySelector("#t-fil thead tr").prepend(heading);
const thumbLabel=document.createElement("label");thumbLabel.textContent="3D-Thumbnails bis Dateigröße (MB; 0 = aus)";const thumbInput=document.createElement("input");thumbInput.id="a_tm";thumbInput.type="number";thumbInput.min="0";thumbLabel.append(thumbInput);$("a_view").closest("label").after(thumbLabel);settingFields.a_tm="thumb_max_mb";$("a_view").querySelector('[value="thumbs"]').textContent="3D-Thumbnails";
const oldAdmin=loadAdm;
loadAdm=async()=>{await oldAdmin();const stats=await api("/stats");$("as").className="st";$("as").innerHTML=[["Dateien",stats.files],["Belegt",fmt(stats.bytes)],["Frei",fmt(stats.free)],["Papierkorb",stats.trash],["Filamente",stats.filaments]].map(([label,value])=>"<div>"+label+"<b>"+esc(value)+"</b></div>").join("");
  
  const filVm=$("#fil_vm"),filGp=$("#fil_gp"),filSort=$("#fil_sort"),filGc=$("#fil_gc");
  if(filVm){filVm.value=CFG.filament_view_mode||"list";}
  if(filGp){filGp.value=CFG.filament_group||"none";}
  if(filSort){filSort.value=CFG.filament_sort||"brand";}
  if(filGc){filGc.value=CFG.filament_grid_columns||4;}
  
  if(CFG.filament_view_mode)currentView=CFG.filament_view_mode;
  if(CFG.filament_group)currentGroup=CFG.filament_group;
  if(CFG.filament_sort)currentSort={field:CFG.filament_sort,dir:"asc"};
  
  document.getElementById("ff2")?.addEventListener("submit",guard(async(e)=>{
    e.preventDefault();
    await api("/settings",json("POST",{
      filament_view_mode:filVm.value,
      filament_group:filGp.value,
      filament_sort:filSort.value,
      filament_grid_columns:Number(filGc.value)
    }));
    toast("Filament-Einstellungen gespeichert.");
  }));
for(const button of document.querySelectorAll("nav [data-t]")){const handler=button.onclick;button.onclick=async event=>{for(const item of document.querySelectorAll("nav [data-t]"))item.classList.toggle("on",item===button);await handler(event);};}
document.documentElement.dataset.design="restored-v1";
if(!$("app").hidden)Promise.allSettled([loadFiles(),loadFil(),loadAdm()]);
})();
