"""Telegram-Bot mit Inline-Buttons (Long Polling, kein offener Port nötig)."""
import os, time, json, html, threading
from pathlib import Path
import httpx

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED = {int(x) for x in os.getenv("TELEGRAM_ALLOWED_IDS", "").replace(" ", "").split(",") if x.lstrip("-").isdigit()}
API = f"https://api.telegram.org/bot{TOKEN}"
H = httpx.Client(timeout=40)
S, BOT, PER, E = {}, {"name": ""}, 12, html.escape

def M():
    from . import main
    return main

def call(method, **kw):
    return H.post(f"{API}/{method}", json={k: v for k, v in kw.items() if v is not None}).json().get("result")
def b(t, d): return {"text": t, "callback_data": d}
def send(cid, text, rows=None):
    return call("sendMessage", chat_id=cid, text=text, parse_mode="HTML", reply_markup={"inline_keyboard": rows} if rows else None)
def show(cid, mid, text, rows):
    if mid: call("editMessageText", chat_id=cid, message_id=mid, text=text, parse_mode="HTML", reply_markup={"inline_keyboard": rows})
    else: send(cid, text, rows)
def notify(text):
    if TOKEN:
        for c in ALLOWED: threading.Thread(target=send, args=(c, text), daemon=True).start()
def st(cid): return S.setdefault(cid, {"cwd": "", "mode": "browse", "items": []})

def menu(cid, mid=None):
    show(cid, mid, "🧊 <b>hAI.3DDir</b>\nWas möchtest du tun?\n<i>Tipp: Schick mir eine Datei, dann lege ich sie im Ordner deiner Wahl ab.</i>",
         [[b("📁 Dateien", "fi"), b("🔎 Suche", "se")], [b("🧵 Filamente", "fl")]])

# ---- Dateien ----
def show_list(cid, mid, page, head):
    s = st(cid); items = s["items"]; ch = items[page * PER:(page + 1) * PER]
    rows = [[b(("📁 " if isd else "🧊 " if rel.lower().endswith((".stl", ".3mf", ".obj")) else "📄 ") + lab[:44], f"o:{k}")]
            for k, (rel, isd, lab) in enumerate(ch, page * PER)]
    nav = ([b("◀", f"p:{page - 1}")] if page else []) + ([b("▶", f"p:{page + 1}")] if (page + 1) * PER < len(items) else [])
    if nav: rows.append(nav)
    rows.append({"pick": [b("⬆ Hoch", "u"), b("✅ Hier speichern", "ps"), b("✖", "px")],
                 "search": [b("🔎 Neue Suche", "se"), b("🏠 Menü", "m")]}.get(s["mode"], [b("⬆ Hoch", "u"), b("🏠 Menü", "m")]))
    show(cid, mid, f"{head}\n{len(items)} Einträge", rows)

def view(cid, mid=None, page=0):
    s, m = st(cid), M(); pick = s["mode"] == "pick"; d = m.safe(s["cwd"])
    es = sorted((e for e in d.iterdir() if not e.name.startswith(".") and (e.is_dir() or not pick)), key=lambda e: (not e.is_dir(), e.name.lower()))
    s["items"] = [((s["cwd"] + "/" if s["cwd"] else "") + e.name, e.is_dir(), e.name) for e in es]
    show_list(cid, mid, page, f"{'📥 Zielordner wählen' if pick else '📂'} <code>/{E(s['cwd'])}</code>")

def send_file(cid, rel):
    p = M().safe(rel)
    if not p.is_file(): return send(cid, "Datei nicht gefunden.")
    if p.stat().st_size > 50 * 1048576:
        return send(cid, f"⚠️ {E(p.name)} ist größer als 50 MB, das erlaubt Telegram nicht. Bitte die Weboberfläche nutzen.")
    with open(p, "rb") as f:
        H.post(f"{API}/sendDocument", data={"chat_id": cid, "caption": p.name}, files={"document": (p.name, f)}, timeout=300)

def do_search(cid, q):
    s = st(cid); res = M().search(q)
    s.update(mode="search", items=[(r["path"], r["dir"], r["name"] + (" · /" + r["path"].rpartition("/")[0] if "/" in r["path"] else "")) for r in res])
    if not res: return send(cid, "Nichts gefunden.", [[b("🏠 Menü", "m")]])
    show_list(cid, None, 0, f"🔎 <b>{E(q)}</b>")

def on_doc(cid, doc):
    s, m = st(cid), M(); cfg = m.settings(); name = Path(doc.get("file_name") or "datei").name
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    ok = {x.strip().lower().lstrip(".") for x in cfg["allowed_ext"].split(",") if x.strip()}
    if ok and ext not in ok: return send(cid, f"⛔ Endung .{E(ext)} ist nicht erlaubt.")
    if doc.get("file_size", 0) > min(20, cfg["max_upload_mb"]) * 1048576:
        return send(cid, "⚠️ Bots können über Telegram nur Dateien bis 20 MB empfangen. Größere bitte über die Weboberfläche hochladen.")
    s.update(pending={"id": doc["file_id"], "name": name}, mode="pick"); view(cid)

def save_pending(cid):
    s, m = st(cid), M(); pd = s.pop("pending", None)
    if not pd: return send(cid, "Keine Datei ausstehend.")
    fp = call("getFile", file_id=pd["id"])["file_path"]; dest = m.safe(s["cwd"]) / m.clean(pd["name"]); n = 1
    while dest.exists(): dest = dest.with_name(f"{Path(pd['name']).stem} ({n}){Path(pd['name']).suffix}"); n += 1
    with H.stream("GET", f"https://api.telegram.org/file/bot{TOKEN}/{fp}") as r, open(dest, "wb") as o:
        for c in r.iter_bytes(1 << 20): o.write(c)
    s["mode"] = "browse"; send(cid, f"✅ Gespeichert: <code>/{E(dest.relative_to(m.ROOT).as_posix())}</code>", [[b("🏠 Menü", "m")]])

# ---- Filamente ----
def bar(p): n = round(p / 10); return "▓" * n + "░" * (10 - n)
def fil_list(cid, mid=None):
    m = M(); l = m.load(m.FF, []); thr = m.settings()["tg_low_g"]
    if not l: return show(cid, mid, "Noch keine Rollen. Lege sie in der Weboberfläche an.", [[b("🏠 Menü", "m")]])
    rows = [[b(f"{'⚠️' if r['weight_remaining'] <= thr else '🧵'} {r['brand']} {r['material']} {r['color_name']} · {r['weight_remaining']:g} g"[:60], f"fd:{r['id']}")] for r in l[:40]]
    show(cid, mid, f"🧵 <b>Filamente</b> ({len(l)} Rollen)\n⚠️ = höchstens {thr} g Rest", rows + [[b("🏠 Menü", "m")]])
def fil_detail(cid, mid, fid):
    m = M(); r = next((x for x in m.load(m.FF, []) if x["id"] == fid), None)
    if not r: return fil_list(cid, mid)
    p = r["weight_remaining"] / r["weight_total"] * 100 if r["weight_total"] else 0
    txt = (f"🧵 <b>{E(r['material'])}</b> · {E(r['color_name'])}\n{E(r['brand'])}\n{bar(min(p, 100))} {p:.0f} %\n"
           f"Rest: <b>{r['weight_remaining']:g}</b> / {r['weight_total']:g} g" + (f"\n📝 {E(r['notes'])}" if r["notes"] else ""))
    show(cid, mid, txt, [[b(f"−{g} g", f"fa:{fid}:{g}") for g in (10, 50, 100)], [b("✏️ Wert setzen", f"fs:{fid}")], [b("⬅ Liste", "fl"), b("🏠 Menü", "m")]])
def setrem(fid, fn):
    m = M(); l = m.load(m.FF, [])
    for r in l:
        if r["id"] == fid:
            prev = r["weight_remaining"]; r["weight_remaining"] = max(0.0, round(fn(prev), 1)); m.save(m.FF, l); low(r, prev); return r
def low(r, prev):
    s = M().settings(); t = s["tg_low_g"]
    if s["tg_notify_low"] and prev > t >= r["weight_remaining"]:
        notify(f"⚠️ <b>Wenig Filament:</b> {E(r['brand'])} {E(r['material'])} {E(r['color_name'])}: nur noch {r['weight_remaining']:g} g")
def upload_note(names, path):
    if M().settings()["tg_notify_upload"]: notify(f"⬆️ Upload: <b>{E(', '.join(names))}</b> → <code>/{E(path or '')}</code>")

# ---- Routing ----
def route(cid, mid, d):
    s = st(cid); a, _, x = d.partition(":")
    if a == "m": s.pop("await", None); menu(cid, mid)
    elif a == "fi": s.update(cwd="", mode="browse"); view(cid, mid)
    elif a == "u": s["cwd"] = s["cwd"].rpartition("/")[0]; s["mode"] = "pick" if s["mode"] == "pick" else "browse"; view(cid, mid)
    elif a == "p": show_list(cid, mid, int(x), "🔎 Suchergebnisse") if s["mode"] == "search" else view(cid, mid, int(x))
    elif a == "o":
        rel, isd, _ = s["items"][int(x)]
        if isd: s["cwd"] = rel; s["mode"] = "pick" if s["mode"] == "pick" else "browse"; view(cid, mid)
        else: send_file(cid, rel)
    elif a == "se": s["await"] = "search"; send(cid, "🔎 Schick mir den Suchbegriff (mindestens 2 Zeichen).")
    elif a == "ps": save_pending(cid)
    elif a == "px": s.pop("pending", None); s["mode"] = "browse"; menu(cid, mid)
    elif a == "fl": fil_list(cid, mid)
    elif a == "fd": fil_detail(cid, mid, x)
    elif a == "fa":
        fid, g = x.split(":")
        if setrem(fid, lambda v: v - float(g)): fil_detail(cid, mid, fid)
    elif a == "fs": s["await"] = "w:" + x; send(cid, "✏️ Neues Restgewicht in Gramm senden.")

def handle(u):
    cq = u.get("callback_query"); msg = cq["message"] if cq else u.get("message")
    if not msg: return
    uid, cid = (cq or msg)["from"]["id"], msg["chat"]["id"]
    if uid not in ALLOWED:
        if not cq: send(cid, f"⛔ Nicht freigegeben. Deine ID: <code>{uid}</code>")
        return
    if cq:
        call("answerCallbackQuery", callback_query_id=cq["id"]); return route(cid, msg["message_id"], cq["data"])
    if "document" in msg: return on_doc(cid, msg["document"])
    t = (msg.get("text") or "").strip(); aw = st(cid).pop("await", None); cmd, _, arg = t.partition(" ")
    if cmd == "/files": st(cid).update(cwd="", mode="browse"); view(cid)
    elif cmd == "/filament": fil_list(cid)
    elif cmd == "/search" and arg: do_search(cid, arg)
    elif cmd == "/search": st(cid)["await"] = "search"; send(cid, "🔎 Suchbegriff?")
    elif aw == "search" and not t.startswith("/"): do_search(cid, t)
    elif aw and aw.startswith("w:") and not t.startswith("/"):
        try: v = float(t.replace(",", "."))
        except ValueError: return send(cid, "Bitte eine Zahl senden.")
        setrem(aw[2:], lambda _: v); fil_detail(cid, None, aw[2:])
    else: menu(cid)

def loop():
    off = 0
    while not BOT["name"]:
        try:
            call("deleteWebhook"); BOT["name"] = (call("getMe") or {}).get("username", "")
            call("setMyCommands", commands=[{"command": "menu", "description": "Hauptmenü"}, {"command": "files", "description": "Dateien"},
                 {"command": "search", "description": "Suchen"}, {"command": "filament", "description": "Filamente"}])
        except Exception: time.sleep(10)
    while True:
        try:
            r = H.get(f"{API}/getUpdates", params={"timeout": 30, "offset": off, "allowed_updates": json.dumps(["message", "callback_query"])}, timeout=40).json()
            for u in r.get("result", []):
                off = u["update_id"] + 1
                try: handle(u)
                except Exception as e: print("telegram:", repr(e), flush=True)
        except Exception: time.sleep(5)

def start():
    if TOKEN and ALLOWED: threading.Thread(target=loop, daemon=True).start()
    elif TOKEN: print("Telegram: TELEGRAM_ALLOWED_IDS fehlt, Bot bleibt aus", flush=True)
def status(): return {"enabled": bool(TOKEN and ALLOWED), "token": bool(TOKEN), "allowed": len(ALLOWED), "bot": BOT["name"]}
