import os, io, csv, json, time, uuid, hmac, hashlib, shutil, secrets
from pathlib import Path
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from . import telegram_bot as TB

ROOT = Path(os.getenv("SHARE_PATH", "/share")).resolve()
DATA = Path(os.getenv("DATA_DIR", "/data")).resolve()
DATA.mkdir(parents=True, exist_ok=True)
if os.getuid() == 0:  # Rechte auf PUID/PGID absenken, damit Dateien auf dem Share passen
    u, g = int(os.getenv("PUID", 1000)), int(os.getenv("PGID", 1000))
    os.chown(DATA, u, g); os.setgid(g); os.setuid(u)

SF, FF = DATA / "settings.json", DATA / "filaments.json"
FIELDS = ["brand", "material", "color_name", "color_hex", "weight_total", "weight_remaining", "notes"]

def load(f, d):
    try: return json.loads(f.read_text("utf-8"))
    except Exception: return d
def save(f, v): f.write_text(json.dumps(v, ensure_ascii=False, indent=1), "utf-8")
def settings():
    s = {"max_upload_mb": int(os.getenv("MAX_UPLOAD_MB", 500)),
         "allowed_ext": os.getenv("ALLOWED_EXTENSIONS", "stl,3mf,obj,step,stp,gcode,zip,png,jpg,pdf,txt"), "pw_hash": None, "trash_enabled": True, "trash_days": 30, "default_theme": "modern", "title": "hAI.3DDir", "thumb_max_mb": 20, "tg_low_g": 100, "tg_notify_low": True, "tg_notify_upload": True}
    s.update(load(SF, {})); return s
def hpw(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    return salt + "$" + hashlib.scrypt(pw.encode(), salt=salt.encode(), n=2**14, r=8, p=1).hex()
def check_pw(pw):
    h = settings()["pw_hash"]
    if h: return hmac.compare_digest(h, hpw(pw, h.split("$")[0]))
    return hmac.compare_digest(pw.encode(), os.getenv("ADMIN_PASSWORD", "changeme").encode())

def safe(rel=""):
    p = (ROOT / (rel or "").lstrip("/")).resolve()
    if p != ROOT and ROOT not in p.parents: raise HTTPException(400, "Ungültiger Pfad")
    return p
def clean(n):
    n = Path(n or "").name.strip()
    if not n or n in (".", ".."): raise HTTPException(400, "Ungültiger Name")
    return n

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY") or secrets.token_hex(32),
                   max_age=7 * 86400, same_site="lax")
def auth(r: Request):
    if not r.session.get("ok"): raise HTTPException(401, "Nicht angemeldet")
A = APIRouter(prefix="/api")
R = APIRouter(prefix="/api", dependencies=[Depends(auth)])

class Login(BaseModel): password: str
class P(BaseModel):
    path: str = ""
    name: str = ""
class S(BaseModel):
    max_upload_mb: int
    allowed_ext: str
class PW(BaseModel): password: str

fails = {}
@A.post("/login")
def login(b: Login, r: Request):
    ip, now = r.client.host if r.client else "?", time.time()
    a = [t for t in fails.get(ip, []) if now - t < 300]
    if len(a) >= 5: raise HTTPException(429, "Zu viele Versuche, bitte 5 Minuten warten")
    if not check_pw(b.password):
        fails[ip] = a + [now]; raise HTTPException(401, "Falsches Passwort")
    fails.pop(ip, None); r.session["ok"] = True; return {"auth": True}
@A.post("/logout")
def logout(r: Request): r.session.clear(); return {"auth": False}
@A.get("/me")
def me(r: Request): return {"auth": bool(r.session.get("ok"))}

# ---- Dateien ----
@R.get("/list")
def ls(path: str = ""):
    d = safe(path)
    if not d.is_dir(): raise HTTPException(404, "Ordner nicht gefunden")
    items = []
    for e in sorted(d.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
        if e.name.startswith("."): continue
        st = e.stat()
        items.append({"name": e.name, "dir": e.is_dir(), "size": 0 if e.is_dir() else st.st_size, "mtime": st.st_mtime})
    return {"path": "" if d == ROOT else d.relative_to(ROOT).as_posix(), "items": items}

@R.post("/upload")
async def upload(path: str = "", files: list[UploadFile] = File(...)):
    d, s = safe(path), settings()
    ok = {x.strip().lower().lstrip(".") for x in s["allowed_ext"].split(",") if x.strip()}
    lim = s["max_upload_mb"] * 1048576
    for f in files:
        n = clean(f.filename); ext = n.rsplit(".", 1)[-1].lower() if "." in n else ""
        if ok and ext not in ok: raise HTTPException(400, f"Endung .{ext} ist nicht erlaubt")
        t, size = d / n, 0
        with open(t, "wb") as o:
            while c := await f.read(1 << 20):
                size += len(c)
                if size > lim:
                    o.close(); t.unlink(missing_ok=True); raise HTTPException(413, f"Datei größer als {s['max_upload_mb']} MB")
                o.write(c)
    TB.upload_note([f.filename for f in files], path)
    return {"saved": len(files)}

@R.get("/file")
def get_file(path: str, dl: int = 0):
    p = safe(path)
    if not p.is_file(): raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(p, filename=p.name if dl else None, media_type="application/octet-stream")

@R.post("/mkdir")
def mkdir(b: P):
    try: (safe(b.path) / clean(b.name)).mkdir()
    except FileExistsError: raise HTTPException(409, "Existiert bereits")
    return {"ok": True}

@R.post("/rename")
def rename(b: P):
    p = safe(b.path)
    if p == ROOT: raise HTTPException(400, "Root kann nicht umbenannt werden")
    t = p.with_name(clean(b.name))
    if t.exists(): raise HTTPException(409, "Existiert bereits")
    p.rename(t); return {"ok": True}

@R.post("/delete")
def delete(b: P):
    p = safe(b.path)
    if p == ROOT: raise HTTPException(400, "Root kann nicht gelöscht werden")
    if settings()["trash_enabled"]:
        i = uuid.uuid4().hex[:8]; td = ROOT / ".trash" / i; td.mkdir(parents=True)
        d = p.is_dir(); shutil.move(str(p), str(td / p.name))
        save(TJ, load(TJ, []) + [{"id": i, "name": p.name, "orig": p.relative_to(ROOT).as_posix(), "dir": d, "ts": time.time()}])
    else: _rm(p)
    return {"ok": True}

# ---- Admin ----
KEYS = {"max_upload_mb": int, "allowed_ext": str, "trash_enabled": bool, "trash_days": int, "default_theme": str, "title": str, "thumb_max_mb": int, "tg_low_g": int, "tg_notify_low": bool, "tg_notify_upload": bool}
@R.get("/settings")
def get_settings():
    s = settings(); return {k: s[k] for k in KEYS}
@R.put("/settings")
def put_settings(b: dict):
    s = load(SF, {})
    for k, t in KEYS.items():
        if k in b: s[k] = t(b[k])
    save(SF, s); return {"ok": True}
@A.get("/config")
def config():
    s = settings(); return {"title": s["title"], "default_theme": s["default_theme"], "thumb_max_mb": s["thumb_max_mb"]}
@app.get("/health")
def health(): return {"status": "ok"}

@R.post("/password")
def set_pw(b: PW):
    if len(b.password) < 6: raise HTTPException(400, "Mindestens 6 Zeichen")
    s = load(SF, {}); s["pw_hash"] = hpw(b.password); save(SF, s); return {"ok": True}

# ---- Filamente ----
def norm(d):
    d = {str(k).strip().lower(): v for k, v in d.items() if k}
    o = {k: str(d.get(k) or "").strip() for k in ("brand", "material", "color_name", "color_hex", "notes")}
    for k in ("weight_total", "weight_remaining"):
        try: o[k] = float(str(d.get(k) or 0).replace(",", "."))
        except ValueError: o[k] = 0
    h = o["color_hex"]; o["color_hex"] = "#888888" if not h else (h if h.startswith("#") else "#" + h)
    return o

@R.get("/filaments")
def fl(): return load(FF, [])
@R.post("/filaments")
def fadd(b: dict):
    l = load(FF, []); r = {"id": uuid.uuid4().hex[:8], **norm(b)}; l.append(r); save(FF, l); return r
@R.put("/filaments/{i}")
def fput(i: str, b: dict):
    l = load(FF, [])
    for r in l:
        if r["id"] == i: prev = r["weight_remaining"]; r.update(norm(b)); save(FF, l); TB.low(r, prev); return r
    raise HTTPException(404, "Rolle nicht gefunden")
@R.delete("/filaments/{i}")
def fdel(i: str):
    save(FF, [r for r in load(FF, []) if r["id"] != i]); return {"ok": True}

@R.get("/filaments/export")
def fexp(fmt: str = "csv"):
    l = load(FF, [])
    if fmt == "json":
        return Response(json.dumps(l, ensure_ascii=False, indent=1), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="filamente.json"'})
    o = io.StringIO(); w = csv.DictWriter(o, FIELDS, delimiter=";", extrasaction="ignore"); w.writeheader(); w.writerows(l)
    return Response("\ufeff" + o.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="filamente.csv"'})

@R.post("/filaments/import")
async def fimp(file: UploadFile = File(...), replace: int = 0):
    t = (await file.read()).decode("utf-8-sig")
    try:
        if (file.filename or "").lower().endswith(".json"): rows = json.loads(t)
        else:
            h = t.split("\n", 1)[0]
            rows = list(csv.DictReader(io.StringIO(t), delimiter=";" if h.count(";") > h.count(",") else ","))
    except Exception: raise HTTPException(400, "Datei konnte nicht gelesen werden")
    if not isinstance(rows, list): raise HTTPException(400, "Erwartet wird eine Liste von Rollen")
    new = [{"id": uuid.uuid4().hex[:8], **norm(r)} for r in rows if isinstance(r, dict)]
    save(FF, new if replace else load(FF, []) + new)
    return {"imported": len(new)}

# ---- Papierkorb, Suche, Verschieben, ZIP, Statistik ----
import tempfile, zipfile
from starlette.background import BackgroundTask
TJ = DATA / "trash.json"
class IDs(BaseModel):
    paths: list[str] = []
    to: str = ""
    id: str = ""
def _rm(p): shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
def purge_old():
    days, l, keep = settings()["trash_days"], load(TJ, []), []
    for e in l:
        if days and time.time() - e["ts"] > days * 86400: _rm(ROOT / ".trash" / e["id"])
        else: keep.append(e)
    if len(keep) != len(l): save(TJ, keep)
    return keep
@R.get("/trash")
def trash_list(): return purge_old()
@R.post("/trash/restore")
def trash_restore(b: IDs):
    l = load(TJ, []); e = next((x for x in l if x["id"] == b.id), None)
    if not e: raise HTTPException(404, "Eintrag nicht gefunden")
    src, dst = ROOT / ".trash" / e["id"] / e["name"], safe(e["orig"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists(): dst = dst.with_name(dst.stem + "_wiederhergestellt" + dst.suffix)
    shutil.move(str(src), str(dst)); _rm(ROOT / ".trash" / e["id"])
    save(TJ, [x for x in l if x is not e]); return {"ok": True}
@R.post("/trash/purge")
def trash_purge(b: IDs):
    keep = []
    for x in load(TJ, []):
        if not b.id or x["id"] == b.id: _rm(ROOT / ".trash" / x["id"])
        else: keep.append(x)
    save(TJ, keep); return {"ok": True}
@R.get("/search")
def search(q: str):
    q, out = q.lower().strip(), []
    if len(q) < 2: return out
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if not d.startswith(".")]
        for n in dn + fn:
            if q in n.lower() and not n.startswith("."):
                p = Path(dp) / n
                out.append({"name": n, "dir": p.is_dir(), "size": 0 if p.is_dir() else p.stat().st_size, "path": p.relative_to(ROOT).as_posix(), "mtime": p.stat().st_mtime})
                if len(out) >= 300: return out
    return out
@R.post("/move")
def move(b: IDs):
    d = safe(b.to)
    for x in b.paths:
        p = safe(x)
        if p == ROOT or d == p or p in d.parents: raise HTTPException(400, "Ziel liegt im verschobenen Ordner")
        if (d / p.name).exists(): raise HTTPException(409, f"{p.name} existiert im Ziel bereits")
        shutil.move(str(p), str(d / p.name))
    return {"ok": True}
@R.post("/zip")
def zipit(b: IDs):
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False); tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as z:
        for x in b.paths:
            p = safe(x)
            if p.is_file(): z.write(p, p.name)
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file() and ".trash" not in f.parts: z.write(f, (Path(p.name) / f.relative_to(p)).as_posix())
    return FileResponse(tmp.name, filename="3DDir.zip", media_type="application/zip", background=BackgroundTask(os.unlink, tmp.name))
@R.get("/stats")
def stats():
    n = sz = 0
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d != ".trash"]
        for f in fn:
            try: sz += (Path(dp) / f).stat().st_size; n += 1
            except OSError: pass
    u = shutil.disk_usage(ROOT)
    return {"files": n, "bytes": sz, "free": u.free, "trash": len(load(TJ, [])), "filaments": len(load(FF, []))}

@R.get("/telegram")
def tg_status(): return TB.status()
@R.post("/telegram/test")
def tg_test():
    if not TB.status()["enabled"]: raise HTTPException(400, "Bot ist nicht aktiv (Token und erlaubte IDs setzen)")
    TB.notify("✅ Testnachricht von hAI.3DDir"); return {"ok": True}

app.include_router(A); app.include_router(R)
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))

TB.start()
