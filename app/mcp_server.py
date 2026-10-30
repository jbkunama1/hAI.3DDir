"""MCP-Server (Streamable HTTP, JSON-RPC) mit Bearer-Token. Endpoint: POST /mcp"""
import os, json, hmac, hashlib, base64, time, inspect
from pathlib import Path

VERS = ["2025-06-18", "2025-03-26", "2024-11-05"]
TOOLS = {}

def M():
    from . import main
    return main
def _h(s): return hashlib.sha256(s.encode()).hexdigest()
def _tf(): return M().DATA / "mcp_tokens.json"
def tokens(): return M().load(_tf(), [])
def _iso(t): return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t))

def auth(h):
    m = M()
    if not m.settings()["mcp_enabled"] or not h.lower().startswith("bearer "): return None
    tok, env = h[7:].strip(), os.getenv("MCP_TOKEN", "")
    if env and hmac.compare_digest(tok.encode(), env.encode()): return {"name": "env", "ro": False}
    hh, L = _h(tok), tokens()
    for t in L:
        if hmac.compare_digest(t["hash"], hh):
            if time.time() - t.get("used", 0) > 60: t["used"] = time.time(); m.save(_tf(), L)
            return t
    return None

def tool(name, desc, props=None, req=(), write=False):
    def d(f):
        sch = {"type": "object", "properties": {k: {"type": v[0], "description": v[1]} for k, v in (props or {}).items()}, "required": list(req)}
        TOOLS[name] = {"f": f, "write": write, "def": {"name": name, "description": desc, "inputSchema": sch, "annotations": {"readOnlyHint": not write}}}
        return f
    return d

def _sort(items, sort, order):
    k = {"size": lambda i: i["size"], "date": lambda i: i["mtime"],
         "type": lambda i: (i["name"].rsplit(".", 1)[-1].lower() if "." in i["name"] else "", i["name"].lower())}.get(sort, lambda i: i["name"].lower())
    rv = order == "desc"
    return sorted([i for i in items if i["dir"]], key=k, reverse=rv) + sorted([i for i in items if not i["dir"]], key=k, reverse=rv)

# ---- Dateien ----
@tool("list_directory", "List folders and files in a directory of the 3D print share. Folders come first.",
      {"path": ("string", "Path relative to the share root, empty = root"), "sort": ("string", "name | size | date | type (default name)"), "order": ("string", "asc | desc (default asc)")})
def list_directory(path="", sort="name", order="asc"):
    d = M().ls(path)
    return {"path": d["path"], "items": [{"name": i["name"], "dir": i["dir"], "size": i["size"], "modified": _iso(i["mtime"])} for i in _sort(d["items"], sort, order)]}

@tool("search_files", "Search files and folders by name (substring, min. 2 characters) across the whole share.", {"query": ("string", "Search term")}, ["query"])
def search_files(query): return M().search(query)

@tool("get_file_info", "Get size, type and modification date of a file or folder.", {"path": ("string", "Relative path")}, ["path"])
def get_file_info(path):
    m = M(); p = m.safe(path)
    if not p.exists(): raise ValueError("Not found")
    s = p.stat(); r = {"path": "" if p == m.ROOT else p.relative_to(m.ROOT).as_posix(), "name": p.name, "type": "folder" if p.is_dir() else "file", "modified": _iso(s.st_mtime)}
    if p.is_dir(): r["entries"] = sum(1 for e in p.iterdir() if not e.name.startswith("."))
    else: r.update(size=s.st_size, extension=p.suffix.lstrip(".").lower())
    return r

@tool("read_file", "Read a file (max 5 MB) as text or base64.", {"path": ("string", "Relative path"), "encoding": ("string", "text | base64 (default text)")}, ["path"])
def read_file(path, encoding="text"):
    p = M().safe(path)
    if not p.is_file(): raise ValueError("File not found")
    if p.stat().st_size > 5 * 1048576: raise ValueError("File larger than 5 MB")
    raw = p.read_bytes()
    return {"name": p.name, "bytes": len(raw), "encoding": encoding, "content": base64.b64encode(raw).decode() if encoding == "base64" else raw.decode("utf-8", "replace")}

@tool("write_file", "Create or overwrite a file. Allowed extensions and size limit follow the admin settings. Missing folders are created.",
      {"path": ("string", "Target path incl. file name"), "content": ("string", "File content"), "encoding": ("string", "text | base64 (default text)"), "overwrite": ("boolean", "Overwrite if it exists (default false)")}, ["path", "content"], True)
def write_file(path, content, encoding="text", overwrite=False):
    m = M(); rel = path.strip("/"); name = m.clean(rel.rpartition("/")[2]); par = m.safe(rel.rpartition("/")[0]); cfg = m.settings()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    ok = {x.strip().lower().lstrip(".") for x in cfg["allowed_ext"].split(",") if x.strip()}
    if ok and ext not in ok: raise ValueError(f"Extension .{ext} not allowed")
    data = base64.b64decode(content) if encoding == "base64" else content.encode()
    if len(data) > cfg["max_upload_mb"] * 1048576: raise ValueError("File too large")
    par.mkdir(parents=True, exist_ok=True); t = par / name
    if t.exists() and not overwrite: raise ValueError("Already exists, set overwrite=true")
    t.write_bytes(data); m.TB.upload_note([name], par.relative_to(m.ROOT).as_posix() if par != m.ROOT else "")
    return {"saved": t.relative_to(m.ROOT).as_posix(), "bytes": len(data)}

@tool("create_folder", "Create a folder (including parents).", {"path": ("string", "Relative path of the new folder")}, ["path"], True)
def create_folder(path): M().safe(path).mkdir(parents=True, exist_ok=True); return {"ok": True}
@tool("move_item", "Move a file or folder into another folder.", {"path": ("string", "Item to move"), "to": ("string", "Target folder")}, ["path", "to"], True)
def move_item(path, to): m = M(); return m.move(m.IDs(paths=[path], to=to))
@tool("rename_item", "Rename a file or folder.", {"path": ("string", "Item path"), "name": ("string", "New name (no path)")}, ["path", "name"], True)
def rename_item(path, name): m = M(); return m.rename(m.P(path=path, name=name))
@tool("delete_item", "Delete a file or folder. Goes to the trash if the trash is enabled (restorable).", {"path": ("string", "Item path")}, ["path"], True)
def delete_item(path): m = M(); return m.delete(m.P(path=path))
@tool("list_trash", "List items in the trash.")
def list_trash(): return M().trash_list()
@tool("restore_trash", "Restore an item from the trash.", {"id": ("string", "Trash entry id from list_trash")}, ["id"], True)
def restore_trash(id): m = M(); return m.trash_restore(m.IDs(id=id))
@tool("get_stats", "Share statistics: file count, used and free space, trash and filament counts.")
def get_stats(): return M().stats()

# ---- Filamente ----
def _fmerge(id, **kw):
    m = M(); cur = next((r for r in m.fl() if r["id"] == id), None)
    if not cur: raise ValueError("Filament spool not found")
    cur.update({k: v for k, v in kw.items() if v is not None}); return m.fput(id, cur)

@tool("list_filaments", "List filament spools (brand, material, color, total and remaining weight in grams).",
      {"material": ("string", "Filter by material, e.g. PLA, PETG, TPU"), "low_only": ("boolean", "Only spools at or below the low-stock threshold")})
def list_filaments(material="", low_only=False):
    m = M(); thr = m.settings()["tg_low_g"]; l = m.fl()
    if material: l = [r for r in l if material.lower() in r["material"].lower()]
    if low_only: l = [r for r in l if r["weight_remaining"] <= thr]
    return {"low_threshold_g": thr, "count": len(l), "filaments": l}
_FP = {"brand": ("string", "Brand"), "material": ("string", "Material, e.g. PLA, PLA+, PLA Silk, PLA Matte, PETG, TPU"), "color_name": ("string", "Color name"),
       "color_hex": ("string", "Color as #RRGGBB"), "weight_total": ("number", "Spool weight in g"), "weight_remaining": ("number", "Remaining weight in g"), "notes": ("string", "Notes"), "barcode": ("string", "EAN/UPC/QR text of the spool")}
@tool("add_filament", "Add a new filament spool.", _FP, ["material"], True)
def add_filament(material, brand="", color_name="", color_hex="#888888", weight_total=1000, weight_remaining=None, notes="", barcode=""):
    return M().fadd({"brand": brand, "material": material, "color_name": color_name, "color_hex": color_hex, "weight_total": weight_total,
                     "weight_remaining": weight_total if weight_remaining is None else weight_remaining, "notes": notes, "barcode": barcode})
@tool("update_filament", "Update fields of a spool; omitted fields stay unchanged.", {"id": ("string", "Spool id"), **_FP}, ["id"], True)
def update_filament(id, brand=None, material=None, color_name=None, color_hex=None, weight_total=None, weight_remaining=None, notes=None, barcode=None):
    return _fmerge(id, brand=brand, material=material, color_name=color_name, color_hex=color_hex, weight_total=weight_total, weight_remaining=weight_remaining, notes=notes, barcode=barcode)
@tool("adjust_filament_weight", "Add or subtract grams from the remaining weight (negative = consumed by a print).",
      {"id": ("string", "Spool id"), "delta_g": ("number", "Grams to add, negative to subtract")}, ["id", "delta_g"], True)
def adjust_filament_weight(id, delta_g):
    cur = next((r for r in M().fl() if r["id"] == id), None)
    if not cur: raise ValueError("Filament spool not found")
    return _fmerge(id, weight_remaining=max(0.0, cur["weight_remaining"] + delta_g))
@tool("delete_filament", "Delete a filament spool.", {"id": ("string", "Spool id")}, ["id"], True)
def delete_filament(id): return M().fdel(id)

@tool("find_filament_by_barcode", "Find a filament spool by its barcode (EAN/UPC/QR text). Returns the spool or {found: false}.", {"code": ("string", "Barcode value")}, ["code"])
def find_filament_by_barcode(code): return M().find_barcode(code) or {"found": False}
@tool("log_print", "Book a print against a spool: subtracts the grams from the remaining weight and stores it in the usage history.",
      {"id": ("string", "Spool id"), "grams": ("number", "Grams used"), "name": ("string", "Print name"), "file": ("string", "Path of the print file in the share")}, ["id", "grams"], True)
def log_print(id, grams, name="", file=""): return M().print_add({"filament_id": id, "grams": grams, "name": name, "file": file})
@tool("list_prints", "Usage history of booked prints, newest first, optionally for one spool.", {"id": ("string", "Spool id (optional)")})
def list_prints(id=""): return M().prints_list(id)
@tool("estimate_filament_usage", "Estimate filament usage in grams for a print file in the share. G-code and sliced 3MF files give exact slicer values; STL/OBJ/3MF models are estimated from mesh volume (walls + infill, no supports).",
      {"path": ("string", "File path in the share"), "infill_percent": ("number", "Infill in percent, default 15"), "material": ("string", "Material for density, default PLA")}, ["path"])
def estimate_filament_usage(path, infill_percent=15, material="PLA"):
    from . import extras as EX; return EX.estimate(M().safe(path), infill_percent, material)

# ---- JSON-RPC ----
def _res(x, err=False):
    return {"content": [{"type": "text", "text": x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, indent=1)}], "isError": err}

def handle(msg, tok):
    if isinstance(msg, list): return [o for o in (handle(x, tok) for x in msg) if o] or None
    mid, meth, p = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if meth is None or mid is None: return None
    ok = lambda r: {"jsonrpc": "2.0", "id": mid, "result": r}
    er = lambda c, t: {"jsonrpc": "2.0", "id": mid, "error": {"code": c, "message": t}}
    if meth == "initialize":
        v = p.get("protocolVersion")
        return ok({"protocolVersion": v if v in VERS else VERS[0], "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "hAI.3DDir", "version": "1.0.0"},
                   "instructions": "Access to a 3D print file share (STL/3MF/OBJ) and a filament spool inventory. Paths are relative to the share root."})
    if meth == "ping": return ok({})
    if meth == "tools/list": return ok({"tools": [t["def"] for t in TOOLS.values() if not (tok.get("ro") and t["write"])]})
    if meth == "tools/call":
        t = TOOLS.get(p.get("name"))
        if not t: return er(-32602, "Unknown tool")
        if t["write"] and tok.get("ro"): return ok(_res("This token is read-only.", True))
        try:
            sig = inspect.signature(t["f"]).parameters
            return ok(_res(t["f"](**{k: v for k, v in (p.get("arguments") or {}).items() if k in sig})))
        except Exception as e: return ok(_res(str(getattr(e, "detail", None) or f"{type(e).__name__}: {e}"), True))
    return er(-32601, "Method not found")
