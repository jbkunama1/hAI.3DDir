/* Restored controls layered after login-v2 and the original presentation layer. */
(()=>{
"use strict";
const selected=new Set();let selectionMode=false,busy=false,lastIndex=null,dragDepth=0;
function roots(paths){const unique=[...new Set(paths)].filter(Boolean);return unique.filter(path=>!unique.some(parent=>parent!==path&&path.startsWith(parent+"/")));}
const cards=()=>[...$("gr").querySelectorAll(".card[data-path]")];
const toolbar=document.querySelector("#t-files .bar");
function button(id,label,parent=toolbar){const b=document.createElement("button");b.type="button";b.id=id;b.textContent=label;parent.append(b);return b;}
const toggle=button("selectionMode","Auswählen"),newFolder=button("newFolder","Neuer Ordner");
const batch=document.createElement("div");batch.id="batchTools";batch.className="batch-tools";batch.hidden=true;batch.innerHTML='<b id="selectionCount" aria-live="polite"></b>';document.body.append(batch);
const all=button("selectAll","Alle",batch),clear=button("selectNone","Keine",batch),moveButton=button("batchMove","Verschieben",batch),zipButton=button("batchZip","Als ZIP",batch),deleteButton=button("batchDelete","Löschen",batch);
function paint(){
  $("gr").classList.toggle("selecting",selectionMode);toggle.classList.toggle("pri",selectionMode);toggle.textContent=selectionMode?"Auswahl beenden":"Auswählen";toggle.setAttribute("aria-pressed",String(selectionMode));
  for(const card of cards()){const checked=selected.has(card.dataset.path);card.classList.toggle("selected",checked);const input=card.querySelector(".itemSelect");if(input)input.checked=checked;}
  batch.hidden=!selected.size||$("t-files").hidden||$("app").hidden;$("selectionCount").textContent=selected.size+" ausgewählt";
  for(const b of [toggle,all,clear,moveButton,zipButton,deleteButton,newFolder])b.disabled=busy;
}
function decorate(){
  const visible=new Set(cards().map(c=>c.dataset.path));for(const path of selected)if(!visible.has(path))selected.delete(path);
  for(const card of cards()){
    card.draggable=true;card.dataset.dir=String(card.querySelector(".download")?.hidden===true);
    if(card.querySelector(".itemSelect"))continue;
    const input=document.createElement("input");input.type="checkbox";input.className="itemSelect";input.setAttribute("aria-label","Auswählen: "+card.dataset.path);
    input.onchange=()=>{if(busy){paint();return;}selectionMode=true;if(input.checked)selected.add(card.dataset.path);else selected.delete(card.dataset.path);paint();};card.prepend(input);
  }
  paint();
}
const previousFiles=loadFiles;let currentLocation=cwd+"|"+$("q").value;
loadFiles=async()=>{const location=cwd+"|"+$("q").value;if(location!==currentLocation){selected.clear();lastIndex=null;currentLocation=location;}await previousFiles();decorate();};
new MutationObserver(decorate).observe($("gr"),{childList:true});
new MutationObserver(paint).observe($("app"),{attributes:true,attributeFilter:["hidden"]});
toggle.onclick=()=>{selectionMode=!selectionMode;if(!selectionMode)selected.clear();paint();};all.onclick=()=>{selectionMode=true;for(const card of cards())selected.add(card.dataset.path);paint();};clear.onclick=()=>{selected.clear();paint();};
$("gr").addEventListener("click",event=>{
  const card=event.target.closest(".card[data-path]");if(!card)return;
  if(event.target.closest(".itemSelect")){event.stopPropagation();return;}
  if(event.target.closest(".acts"))return;
  if(busy){event.preventDefault();event.stopImmediatePropagation();return;}
  if(!selectionMode&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey)return;
  event.preventDefault();event.stopImmediatePropagation();selectionMode=true;
  const visible=cards(),index=visible.indexOf(card);
  if(event.shiftKey&&lastIndex!==null){for(const item of visible.slice(Math.min(index,lastIndex),Math.max(index,lastIndex)+1))selected.add(item.dataset.path);}
  else if(selected.has(card.dataset.path))selected.delete(card.dataset.path);else selected.add(card.dataset.path);
  lastIndex=index;paint();
},true);
async function refresh(){await loadFiles();if(!$("t-adm").hidden)await loadAdm();}
newFolder.onclick=guard(async()=>{const name=prompt("Name des neuen Ordners");if(name===null||!name.trim())return;if(name.trim().startsWith(".")||/[\\/]/.test(name))throw new Error("Bitte einen sichtbaren Ordnernamen ohne Pfad eingeben.");await api("/mkdir",json("POST",{path:cwd,name:name.trim()}));await refresh();});
function busyState(value){busy=value;paint();}
deleteButton.onclick=guard(async()=>{
  const paths=roots([...selected]);if(!paths.length)return;
  if(!confirm(paths.length+" Element(e) löschen?\n"+paths.join("\n")+"\n"+(CFG.trash_enabled===false?"Papierkorb ist aus: endgültiges Löschen!":"Gelöschtes wird gemäß Papierkorb-Einstellung behandelt.")))return;
  const failed=[];let done=0;busyState(true);
  try{for(const path of paths){try{await api("/delete",json("POST",{path}));selected.delete(path);for(const child of selected)if(child.startsWith(path+"/"))selected.delete(child);done++;}catch(error){failed.push(path+": "+error.message);if(!$("login").hidden)break;}}}
  finally{busyState(false);try{await refresh();}catch(error){failed.push("Aktualisierung: "+error.message);}}
  toast(done+" gelöscht; "+failed.length+" fehlgeschlagen"+(failed.length?"\n"+failed.join("\n"):""));
});
zipButton.onclick=guard(async()=>{
  const paths=roots([...selected]);if(!paths.length)return;
  if(new Set(paths.map(p=>p.split("/").pop())).size!==paths.length)throw new Error("Gleichnamige Elemente aus verschiedenen Ordnern bitte getrennt als ZIP herunterladen.");
  busyState(true);const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),300000);toast("ZIP wird erstellt …");
  try{const response=await fetch("/api/zip",{...json("POST",{paths}),headers:{"Content-Type":"application/json"},credentials:"include",signal:controller.signal});if(!response.ok){const data=await response.json().catch(()=>({}));if(response.status===401)showLogin();throw new Error(data.detail||"ZIP HTTP "+response.status);}const url=URL.createObjectURL(await response.blob()),link=document.createElement("a");link.href=url;link.download="3DDir.zip";document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);toast("ZIP-Download gestartet.");}
  catch(error){if(error.name==="AbortError")throw new Error("ZIP-Erstellung hat zu lange gedauert.");throw error;}
  finally{clearTimeout(timer);busyState(false);}
});
const picker=document.createElement("dialog");picker.id="moveDialog";picker.innerHTML='<h2>Zielordner wählen</h2><p id="movePath"></p><div id="moveFolders" class="f"></div><div class="bar"><button id="moveHere" class="pri" type="button">Hierher verschieben</button><button id="cancelMove" type="button">Abbrechen</button></div>';document.body.append(picker);
let destination="",moving=[];
async function listDest(){const result=await api("/list?path="+encodeURIComponent(destination));destination=result.path;$("movePath").textContent="/"+destination;$("moveFolders").replaceChildren();
  if(destination){const up=button("moveUp","⬆ Hoch",$("moveFolders"));up.onclick=guard(async()=>{destination=destination.split("/").slice(0,-1).join("/");await listDest();});}
  for(const item of result.items.filter(i=>i.dir)){const path=[destination,item.name].filter(Boolean).join("/");if(moving.some(p=>path===p||path.startsWith(p+"/")))continue;const b=document.createElement("button");b.type="button";b.textContent="📁 "+item.name;b.dataset.path=path;b.onclick=guard(async()=>{destination=path;await listDest();});$("moveFolders").append(b);}}
moveButton.onclick=guard(async()=>{moving=roots([...selected]);if(!moving.length)return;destination=cwd;await listDest();picker.showModal();});$("cancelMove").onclick=()=>picker.close();
async function movePaths(paths,to){if(busy)throw new Error("Eine Dateiaktion läuft bereits.");if(paths.some(p=>p===to||to.startsWith(p+"/")))throw new Error("Ein Ordner kann nicht in sich selbst verschoben werden.");if(!confirm(paths.length+" Element(e) nach /"+to+" verschieben?\n"+paths.join("\n")))return;busyState(true);
  try{await api("/move",json("POST",{paths,to}));selected.clear();picker.close();toast("Verschoben.");}
  catch(error){throw new Error("Verschieben fehlgeschlagen. Teiländerungen sind möglich; Quelle und Ziel prüfen. "+error.message);}
  finally{busyState(false);await refresh();}}
$("moveHere").onclick=guard(()=>movePaths(moving,destination));
const trash=document.createElement("section");trash.id="t-trash";trash.hidden=true;trash.innerHTML='<div class="bar"><h2>Papierkorb</h2><button id="emptyTrash" type="button">Papierkorb leeren</button></div><div id="trashRows"></div>';document.querySelector("main").append(trash);
async function loadTrash(){const rows=await api("/trash");$("trashRows").replaceChildren();for(const row of rows){const div=document.createElement("div");div.className="box";div.dataset.origin=row.orig;const label=document.createElement("p");label.textContent=row.name+" · /"+row.orig+" · "+new Date(row.ts*1000).toLocaleString("de-DE");div.append(label);
  for(const[caption,endpoint,kind]of [["Wiederherstellen","/trash/restore","restore"],["Endgültig löschen","/trash/purge","purge"]]){const b=document.createElement("button");b.type="button";b.textContent=caption;b.dataset.action=kind;b.onclick=guard(async()=>{if(kind==="purge"&&!confirm(row.name+" endgültig löschen?"))return;await api(endpoint,json("POST",{id:row.id}));await loadTrash();});div.append(b);}$("trashRows").append(div);}if(!rows.length)$("trashRows").textContent="Der Papierkorb ist leer.";}
$("emptyTrash").onclick=guard(async()=>{if(confirm("Gesamten Papierkorb endgültig leeren?")){await api("/trash/purge",json("POST",{id:""}));await loadTrash();}});
const trashTab=document.createElement("button");trashTab.type="button";trashTab.dataset.t="trash";trashTab.textContent="Papierkorb";document.querySelector("nav").insertBefore(trashTab,document.querySelector('nav [data-t="adm"]'));
for(const b of document.querySelectorAll("nav [data-t]"))b.onclick=guard(async()=>{selected.clear();selectionMode=false;for(const tab of ["files","fil","trash","adm"])$("t-"+tab).hidden=tab!==b.dataset.t;for(const button of document.querySelectorAll("nav [data-t]"))button.classList.toggle("on",button===b);paint();await({files:loadFiles,fil:loadFil,trash:loadTrash,adm:loadAdm})[b.dataset.t]();});
const progress=document.createElement("div");progress.id="uploadProgress";document.body.prepend(progress);const uploadStatus=document.createElement("p");uploadStatus.id="uploadStatus";uploadStatus.setAttribute("role","status");$("gr").before(uploadStatus);
let uploading=false;
async function uploadFiles(items){const files=[...items];if(!files.length)return;if(uploading)throw new Error("Ein Upload läuft bereits.");const existing=new Set(cards().map(c=>c.dataset.path));if(files.some(f=>existing.has([cwd,f.name].filter(Boolean).join("/")))&&!confirm("Dateien gleichen Namens werden überschrieben. Fortfahren?"))return;
  uploading=true;$("ub").disabled=true;const path=cwd;uploadStatus.textContent="Upload wird gestartet …";
  try{await new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest(),body=new FormData();for(const file of files)body.append("files",file);xhr.open("POST","/api/upload?path="+encodeURIComponent(path));xhr.withCredentials=true;xhr.timeout=300000;xhr.upload.onprogress=event=>{if(event.lengthComputable){const percent=Math.round(event.loaded/event.total*100);progress.style.width=percent+"%";uploadStatus.textContent=percent+" % übertragen; Server verarbeitet …";}};xhr.onerror=()=>reject(new Error("Netzwerkfehler beim Upload"));xhr.ontimeout=()=>reject(new Error("Upload-Zeitüberschreitung"));xhr.onload=()=>{if(xhr.status>=200&&xhr.status<300)resolve();else{if(xhr.status===401)showLogin();let detail="Upload HTTP "+xhr.status;try{detail=JSON.parse(xhr.responseText).detail||detail;}catch{}reject(new Error(detail));}};xhr.send(body);});uploadStatus.textContent=files.length+" Datei(en) hochgeladen.";await refresh();}
  catch(error){uploadStatus.textContent="Upload fehlgeschlagen: "+error.message;throw error;}
  finally{uploading=false;$("ub").disabled=false;$("fi").value="";progress.style.width="0";}}
$("fi").onchange=guard(()=>uploadFiles($("fi").files));
$("gr").addEventListener("dragstart",event=>{const card=event.target.closest(".card[data-path]");if(!card||busy)return;const paths=roots(selected.has(card.dataset.path)?[...selected]:[card.dataset.path]);event.dataTransfer.setData("application/x-hai-paths",JSON.stringify(paths));event.dataTransfer.effectAllowed="move";});
const fileSection=$("t-files");fileSection.addEventListener("dragenter",event=>{if(event.dataTransfer.types.includes("Files")){event.preventDefault();dragDepth++;$("gr").classList.add("drop");}});fileSection.addEventListener("dragleave",()=>{dragDepth=Math.max(0,dragDepth-1);if(!dragDepth)$("gr").classList.remove("drop");});fileSection.addEventListener("dragover",event=>{if(event.dataTransfer.types.includes("Files")||event.dataTransfer.types.includes("application/x-hai-paths"))event.preventDefault();});
fileSection.addEventListener("drop",guard(async event=>{dragDepth=0;$("gr").classList.remove("drop");if(event.dataTransfer.files.length){await uploadFiles(event.dataTransfer.files);return;}const raw=event.dataTransfer.getData("application/x-hai-paths");if(!raw)return;const paths=JSON.parse(raw);if(!Array.isArray(paths)||!paths.length||paths.some(p=>typeof p!=="string"||!p))throw new Error("Ungültige Drag-and-drop-Daten");const card=event.target.closest(".card[data-path]");if(card&&card.dataset.dir!=="true")throw new Error("Zum Verschieben bitte auf einen Ordner ziehen.");await movePaths(roots(paths),card?card.dataset.path:cwd);}));
const filBar=document.querySelector("#t-fil .bar"),exportJSON=document.createElement("a"),importInput=document.createElement("input"),replaceLabel=document.createElement("label"),replaceInput=document.createElement("input");exportJSON.textContent="JSON exportieren";exportJSON.href="/api/filaments/export?fmt=json";importInput.id="filamentImport";importInput.type="file";importInput.accept=".csv,.json";importInput.hidden=true;replaceInput.id="replaceFilaments";replaceInput.type="checkbox";replaceLabel.append(replaceInput," Bestehende Rollen beim Import ersetzen");filBar.append(exportJSON,importInput,replaceLabel);button("importFilaments","Import CSV/JSON",filBar).onclick=()=>importInput.click();
importInput.onchange=guard(async()=>{const file=importInput.files[0];if(!file)return;if(replaceInput.checked&&!confirm("Alle vorhandenen Filamentrollen durch den Import ersetzen?")){importInput.value="";return;}const body=new FormData();body.append("file",file);try{const result=await api("/filaments/import?replace="+(replaceInput.checked?1:0),{method:"POST",body});await loadFil();toast(result.imported+" Rollen importiert.");}finally{importInput.value="";}});
let currentSort={field:"brand",dir:"asc"},currentGroup="none",currentView="list";
const materialsSet=new Set(),brandsSet=new Set();

// Delete Filament Funktion earlier definieren
window.deleteFilament=async function(id){
  const filament=rolls.find(r=>r.id===id);
  if(filament&&confirm("Filamentrolle "+filament.brand+" "+filament.material+" löschen?")){
    await api("/filaments/"+encodeURIComponent(id),{method:"DELETE"});
    await loadFil();
  }
};

const previousFil=loadFil;loadFil=async()=>{
  await previousFil();
  
  // Prüfen ob Elemente existieren, bevor wir sie manipulieren
  const materials=$("#materials"),brands=$("#brands");
  if(!materials||!brands) return;
  
  materials.innerHTML="";
  brands.innerHTML="";
  
  materialsSet.add("");materialsSet.forEach(mat=>{
    const option=document.createElement("option");
    option.value=mat;
    option.textContent=mat||"Alle Materialien";
    materials.appendChild(option);
  });
  
  brandsSet.add("");brandsSet.forEach(brand=>{
    const option=document.createElement("option");
    option.value=brand;
    option.textContent=brand||"Alle Marken";
    brands.appendChild(option);
  });
  const q=$("fq").value.toLowerCase();
  const materialFilter=$("#fm")?.value?.toLowerCase()||"";
  const brandFilter=$("#fb")?.value?.toLowerCase()||"";
  
  rolls.forEach(r=>{
    materialsSet.add(r.material?.toLowerCase()||"");
    brandsSet.add(r.brand?.toLowerCase()||"");
  });
  
  const filtered=rolls.filter(r=>{
    const searchText=[r.brand,r.material,r.color_name,r.barcode].join(" ").toLowerCase();
    const searchMatch=searchText.includes(q);
    const materialMatch=!materialFilter||r.material?.toLowerCase().includes(materialFilter);
    const brandMatch=!brandFilter||r.brand?.toLowerCase().includes(brandFilter);
    return searchMatch&&materialMatch&&brandMatch;
  });
  
  const sorted=filtered.sort((a,b)=>{
    let aValue=a[currentSort.field]||"",bValue=b[currentSort.field]||"";
    if(currentSort.field==="weight_remaining"||currentSort.field==="weight_total"){
      aValue=Number(aValue)||0;
      bValue=Number(bValue)||0;
    }
    if(aValue<bValue)return currentSort.dir==="asc"?-1:1;
    if(aValue>bValue)return currentSort.dir==="asc"?1:-1;
    return 0;
  });
  
  renderFilaments(sorted);
};
function renderFilaments(filaments){
  const container=$("#filamentContent");
  const viewMode=$("#viewMode")?.value||"list";
  currentView=viewMode;
  container.className=viewMode==="grid"?"grid":viewMode==="columns"?"view-mode-3":"";
  
  if(viewMode==="list"){
    renderListView(filaments);
  }else if(viewMode==="columns"){
    renderColumnsView(filaments);
  }else{
    renderGridView(filaments);
  }
}
function renderListView(filaments){
  const table=$("#filTable");
  const tbody=$("#ft");
  table.style.display="table";
  tbody.innerHTML="";
  
  if(currentGroup==="material"){
    const groups={};
    filaments.forEach(f=>{
      const group=f.material||(f.brand||"Unbekannt");
      if(!groups[group])groups[group]=[];
      groups[group].push(f);
    });
    Object.entries(groups).forEach(([group,items])=>{
      const header=createGroupHeader(group,items.length);
      tbody.appendChild(header);
      items.forEach(item=>tbody.appendChild(createFilamentRow(item)));
    });
  }else if(currentGroup==="brand"){
    const groups={};
    filaments.forEach(f=>{
      const group=f.brand||(f.material||"Unbekannt");
      if(!groups[group])groups[group]=[];
      groups[group].push(f);
    });
    Object.entries(groups).forEach(([group,items])=>{
      const header=createGroupHeader(group,items.length);
      tbody.appendChild(header);
      items.forEach(item=>tbody.appendChild(createFilamentRow(item)));
    });
  }else{
    filaments.forEach(item=>tbody.appendChild(createFilamentRow(item)));
  }
}
function renderColumnsView(filaments){
  const table=$("#filTable");
  table.style.display="none";
  const container=$("#filamentContent");
  container.innerHTML="";
  
  const columns=3;
  const columnsArray=Array.from({length:columns},()=>[]);
  
  filaments.forEach((item,index)=>{
    columnsArray[index%columns].push(item);
  });
  
  columnsArray.forEach(column=>{
    const columnDiv=document.createElement("div");
    columnDiv.className="filament-column";
    column.forEach(item=>columnDiv.appendChild(createFilamentItem(item)));
    container.appendChild(columnDiv);
  });
}
function renderGridView(filaments){
  const table=$("#filTable");
  table.style.display="none";
  const container=$("#filamentContent");
  container.innerHTML="";
  
  filaments.forEach(item=>{
    const gridItem=createFilamentGridItem(item);
    container.appendChild(gridItem);
  });
}
function createGroupHeader(name,count){
  const header=document.createElement("tr");
  header.className="group-header-row";
  header.innerHTML=`<td colspan="5"><span>${name} (${count})</span></td>`;
  return header;
}
function createFilamentRow(filament){
  const tr=document.createElement("tr");
  tr.dataset.id=filament.id;
  tr.innerHTML=`
    <td>${filament.brand||""}</td>
    <td>${filament.material||""}</td>
    <td><span class="spool" style="--c:${filament.color_hex||"#888888"}"></span> ${filament.color_name||""}</td>
    <td>${filament.weight_remaining||0}/${filament.weight_total||0}g</td>
    <td><button data-delete="${filament.id}">Löschen</button></td>
  `;
  
  // Event-Handler nach dem DOM-Erstellung zuweisen
  const deleteBtn=tr.querySelector("[data-delete]");
  if(deleteBtn) deleteBtn.onclick=guard(async()=>window.deleteFilament(filament.id));
  
  return tr;
}
function createFilamentItem(filament){
  const div=document.createElement("div");
  div.className="filament-item";
  div.innerHTML=`
    <div style="display:flex;align-items:center;gap:12px;">
      <span class="spool" style="--c:${filament.color_hex||"#888888"}"></span>
      <div>
        <div>${filament.brand||""} ${filament.material||""}</div>
        <div style="font-size:12px;color:var(--m)">${filament.color_name||""}</div>
      </div>
    </div>
    <div style="font-size:12px;margin-top:8px">${filament.weight_remaining||0}/${filament.weight_total||0}g</div>
    <div style="margin-top:8px"><button data-delete="${filament.id}" style="font-size:12px">Löschen</button></div>
  `;
  
  // Event-Handler nach dem DOM-Erstellung zuweisen
  const deleteBtn=div.querySelector("[data-delete]");
  if(deleteBtn) deleteBtn.onclick=guard(async()=>window.deleteFilament(filament.id));
  
  return div;
}
function createFilamentGridItem(filament){
  const div=document.createElement("div");
  div.className="filament-grid-item";
  div.innerHTML=`
    <div class="header">
      <span class="spool" style="--c:${filament.color_hex||"#888888"}"></span>
      <div class="info">
        <div class="brand">${filament.brand||""}</div>
        <div class="material">${filament.material||""}</div>
        <div class="color">${filament.color_name||""}</div>
      </div>
    </div>
    <div class="weight">${filament.weight_remaining||0}/${filament.weight_total||0}g</div>
    <div class="actions">
      <button data-delete="${filament.id}" style="font-size:12px">Löschen</button>
    </div>
  `;
  
  // Event-Handler nach dem DOM-Erstellung zuweisen
  const deleteBtn=div.querySelector("[data-delete]");
  if(deleteBtn) deleteBtn.onclick=guard(async()=>window.deleteFilament(filament.id));
  
  return div;
}
$("fq").addEventListener("input",guard(()=>loadFil()));
$("#fm")?.addEventListener("input",guard(()=>loadFil()));
$("#fb")?.addEventListener("input",guard(()=>loadFil()));
$("#viewMode")?.addEventListener("change",guard(e=>{
  currentView=e.target.value;
  loadFil();
}));

// Sortierung für Table-Header
document.querySelectorAll("#filTable th[data-sort]").forEach(th=>{ 
  th.style.cursor="pointer";
  th.addEventListener("click",guard((e)=>{
    const field=e.currentTarget.dataset.sort;
    if(currentSort.field===field){
      currentSort.dir=currentSort.dir==="asc"?"desc":"asc";
    }else{
      currentSort.field=field;
      currentSort.dir="asc";
    }
    // Sortier-Icon aktualisieren
    e.currentTarget.querySelector(".sort").textContent=currentSort.dir==="asc"?"▲":"▼";
    loadFil();
  }));
});
window.addEventListener("keydown",event=>{if(event.key==="Escape"&&!document.querySelector("dialog[open]")){selected.clear();selectionMode=false;paint();}});
document.documentElement.dataset.controls="restored-v1";decorate();
})();
