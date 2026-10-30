import os, io, re, csv, json, time, uuid, hmac, hashlib, shutil, secrets, zipfile, tempfile, base64
from pathlib import Path
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from . import telegram_bot as TB
from . import mcp_server as MCP
from . import extras as EX

ROOT = Path(os.getenv("SHARE_PATH", "/share")).resolve()
DATA = Path(os.getenv("DATA_DIR", "/data")).resolve()
DATA.mkdir(parents=True, exist_ok=True)
if os.getuid() == 0:  # Rechte auf PUID/PGID absenken, damit Dateien auf dem Share passen
    u, g = int(os.getenv("PUID", 1000)), int(os.getenv("PGID", 1000))
    os.chown(DATA, u, g); os.setgid(g); os.setuid(u)

SF, FF, PF, TJ = DATA / "settings.json", DATA / "filaments.json", DATA / "prints.json", DATA / "trash.json"
IMG = DATA / "img"; IMG.mkdir(exist_ok=True)
FIELDS = ["brand", "material", "color_name", "color_hex", "weight_total", "weight_remaining", "notes", "barcode", "price_per_kg", "purchase_date"]

def load(f, d):
    try: return json.loads(f.read_text("utf-8"))
    except Exception: return d
def save(f, v): f.write_text(json.dumps(v, ensure_ascii=False, indent=1), "utf-8")
def settings():
    s = {"max_upload_mb": int(os.getenv("MAX_UPLOAD_MB", 500)),
         "allowed_ext": os.getenv("ALLOWED_EXTENSIONS", "stl,3mf,obj,step,stp,gcode,zip,png,jpg,pdf,txt"), "pw_hash": None, "trash_enabled": True, "trash_days": 30, "default_theme": "modern", "title": "hAI.3DDir", "thumb_max_mb": 20, "tg_low_g": 100, "tg_notify_start": True, "tg_daily": True, "tg_daily_time": "08:00", "tg_daily_backup": False, "tg_notify_upload": True, "mcp_enabled": True, "folder_view": "links", "sort_by": "name", "sort_order": "asc", "file_view": "icons"}
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
R = APIRouter(prefix="/api")
R_ADMIN = APIRouter(prefix="/api/admin", dependencies=[Depends(auth)])

class Login(BaseModel): password: str
class P(BaseModel):
    path: str = ""
    name: str = ""
class S(BaseModel):
    max_upload_mb: int
    allowed_ext: str
class PW(BaseModel): password: str

fails = {}
@R.post("/login")
def login(b: Login, r: Request):
    ip, now = r.client.host if r.client else "?", time.time()
    a = [t for t in fails.get(ip, []) if now - t < 300]
    if len(a) >= 5: raise HTTPException(429, "Zu viele Versuche, bitte 5 Minuten warten")
    if not check_pw(b.password):
        fails[ip] = a + [now]; raise HTTPException(401, "Falsches Passwort")
    fails.pop(ip, None); r.session["ok"] = True; return {"auth": True}
@R.post("/logout")
def logout(r: Request): r.session.clear(); return {"auth": False}
@R.get("/me")
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

    def _rm(p):
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
    return {"ok": True}

# ---- Admin ----
KEYS = {"max_upload_mb": int, "allowed_ext": str, "trash_enabled": bool, "trash_days": int, "default_theme": str, "title": str, "thumb_max_mb": int, "tg_low_g": int, "tg_notify_start": bool, "tg_daily": bool, "tg_daily_time": str, "tg_daily_backup": bool, "tg_notify_upload": bool, "mcp_enabled": bool, "folder_view": str, "sort_by": str, "sort_order": str}
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
    s = settings(); return {"title": s["title"], "default_theme": s["default_theme"], "thumb_max_mb": s["thumb_max_mb"], "folder_view": s["folder_view"], "sort_by": s["sort_by"], "sort_order": s["sort_order"]}
@app.get("/health")
def health(): return {"status": "ok"}

@R.post("/password")
def set_pw(b: PW):
    if len(b.password) < 6: raise HTTPException(400, "Mindestens 6 Zeichen")
    s = load(SF, {}); s["pw_hash"] = hpw(b.password); save(SF, s); return {"ok": True}

# ---- Backup ----
@A.post("/backup")
def backup():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as t:
        with zipfile.ZipFile(t.name, 'w') as z:
            z.write(SF, "settings.json")
            z.write(FF, "filaments.json")
            z.write(PF, "prints.json")
            for f in IMG.glob("*"):
                if f.is_file():
                    z.write(f, f"img/{f.name}")
    return FileResponse(t.name, media_type="application/zip", filename=f"hai3ddir_backup_{int(time.time())}.zip", background=lambda: os.unlink(t.name))

@A.post("/restore")
async def restore(file: UploadFile = File(...)):
    if not file.filename.endswith('.zip'): raise HTTPException(400, "Nur ZIP-Dateien")
    try:
        with zipfile.ZipFile(file.file, 'r') as z:
            if 'settings.json' in z.namelist(): z.extract('settings.json', DATA)
            if 'filaments.json' in z.namelist(): z.extract('filaments.json', DATA)
            if 'prints.json' in z.namelist(): z.extract('prints.json', DATA)
            for nm in z.namelist():
                if nm.startswith("img/") and not nm.endswith("/"):
                    f = DATA / nm
                    f.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(nm) as s, open(f, 'wb') as d: d.write(s.read())
    except Exception as e: raise HTTPException(400, f"Fehler beim Wiederherstellen: {e}")
    return {"ok": True}

# ---- Admin ----
KEYS = {"max_upload_mb": int, "allowed_ext": str, "trash_enabled": bool, "trash_days": int, "default_theme": str, "title": str, "thumb_max_mb": int, "tg_low_g": int, "tg_notify_start": bool, "tg_daily": bool, "tg_daily_time": str, "tg_daily_backup": bool, "tg_notify_upload": bool, "mcp_enabled": bool, "folder_view": str, "sort_by": str, "sort_order": str, "file_view": str}
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
    s = settings(); return {"title": s["title"], "default_theme": s["default_theme"], "thumb_max_mb": s["thumb_max_mb"], "folder_view": s["folder_view"], "sort_by": s["sort_by"], "sort_order": s["sort_order"], "file_view": s["file_view"]}

# ---- AI-Scan ----
@A.get("/ai")
def ai_status():
    return {"enabled": bool(os.getenv("LLM_BASE_URL")), "model": os.getenv("LLM_MODEL", "")}

@R.post("/ai/label")
async def ai_scan_label(file: UploadFile = File(...)):
    try:
        content = await file.read()
        b64 = base64.b64encode(content).decode()
        # TODO: Implement actual AI label scanning with extras.AI
        return {"brand": "Unbekannt", "material": "PLA", "weight_total": 1000, "weight_remaining": 800}
    except Exception as e:
        raise HTTPException(400, f"AI-Scan fehlgeschlagen: {e}")

# ---- Barcode ----
@R.get("/filaments/barcode/{code}")
def barcode_lookup(code: str):
    filaments = load(FF, [])
    for f in filaments:
        if f.get("barcode") == code:
            return f
    return None

# ---- MCP Server ----
@app.get("/mcp")
def mcp_info():
    tokens = load(DATA / "mcp_tokens.json", [])
    return {"tokens": tokens, "env": bool(os.getenv("MCP_TOKEN"))}

@app.post("/mcp/tokens")
def mcp_create_token(b: dict):
    tokens = load(DATA / "mcp_tokens.json", [])
    t = {
        "id": secrets.token_hex(8),
        "name": b["name"],
        "token": secrets.token_urlsafe(32),
        "read_only": b.get("read_only", False),
        "created": time.time()
    }
    tokens.append(t)
    save(DATA / "mcp_tokens.json", tokens)
    return t

@app.delete("/mcp/tokens/{token}")
def mcp_delete_token(token: str):
    tokens = load(DATA / "mcp_tokens.json", [])
    tokens = [t for t in tokens if t["token"] != token and t["id"] != token]
    save(DATA / "mcp_tokens.json", tokens)
    return {"ok": True}

# ---- Slicer Data ----
@R.get("/slicer")
async def get_slicer_data(path: str, v: str):
    p = safe(path)
    if not p.is_file(): raise HTTPException(404, "Datei nicht gefunden")
    # TODO: Implement actual slicer data extraction
    return {"has": True, "data": {"time_s": 3600, "grams": 120}, "image": None}

@R.get("/slicer/image")
def get_slicer_image(path: str, v: str):
    p = safe(path)
    if not p.is_file(): raise HTTPException(404, "Datei nicht gefunden")
    # TODO: Generate thumbnail from file
    return FileResponse(p, media_type="image/png")

# ---- Filament Images ----
@R.get("/filaments/{id}/image")
def get_filament_image(id: str, v: str = "0"):
    filaments = load(FF, [])
    for f in filaments:
        if f["id"] == id and f.get("image"):
            img_path = IMG / f["image"]
            if img_path.exists():
                return FileResponse(img_path, media_type="image/jpeg")
    raise HTTPException(404, "Bild nicht gefunden")

@R.post("/filaments/{id}/image")
async def upload_filament_image(id: str, file: UploadFile = File(...)):
    filaments = load(FF, [])
    for f in filaments:
        if f["id"] == id:
            filename = f"{id}-{int(time.time())}.jpg"
            img_path = IMG / filename
            content = await file.read()
            img_path.write_bytes(content)
            f["image"] = filename
            f["img_ts"] = int(time.time())
            save(FF, filaments)
            return {"ok": True}
    raise HTTPException(404, "Filament nicht gefunden")

@R.delete("/filaments/{id}/image")
def delete_filament_image(id: str):
    filaments = load(FF, [])
    for f in filaments:
        if f["id"] == id and f.get("image"):
            img_path = IMG / f["image"]
            img_path.unlink(missing_ok=True)
            f.pop("image", None)
            f.pop("img_ts", None)
            save(FF, filaments)
    return {"ok": True}

# ---- Trash ----
@R.get("/trash")
def get_trash():
    return load(TJ, [])

@R.post("/trash/restore")
def restore_trash_item(b: dict):
    l = load(TJ, [])
    t = next((x for x in l if x["id"] == b["id"]), None)
    if t:
        trash_path = ROOT / ".trash" / t["id"]
        if trash_path.exists():
            target_path = ROOT / t["orig"]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(trash_path), str(target_path))
        l.remove(t)
        save(TJ, l)
    return {"ok": True}

@R.post("/trash/purge")
def purge_trash(b: dict):
    l = load(TJ, [])
    if not b.get("id"):
        # Empty all trash
        for item in l:
            trash_path = ROOT / ".trash" / item["id"]
            if trash_path.exists():
                shutil.rmtree(trash_path)
        save(TJ, [])
    else:
        # Purge specific item
        t = next((x for x in l if x["id"] == b["id"]), None)
        if t:
            trash_path = ROOT / ".trash" / t["id"]
            if trash_path.exists():
                shutil.rmtree(trash_path)
            l.remove(t)
            save(TJ, l)
    return {"ok": True}

# ---- Prints & Costs ----
@R.post("/prints")
def add_print(b: dict):
    prints = load(PF, [])
    p = {"id": uuid.uuid4().hex[:8], "filament_id": b["filament_id"], "grams": b["grams"], "name": b.get("name", ""), "file": b.get("file", ""), "ts": time.time(), "cost": b.get("cost", 0)}
    prints.append(p)
    save(PF, prints)
    
    # Update filament remaining weight
    filaments = load(FF, [])
    for f in filaments:
        if f["id"] == b["filament_id"]:
            prev = f["weight_remaining"]
            f["weight_remaining"] = max(0, f["weight_remaining"] - b["grams"])
            save(FF, filaments)
            TB.low(f, prev)
    
    return p

@R.get("/prints")
def get_prints(filament_id: str = None):
    prints = load(PF, [])
    if filament_id:
        prints = [p for p in prints if p["filament_id"] == filament_id]
    return prints

@R.get("/prints/summary")
def get_prints_summary():
    prints = load(PF, [])
    filaments = load(FF, [])
    
    invested = sum(f.get("price_per_kg", 0) * f.get("weight_total", 0) / 1000 for f in filaments)
    stock_value = sum(f.get("price_per_kg", 0) * f.get("weight_remaining", 0) / 1000 for f in filaments)
    
    by_month = {}
    by_material = {}
    
    for p in prints:
        f = next((x for x in filaments if x["id"] == p["filament_id"]), None)
        if f:
            month = time.strftime("%Y-%m", time.localtime(p["ts"]))
            if month not in by_month:
                by_month[month] = {"prints": 0, "grams": 0, "cost": 0}
            by_month[month]["prints"] += 1
            by_month[month]["grams"] += p["grams"]
            by_month[month]["cost"] += p.get("cost", 0)
            
            material = f.get("material", "Unbekannt")
            if material not in by_material:
                by_material[material] = {"prints": 0, "grams": 0, "cost": 0}
            by_material[material]["prints"] += 1
            by_material[material]["grams"] += p["grams"]
            by_material[material]["cost"] += p.get("cost", 0)
    
    return {"invested": invested, "stock_value": stock_value, "by_month": by_month, "by_material": by_material}

@R.delete("/prints/{id}")
def delete_print(id: str):
    prints = load(PF, [])
    p = next((x for x in prints if x["id"] == id), None)
    if p:
        # Restore filament weight
        filaments = load(FF, [])
        for f in filaments:
            if f["id"] == p["filament_id"]:
                f["weight_remaining"] += p["grams"]
                save(FF, filaments)
                TB.low(f, f["weight_remaining"] - p["grams"])
                break
        
        prints.remove(p)
        save(PF, prints)
        return {"ok": True}
    raise HTTPException(404, "Druck nicht gefunden")

# ---- Estimate ----
@R.post("/estimate")
def estimate_consumption(b: dict):
    p = safe(b["path"])
    if not p.is_file(): raise HTTPException(404, "Datei nicht gefunden")
    
    # TODO: Implement actual consumption estimation
    weight = b.get("grams", 100)
    material = b.get("material", "PLA")
    note = f"Geschätzter Verbrauch für {material}"
    
    return {"grams": weight, "note": note}

# ---- Cache ----
@R.delete("/cache")
def clear_cache():
    # TODO: Implement actual cache clearing
    return {"ok": True}

# ---- Stats ----
@R.get("/stats")
def get_stats():
    total_files = sum(1 for _ in ROOT.rglob("*") if not _.is_dir())
    total_size = sum(f.stat().st_size for f in ROOT.rglob("*") if f.is_file())
    trash_count = len(load(TJ, []))
    filaments_count = len(load(FF, []))
    
    # Get free space
    free_space = shutil.disk_usage(ROOT).free
    
    return {
        "files": total_files,
        "bytes": total_size,
        "free": free_space,
        "trash": trash_count,
        "filaments": filaments_count
    }

# ---- MCP Tokens ----
@R.get("/mcp/tokens")
def mcp_tokens():
    return load(DATA / "mcp_tokens.json", [])

@R.post("/mcp/tokens")
def mcp_create(b: dict):
    tokens = load(DATA / "mcp_tokens.json", [])
    t = {
        "name": b["name"],
        "token": secrets.token_urlsafe(32),
        "read_only": b.get("read_only", False),
        "created": time.time()
    }
    tokens.append(t); save(DATA / "mcp_tokens.json", tokens)
    return t

@R.delete("/mcp/tokens/{i}")
def mcp_delete(i: str):
    tokens = load(DATA / "mcp_tokens.json", [])
    tokens = [t for t in tokens if t.get("id") != i and t.get("token") != i]
    save(DATA / "mcp_tokens.json", tokens); return {"ok": True}

# ---- Filamente ----
def norm(d):
    d = {str(k).strip().lower(): v for k, v in d.items() if k}
    o = {k: str(d.get(k) or "").strip() for k in ("brand", "material", "color_name", "color_hex", "notes", "barcode")}
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
    for r in load(FF, []):
        if r["id"] == i and r.get("image"): (IMG / r["image"]).unlink(missing_ok=True)
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

# ---- Bilder, Barcode, Druckverlauf, KI ----
from starlette.concurrency import run_in_threadpool
def set_image(fid, data, ct="image/jpeg"):
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(ct)
    if not ext: raise HTTPException(400, "Nur JPG, PNG oder WebP")
    if len(data) > 6 * 1048576: raise HTTPException(413, "Bild größer als 6 MB")
    l = load(FF, []); r = next((x for x in l if x["id"] == fid), None)
    if not r: raise HTTPException(404, "Rolle nicht gefunden")
    if r.get("image"): (IMG / r["image"]).unlink(missing_ok=True)
    r["image"] = f"{fid}.{ext}"; r["img_ts"] = int(time.time()); (IMG / r["image"]).write_bytes(data); save(FF, l); return r
@R.post("/filaments/{i}/image")
async def img_set(i: str, file: UploadFile = File(...)): return set_image(i, await file.read(), file.content_type)
@R.delete("/filaments/{i}/image")
def img_del(i: str):
    l = load(FF, [])
    for r in l:
        if r["id"] == i and r.get("image"): (IMG / r["image"]).unlink(missing_ok=True); r.pop("image"); r.pop("img_ts", None)
    save(FF, l); return {"ok": True}
@R.get("/filaments/{i}/image")
def img_get(i: str):
    r = next((x for x in load(FF, []) if x["id"] == i), None)
    if not r or not r.get("image"): raise HTTPException(404, "Kein Bild")
    return FileResponse(IMG / r["image"])
def find_barcode(code):
    c = str(code).strip().lstrip("0")
    return next((r for r in load(FF, []) if c and str(r.get("barcode", "")).strip().lstrip("0") == c), None)
@R.get("/filaments/barcode/{code}")
def fbar(code: str): return find_barcode(code)
@R.get("/prints")
def prints_list(filament_id: str = ""):
    return [p for p in load(PF, []) if not filament_id or p["filament_id"] == filament_id][::-1]
@R.post("/prints")
def print_add(b: dict):
    fid = str(b.get("filament_id", "")); g = float(b.get("grams") or 0)
    if g <= 0: raise HTTPException(400, "Gramm müssen größer als 0 sein")
    l = load(FF, []); r = next((x for x in l if x["id"] == fid), None)
    if not r: raise HTTPException(404, "Rolle nicht gefunden")
    prev = r["weight_remaining"]; r["weight_remaining"] = max(0.0, round(prev - g, 1)); save(FF, l); TB.low(r, prev)
    p = {"id": uuid.uuid4().hex[:8], "filament_id": fid, "grams": g, "name": str(b.get("name") or "")[:80], "file": str(b.get("file") or "")[:300], "ts": time.time()}
    save(PF, load(PF, []) + [p]); return {"print": p, "remaining": r["weight_remaining"]}
@R.delete("/prints/{i}")
def print_del(i: str):
    L = load(PF, []); p = next((x for x in L if x["id"] == i), None)
    if not p: raise HTTPException(404, "Buchung nicht gefunden")
    l = load(FF, [])
    for r in l:
        if r["id"] == p["filament_id"]: r["weight_remaining"] = round(r["weight_remaining"] + p["grams"], 1)
    save(FF, l); save(PF, [x for x in L if x is not p]); return {"ok": True}
@R.get("/ai")
def ai_status(): return {"enabled": EX.enabled(), "model": EX.MODEL}
@R.post("/ai/label")
async def ai_label(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 5 * 1048576: raise HTTPException(413, "Bild größer als 5 MB")
    mt = file.content_type if file.content_type in ("image/jpeg", "image/png", "image/webp", "image/gif") else "image/jpeg"
    try: return await run_in_threadpool(EX.ai_label, raw, mt)
    except ValueError as e: raise HTTPException(400, str(e))
@R.post("/estimate")
async def estimate(b: dict):
    p = safe(str(b.get("path", "")))
    try: return await run_in_threadpool(EX.estimate, p, float(b.get("infill") or 15), str(b.get("material") or "PLA"))
    except ValueError as e: raise HTTPException(400, str(e))

# ---- Backup der Filament-DB ----
def make_backup():
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False); tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (FF, PF):
            if f.exists(): z.write(f, f.name)
        for f in IMG.glob("*"): z.write(f, "img/" + f.name)
    return tmp.name
@R.get("/backup")
def backup_dl():
    p = make_backup()
    return FileResponse(p, filename=f"hai3ddir-filamente-{time.strftime('%Y%m%d')}.zip", media_type="application/zip", background=BackgroundTask(os.unlink, p))
@R.post("/backup/restore")
async def backup_restore(file: UploadFile = File(...)):
    try: z = zipfile.ZipFile(io.BytesIO(await file.read()))
    except Exception: raise HTTPException(400, "Keine gültige ZIP-Datei")
    try:
        if not isinstance(json.loads(z.read("filaments.json")), list): raise ValueError
    except Exception: raise HTTPException(400, "filaments.json fehlt oder ist ungültig")
    if FF.exists(): shutil.copy(FF, FF.with_name("filaments.json.bak"))
    for n in z.namelist():
        if n in ("filaments.json", "prints.json"): (DATA / n).write_bytes(z.read(n))
        elif n.startswith("img/") and n[4:] and "/" not in n[4:] and ".." not in n: (IMG / n[4:]).write_bytes(z.read(n))
    return {"ok": True}

# ---- MCP ----
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
@app.post("/mcp")
async def mcp_endpoint(r: Request):
    if r.headers.get("origin"): return JSONResponse({"error": "Origin not allowed"}, 403)
    tok = MCP.auth(r.headers.get("authorization", ""))
    if not tok: return JSONResponse({"error": "Unauthorized"}, 401, headers={"WWW-Authenticate": 'Bearer realm="hAI.3DDir"'})
    try: body = await r.json()
    except Exception: return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, 400)
    out = await run_in_threadpool(MCP.handle, body, tok)
    return Response(status_code=202) if out is None else JSONResponse(out)
@app.get("/mcp")
def mcp_get(): return JSONResponse({"error": "Use POST"}, 405, headers={"Allow": "POST"})
@R.get("/mcp")
def mcp_info(): return {"env": bool(os.getenv("MCP_TOKEN")), "tokens": [{k: t.get(k) for k in ("id", "name", "ro", "created", "used")} for t in MCP.tokens()]}
@R.post("/mcp/tokens")
def mcp_new(b: dict):
    sec = "hai_" + secrets.token_urlsafe(32); L = MCP.tokens()
    L.append({"id": uuid.uuid4().hex[:8], "name": str(b.get("name") or "Agent")[:40], "ro": bool(b.get("ro")), "hash": MCP._h(sec), "created": time.time()})
    save(MCP._tf(), L); return {"token": sec}
@R.delete("/mcp/tokens/{i}")
def mcp_del(i: str): save(MCP._tf(), [t for t in MCP.tokens() if t["id"] != i]); return {"ok": True}

app.include_router(A); app.include_router(R)
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))

TB.start()
