// Three.js is imported only when an optional model preview is requested.
import * as T from "three";
import {OrbitControls} from "three/addons/controls/OrbitControls.js";
import {STLLoader} from "three/addons/loaders/STLLoader.js";
import {OBJLoader} from "three/addons/loaders/OBJLoader.js";
import {ThreeMFLoader} from "three/addons/loaders/3MFLoader.js";

async function model(path){
  const response=await fetch("/api/file?path="+encodeURIComponent(path),{credentials:"include"});
  if(!response.ok)throw new Error("Datei HTTP "+response.status);
  if(Number(response.headers.get("Content-Length"))>300*1048576)throw new Error("Modell ist größer als 300 MB");
  const buffer=await response.arrayBuffer(),extension=path.split(".").pop().toLowerCase();
  if(buffer.byteLength>300*1048576)throw new Error("Modell ist zu groß");
  let object;
  if(extension==="stl")object=new T.Mesh(new STLLoader().parse(buffer),new T.MeshStandardMaterial({color:0x3d8fa5,roughness:.55,metalness:.1}));
  else if(extension==="obj"){object=new OBJLoader().parse(new TextDecoder().decode(buffer));object.traverse(node=>{if(node.isMesh){if(node.material?.dispose)node.material.dispose();node.material=new T.MeshStandardMaterial({color:0x3d8fa5,roughness:.55,metalness:.1});node.geometry.computeVertexNormals();}});}
  else if(extension==="3mf")object=new ThreeMFLoader().parse(buffer);
  else throw new Error("Unterstützt sind STL, OBJ und 3MF");
  const bounds=new T.Box3().setFromObject(object),dimensions=bounds.getSize(new T.Vector3());
  if(![dimensions.x,dimensions.y,dimensions.z].every(Number.isFinite)||Math.max(dimensions.x,dimensions.y,dimensions.z)<=0){dispose(object);throw new Error("Keine darstellbare Geometrie");}
  object.position.sub(bounds.getCenter(new T.Vector3()));const group=new T.Group();group.add(object);group.rotation.x=-Math.PI/2;
  return {group,dimensions,distance:Math.max(dimensions.x,dimensions.y,dimensions.z)*2};
}
function dispose(object){object.traverse(node=>{node.geometry?.dispose();for(const material of (Array.isArray(node.material)?node.material:[node.material])){if(!material)continue;for(const value of Object.values(material))if(value?.isTexture)value.dispose();material.dispose();}});}
function setup(scene){scene.add(new T.HemisphereLight(0xffffff,0x778899,1.3));const light=new T.DirectionalLight(0xffffff,1.6);light.position.set(1,2,1.5);scene.add(light);}
export async function showModel(path,container,info){
  const loaded=await model(path);let renderer;
  try{renderer=new T.WebGLRenderer({antialias:true});}catch(error){dispose(loaded.group);throw error;}
  renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));container.append(renderer.domElement);
  const scene=new T.Scene();scene.background=new T.Color(getComputedStyle(container).backgroundColor);setup(scene);scene.add(loaded.group);
  const camera=new T.PerspectiveCamera(40,1,Math.max(.001,loaded.distance/10000),Math.max(100,loaded.distance*100));camera.position.set(loaded.distance,loaded.distance*.8,loaded.distance);
  const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
  const resize=()=>{const w=Math.max(1,container.clientWidth),h=Math.max(1,container.clientHeight);renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();};resize();
  const observer=typeof ResizeObserver!=="undefined"?new ResizeObserver(resize):null;observer?.observe(container);window.addEventListener("resize",resize);
  const d=loaded.dimensions;info.textContent=d.x.toFixed(1)+" × "+d.y.toFixed(1)+" × "+d.z.toFixed(1)+" mm · Drehen / Zoomen";
  let active=true,frame;function loop(){if(!active)return;controls.update();renderer.render(scene,camera);frame=requestAnimationFrame(loop);}loop();
  return ()=>{if(!active)return;active=false;cancelAnimationFrame(frame);observer?.disconnect();window.removeEventListener("resize",resize);controls.dispose();dispose(loaded.group);renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();};
}
let database;
function db(){if(!database)database=new Promise(resolve=>{if(!globalThis.indexedDB)return resolve(null);const request=indexedDB.open("hai-thumbs",1);request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains("t"))request.result.createObjectStore("t");};request.onsuccess=()=>resolve(request.result);request.onerror=request.onblocked=()=>resolve(null);});return database;}
async function cached(key){const database=await db();if(!database)return null;try{return await new Promise(resolve=>{const request=database.transaction("t").objectStore("t").get(key);request.onsuccess=()=>resolve(request.result);request.onerror=()=>resolve(null);});}catch{return null;}}
async function store(key,value){const database=await db();if(!database)return;try{const transaction=database.transaction("t","readwrite"),storage=transaction.objectStore("t");storage.put(value,key);const request=storage.getAllKeys();request.onsuccess=()=>{for(const old of request.result.slice(0,Math.max(0,request.result.length-256)))storage.delete(old);};}catch{}}
let preview;
export async function thumbnail(path,mtime,size){
  const key="restored-v1|"+path+"|"+mtime+"|"+size,hit=await cached(key);if(typeof hit==="string"&&hit.startsWith("data:image/png;base64,"))return hit;
  const loaded=await model(path);
  try{
    if(!preview){const renderer=new T.WebGLRenderer({antialias:true,alpha:true,preserveDrawingBuffer:true});renderer.setSize(160,160);renderer.setClearColor(0,0);const scene=new T.Scene();setup(scene);preview={renderer,scene};}
    const camera=new T.PerspectiveCamera(40,1,Math.max(.001,loaded.distance/10000),Math.max(100,loaded.distance*100));camera.position.set(loaded.distance,loaded.distance*.8,loaded.distance);camera.lookAt(0,0,0);
    preview.scene.add(loaded.group);preview.renderer.render(preview.scene,camera);const url=preview.renderer.domElement.toDataURL("image/png");await store(key,url);return url;
  }finally{preview?.scene.remove(loaded.group);dispose(loaded.group);}
}
window.addEventListener("beforeunload",()=>{if(preview){preview.renderer.dispose();preview.renderer.forceContextLoss();}});
