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