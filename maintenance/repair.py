import ast,re
from pathlib import Path
p=Path('app/main.py'); tree=ast.parse(p.read_text()); seen=set(); kept=[]
for node in reversed(tree.body):
    key=None; skip=False
    for d in getattr(node,'decorator_list',[]):
        if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.args and isinstance(d.args[0],ast.Constant):
            owner=ast.unparse(d.func.value); path=d.args[0].value
            skip=owner=='R_ADMIN' or (owner=='A' and path!='/config') or (owner=='app' and node.name not in ('health','mcp_endpoint','mcp_get')) or path=='/debug/checkpw'
            key=(owner,d.func.attr,re.sub(r'\{[^}]+\}','{}',path))
    if skip: continue
    if key is None and isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): key=('fn',node.name)
    if key is not None:
        if key in seen: continue
        seen.add(key)
    if isinstance(node,ast.FunctionDef) and node.name=='delete': node.body=[n for n in node.body if not isinstance(n,ast.FunctionDef)]
    kept.append(node)
tree.body=list(reversed(kept)); s=ast.unparse(ast.fix_missing_locations(tree))+'\n'
def change(a,b):
    global s
    if s.count(a)!=1: raise RuntimeError('Unexpected source: '+a[:60])
    s=s.replace(a,b,1)
change("R = APIRouter(prefix='/api')","R = APIRouter(prefix='/api',dependencies=[Depends(auth)])\nPUBLIC=APIRouter(prefix='/api')")
for method,path in [('post','login'),('post','logout'),('get','me')]: change('@R.'+method+"('/"+path+"')",'@PUBLIC.'+method+"('/"+path+"')")
change('app.include_router(A)','app.include_router(PUBLIC)\napp.include_router(A,dependencies=[Depends(auth)])')
change('from . import extras as EX','from . import extras as EX\nfrom .slicer import slicer_info\nEX.slicer_info=slicer_info')
change('def get_slicer_info(path: str):','async def get_slicer_info(path: str):')
change('def get_slicer_image(path: str, v: str):',"async def get_slicer_image(path: str,v:str=''):")
s=s.replace('result = run_in_threadpool(EX.slicer_info, p, cache_dir)','result = await run_in_threadpool(EX.slicer_info,p,cache_dir)')
change("'has': result['data'] or result['image'], 'data': result['data'], 'image': result['image']","'has':bool(result['data'] or result['image']),'data':result['data'],'image':bool(result['image'])")
change("return FileResponse(p, media_type=EX._mime(result['image']) if result['image'] else 'image/png', headers={'Cache-Control': 'private, max-age=86400'})","return Response(result['image'],media_type=EX._mime(result['image']),headers={'Cache-Control':'private, max-age=3600'})")
change('for f in (FF, PF):','for f in (SF, FF, PF):')
change('if f.exists():\n                z.write(f, f.name)',"z.writestr(f.name,f.read_bytes() if f.exists() else (b'{}' if f==SF else b'[]'))")
change("if n in ('filaments.json', 'prints.json'):","if n in ('settings.json','filaments.json','prints.json'):")
change('t, size = (d / n, 0)',"t,size=(safe((d/n).relative_to(ROOT).as_posix()),0)")
change("return FileResponse(IMG / r['image'])","image=(IMG/r['image']).resolve()\n    if image.parent!=IMG: raise HTTPException(400,'Ungültiger Bildpfad')\n    return FileResponse(image)")
# A persisted secret avoids losing sessions on every container restart.
secret="""def session_secret():
    if os.getenv('SECRET_KEY'): return os.environ['SECRET_KEY']
    path=DATA/'.session_secret'
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as out: out.write(secrets.token_hex(32))
    except FileExistsError: pass
    value=path.read_text().strip()
    if not value: raise RuntimeError('Leerer Session-Schlüssel')
    return value
SECRET=session_secret()
def auth_version():
    return hmac.new(SECRET.encode(),str(settings().get('pw_hash') or os.getenv('ADMIN_PASSWORD','changeme')).encode(),hashlib.sha256).hexdigest()
"""
change('app = FastAPI(',secret+'\napp = FastAPI(')
change("secret_key=os.getenv('SECRET_KEY') or secrets.token_hex(32)",'secret_key=SECRET')
change("if not r.session.get('ok'):","if not r.session.get('ok') or not hmac.compare_digest(str(r.session.get('version','')),auth_version()):")
change("r.session['ok'] = True","r.session.clear()\n    r.session['ok']=True\n    r.session['version']=auth_version()")
change("return {'auth': bool(r.session.get('ok')), 'session': dict(r.session)}","return {'auth':bool(r.session.get('ok')) and hmac.compare_digest(str(r.session.get('version','')),auth_version())}")
extra="""def migrate_tokens():
    rows=MCP.tokens(); changed=False
    for token in rows:
        if token.get('token'):
            token['hash']=MCP._h(token.pop('token')); token['ro']=bool(token.get('ro') or token.pop('read_only',False)); changed=True
    if changed: save(MCP._tf(),rows)
migrate_tokens()
@MCP.tool('get_cost_summary','Materialkosten und Restwert')
def mcp_cost_summary(): return cost_summary()
@MCP.tool('get_slicer_info','Slicer-Metadaten',{'path':('string','Relativer Pfad')},['path'])
def mcp_slicer_info(path):
    result=EX.slicer_info(safe(path),DATA/'cache'/'slicer'); return {'data':result['data'],'image':bool(result['image'])}
"""
change('app.include_router(PUBLIC)',extra+'\napp.include_router(PUBLIC)'); p.write_text(s)
p=Path('app/static/index.html'); h=p.read_text()
a=h.index('// Load slicer information with IntersectionObserver'); b=h.index('// Load slicer information with IntersectionObserver',a+1); c=h.index('// Observer for thumbnail loading',b); h=h[:b]+h[c:]
a=h.index('// Start\nconst start='); b=h.index('</script>',a); h=h[:a]+"(async()=>{try{if((await api('/me')).auth)start();else showLogin();}catch(e){showLogin();alert(e.message);}})();\n"+h[b:]
h=h.replace('CFG.fileView=fileView;','').replace('const fileView=s.file_view;for(const r of document.querySelectorAll(\'input[name="file_view"]\')){r.checked=r.value===fileView}','')
h=h.replace('const r=await fetch("/api"+u,{...o,credentials:"include"});if(!r.ok)throw new Error(r.status);return r.json()','const headers=new Headers(o.headers);if(typeof o.body==="string")headers.set("Content-Type","application/json");const r=await fetch("/api"+u,{...o,headers,credentials:"include"}),data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(typeof data.detail==="string"?data.detail:"HTTP "+r.status);return data')
for a,b in [('/api/admin/settings','/settings'),('/api/admin/stats','/stats'),('/api/admin/password','/password'),('/api/admin/cache','/cache'),('/api/admin/backup/restore','/backup/restore'),('/api/admin/mcp/tokens','/mcp/tokens')]: h=h.replace(a,b)
h=h.replace('Promise.all([api("/settings"),api("/stats")]);','Promise.all([api("/settings"),api("/stats")]);CFG.fileView=s.file_view;for(const radio of document.querySelectorAll(\'input[name="file_view"]\'))radio.checked=radio.value===s.file_view;')
h=h.replace('api("/mcp/tokens");document.getElementById("mt")','api("/mcp");document.getElementById("mt")').replace('t.read_only','t.ro').replace('read_only:document.getElementById("mr").checked','ro:document.getElementById("mr").checked')
h=h.replace('<input id="mn" placeholder="Name" required>','<input id="mn" placeholder="Name" required><label><input id="mr" type="checkbox" checked> Nur lesen</label>')
h=h.replace('FormData.fromEntries([[f.name,f]])','(()=>{const body=new FormData();body.append("file",f);return body;})()')
h=h.replace("iconClass='ic data-s=1'","iconClass='ic data-s'").replace("iconClass='ic data-t=1'","iconClass='ic data-t'").replace('id="a_vw"','').replace('dialog::backdialog','dialog::backdrop')
h=h.replace('const esc=s=>s.replace','const esc=s=>String(s??"").replace').replace('${i.name}','${esc(i.name)}').replace('${t.name}','${esc(t.name)}')
h=h.replace('loadFiles();loadFil();loadAdm()','Promise.allSettled([loadFiles(),loadFil(),loadAdm(),loadMcp()]).then(rs=>{for(const r of rs)if(r.status==="rejected")toast("Angemeldet; Ladefehler: "+r.reason.message);})')
h=h.replace('document.getElementById("th").innerHTML=opts;','document.getElementById("th").innerHTML=opts;document.getElementById("a_th").innerHTML=opts;')
h=h.replace('document.getElementById("fx").onclick=()=>{','document.getElementById("fx").onclick=e=>{e.preventDefault();').replace('toast("Passwort geändert")','showLogin();toast("Passwort geändert; erneut anmelden")')
p.write_text(h)
p=Path('app/mcp_server.py'); s=p.read_text().replace('hmac.compare_digest(t["hash"], hh)','hmac.compare_digest(str(t.get("hash","")),hh)'); p.write_text(s)
