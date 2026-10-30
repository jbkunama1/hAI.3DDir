"""Telegram-Bot mit Inline-Buttons (Long Polling, kein offener Port nötig)."""
import os, re, time, json, html, threading
from pathlib import Path
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED = {int(x) for x in os.getenv("TELEGRAM_ALLOWED_IDS", "").replace(" ", "").split(",") if x.lstrip("-").isdigit()}
API = f"https://api.telegram.org/bot{TOKEN}"
ADMIN = {int(x) for x in os.getenv("TELEGRAM_ADMIN_IDS", "").replace(" ", "").split(",") if x.lstrip("-").isdigit()} or ALLOWED
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
         [[b("📁 Dateien", "fi"), b("🔎 Suche", "se")], [b("🧵 Filamente", "fl")] + ([b("🛠 Admin", "ad")] if cid in ADMIN else [])])

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
           f"Rest: <b>{r['weight_remaining']:g}</b> / {r['weight_total']:g} g" + (f"\n🏷 {E(r['barcode'])}" if r.get("barcode") else "") + (f"\n📝 {E(r['notes'])}" if r["notes"] else ""))
    show(cid, mid, txt, [[b(f"−{g} g", f"fa:{fid}:{g}") for g in (10, 50, 100)], [b("🖨 Druck buchen", f"fp:{fid}"), b("✏️ Wert setzen", f"fs:{fid}")], [b("📷 Foto setzen", f"fi2:{fid}")] + ([b("🖼 Foto", f"fv:{fid}")] if r.get("image") else []), [b("⬅ Liste", "fl"), b("🏠 Menü", "m")]])
def setrem(fid, fn):
    m = M(); l = m.load(m.FF, [])
    for r in l:
        if r["id"] == fid:
            prev = r["weight_remaining"]; r["weight_remaining"] = max(0.0, round(fn(prev), 1)); m.save(m.FF, l); low(r, prev); return r
def low(r, prev): pass  # Warnungen bei wenig Filament sind entfernt
def upload_note(names, path):
    if M().settings()["tg_notify_upload"]: notify(f"⬆️ Upload: <b>{E(', '.join(names))}</b> → <code>/{E(path or '')}</code>")

def on_photo(cid, photos):
    s = st(cid); aw = s.pop("await", None) or ""
    if not aw.startswith("img:"): return send(cid, "Zum Hinterlegen: Rolle öffnen, dann 📷 Foto setzen.")
    fp = call("getFile", file_id=photos[-1]["file_id"])["file_path"]
    M().set_image(aw[4:], H.get(f"https://api.telegram.org/file/bot{TOKEN}/{fp}").content, "image/jpeg")
    send(cid, "✅ Foto gespeichert."); fil_detail(cid, None, aw[4:])
def send_img(cid, fid):
    m = M(); r = next((x for x in m.load(m.FF, []) if x["id"] == fid), None)
    if r and r.get("image"):
        with open(m.IMG / r["image"], "rb") as f: H.post(f"{API}/sendPhoto", data={"chat_id": cid}, files={"photo": (r["image"], f)}, timeout=60)

# ---- Bericht, Backup, Zeitplan ----
def now():
    try: return datetime.now(ZoneInfo(os.getenv("TZ", "Europe/Berlin")))
    except Exception: return datetime.now()
def fmtb(n): return f"{n / 1e9:.1f} GB" if n > 1e9 else f"{n / 1e6:.0f} MB"
def report():
    m = M(); thr = m.settings()["tg_low_g"]; s = m.stats(); l = m.load(m.FF, []); lo = [r for r in l if r["weight_remaining"] <= thr]
    body = (f"📁 {s['files']} Dateien, {fmtb(s['bytes'])} belegt, {fmtb(s['free'])} frei\n🗑 {s['trash']} im Papierkorb\n"
            f"🧵 {len(l)} Rollen, {sum(r['weight_remaining'] for r in l) / 1000:.2f} kg Rest")
    if lo: body += f"\n⚠️ Höchstens {thr} g Rest:\n" + "\n".join(f"• {E(r['brand'])} {E(r['material'])} {E(r['color_name'])}: {r['weight_remaining']:g} g" for r in lo[:10])
    return body, [[b("🧵 Filamente", "fl"), b("📁 Dateien", "fi")], [b("🛠 Admin", "ad")]]
def send_backup(cid, cap="💾 Backup Filament-DB"):
    m = M(); p = m.make_backup()
    try:
        big = os.path.getsize(p) > 45 * 1048576 and m.FF.exists()
        with open(m.FF if big else p, "rb") as f:
            H.post(f"{API}/sendDocument", data={"chat_id": cid, "caption": cap}, files={"document": (f"filamente-{now():%Y%m%d}." + ("json" if big else "zip"), f)}, timeout=300)
    finally: os.unlink(p)
def sched():
    m = M(); sf = m.DATA / "telegram_state.json"
    while not BOT["name"]: time.sleep(5)
    try:
        n, s = now(), m.settings()
        if s["tg_notify_start"]:
            body, rows = report()
            for c in ALLOWED: send(c, f"🟢 <b>hAI.3DDir gestartet</b> ({n:%d.%m.%Y %H:%M})\n" + body, rows)
        if n.strftime("%H:%M") >= s["tg_daily_time"]: m.save(sf, {**m.load(sf, {}), "daily": n.strftime("%Y-%m-%d")})
    except Exception as e: print("telegram start:", repr(e), flush=True)
    while True:
        try:
            n, s, stt = now(), m.settings(), m.load(sf, {})
            if s["tg_daily"] and n.strftime("%H:%M") >= s["tg_daily_time"] and stt.get("daily") != n.strftime("%Y-%m-%d"):
                m.save(sf, {**stt, "daily": n.strftime("%Y-%m-%d")}); body, rows = report()
                for c in ALLOWED: send(c, f"📊 <b>Tagesbericht</b> ({n:%d.%m.%Y})\n" + body, rows)
                if s["tg_daily_backup"]:
                    for c in ADMIN: send_backup(c, "💾 Tägliches Backup der Filament-DB")
        except Exception as e: print("telegram daily:", repr(e), flush=True)
        time.sleep(30)

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
    elif a == "fp": s["await"] = "b:" + x; send(cid, "🖨 Verbrauch in Gramm senden, optional mit Namen, z. B. <code>45 Benchy</code>")
    elif a == "fi2": s["await"] = "img:" + x; send(cid, "📷 Schick mir jetzt das Foto der Rolle.")
    elif a == "fv": send_img(cid, x)
    elif a in ("ad", "ab", "ar", "at", "aty") and cid not in ADMIN: send(cid, "⛔ Nur für Admins.")
    elif a == "ad": show(cid, mid, "🛠 <b>Admin</b>", [[b("💾 Backup Filament-DB", "ab")], [b("📊 Bericht jetzt", "ar"), b("🗑 Papierkorb leeren", "at")], [b("🏠 Menü", "m")]])
    elif a == "ab": send_backup(cid)
    elif a == "ar": body, rows = report(); send(cid, f"📊 <b>Bericht</b> ({now():%d.%m.%Y %H:%M})\n" + body, rows)
    elif a == "at": show(cid, mid, "🗑 Papierkorb wirklich endgültig leeren?", [[b("✅ Ja, leeren", "aty"), b("✖ Abbrechen", "ad")]])
    elif a == "aty": M().trash_purge(M().IDs(id="")); show(cid, mid, "✅ Papierkorb geleert.", [[b("⬅ Admin", "ad")]])

def handle(u):
    cq = u.get("callback_query"); msg = cq["message"] if cq else u.get("message")
    if not msg: return
    uid, cid = (cq or msg)["from"]["id"], msg["chat"]["id"]
    if uid not in ALLOWED:
        if not cq: send(cid, f"⛔ Nicht freigegeben. Deine ID: <code>{uid}</code>")
        return
    if cq:
        call("answerCallbackQuery", callback_query_id=cq["id"]); return route(cid, msg["message_id"], cq["data"])
    if "photo" in msg: return on_photo(cid, msg["photo"])
    if "document" in msg: return on_doc(cid, msg["document"])
    t = (msg.get("text") or "").strip(); aw = st(cid).pop("await", None); cmd, _, arg = t.partition(" ")
    if cmd == "/files": st(cid).update(cwd="", mode="browse"); view(cid)
    elif cmd == "/filament": fil_list(cid)
    elif cmd == "/search" and arg: do_search(cid, arg)
    elif cmd == "/search": st(cid)["await"] = "search"; send(cid, "🔎 Suchbegriff?")
    elif aw == "search" and not t.startswith("/"): do_search(cid, t)
    elif aw and aw.startswith("b:") and not t.startswith("/"):
        mt = re.match(r"([\d.,]+)\s*(.*)", t)
        if not mt: return send(cid, "Bitte so: <code>45 Benchy</code>")
        try: res = M().print_add({"filament_id": aw[2:], "grams": float(mt.group(1).replace(",", ".")), "name": mt.group(2)})
        except Exception as e: return send(cid, "⚠️ " + E(str(getattr(e, "detail", e))))
        send(cid, f"✅ {res['print']['grams']:g} g gebucht."); fil_detail(cid, None, aw[2:])
    elif not aw and not t.startswith("/") and re.fullmatch(r"(?=.*\d)\S{6,}", t) and M().find_barcode(t):
        fil_detail(cid, None, M().find_barcode(t)["id"])
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
    if TOKEN and ALLOWED: threading.Thread(target=loop, daemon=True).start(); threading.Thread(target=sched, daemon=True).start()
    elif TOKEN: print("Telegram: TELEGRAM_ALLOWED_IDS fehlt, Bot bleibt aus", flush=True)
def status(): return {"enabled": bool(TOKEN and ALLOWED), "token": bool(TOKEN), "allowed": len(ALLOWED), "bot": BOT["name"]}
