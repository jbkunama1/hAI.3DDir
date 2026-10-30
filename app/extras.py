"""Verbrauchs-Schätzung aus Druckdateien und KI-Etikettenerkennung (OpenAI-kompatible API)."""
import os, re, io, json, math, base64, struct, zipfile
import xml.etree.ElementTree as ET
import httpx

BASE = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
API_KEY = os.getenv("LLM_API_KEY", "").strip()
MODEL = os.getenv("LLM_MODEL", "").strip()
VERIFY = os.getenv("LLM_VERIFY_TLS", "true").lower() not in ("0", "false", "no")
DENS = {"pla": 1.24, "petg": 1.27, "tpu": 1.21, "abs": 1.04, "asa": 1.07, "pa": 1.14, "pc": 1.20}
UNITS = {"micron": .001, "millimeter": 1, "centimeter": 10, "inch": 25.4, "foot": 304.8, "meter": 1000}
def density(m): m = m.lower().strip(); return next((d for k, d in DENS.items() if m.startswith(k)), 1.24)

def _stl(raw):
    if len(raw) >= 84:
        n = struct.unpack_from("<I", raw, 80)[0]
        if 84 + n * 50 == len(raw):
            for f in struct.iter_unpack("<12fH", raw[84:]): yield f[3:6], f[6:9], f[9:12]
            return
    v = [tuple(map(float, m)) for m in re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", raw)]
    for i in range(0, len(v) - 2, 3): yield v[i], v[i + 1], v[i + 2]

def _obj(raw):
    vs = []
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith("v "): vs.append(tuple(map(float, line.split()[1:4])))
        elif line.startswith("f "):
            ids = [int(x.split("/")[0]) for x in line.split()[1:]]; ids = [i - 1 if i > 0 else len(vs) + i for i in ids]
            for k in range(1, len(ids) - 1): yield vs[ids[0]], vs[ids[k]], vs[ids[k + 1]]

def _3mf(z):
    for n in z.namelist():
        if not n.lower().endswith(".model"): continue
        root = ET.fromstring(z.read(n)); sc = UNITS.get(root.get("unit", "millimeter"), 1)
        for mesh in (e for e in root.iter() if e.tag.split("}")[-1] == "mesh"):
            vs, ts = [], []
            for e in mesh.iter():
                t = e.tag.split("}")[-1]
                if t == "vertex": vs.append((float(e.get("x")) * sc, float(e.get("y")) * sc, float(e.get("z")) * sc))
                elif t == "triangle": ts.append((int(e.get("v1")), int(e.get("v2")), int(e.get("v3"))))
            for a, b, c in ts: yield vs[a], vs[b], vs[c]

def _gcode(raw):
    t = (raw[:300000] + b"\n" + raw[-300000:]).decode("utf-8", "replace")
    m = re.search(r"filament used \[g\]\s*=\s*([\d., ]+)", t) or re.search(r"total filament weight \[g\]\s*:\s*([\d., ]+)", t)
    if m: return sum(float(x) for x in re.findall(r"\d+(?:\.\d+)?", m.group(1)))
    m = re.search(r";\s*Filament used:\s*([\d.]+)\s*m", t, re.I)
    return float(m.group(1)) * 1000 * math.pi * (1.75 / 2) ** 2 * 1.24 / 1000 if m else None

def estimate(p, infill=15, material="PLA"):
    if not p.is_file(): raise ValueError("Datei nicht gefunden")
    if p.stat().st_size > 300 * 1048576: raise ValueError("Datei zu groß für die Schätzung")
    ext, raw = p.suffix.lower(), p.read_bytes()
    if ext in (".gcode", ".gco"):
        g = _gcode(raw)
        if g is None: raise ValueError("Im G-Code steht kein Filamentverbrauch")
        return {"grams": round(g, 1), "method": "gcode", "note": "Exakter Wert aus den G-Code-Kommentaren des Slicers"}
    if ext == ".3mf":
        z = zipfile.ZipFile(io.BytesIO(raw)); info = next((n for n in z.namelist() if n.lower().endswith("slice_info.config")), None)
        if info:
            g = sum(float(x) for x in re.findall(r'used_g="([\d.]+)"', z.read(info).decode("utf-8", "replace")))
            if g > 0: return {"grams": round(g, 1), "method": "3mf-slice", "note": "Exakter Wert aus den Slicer-Daten der 3MF"}
        tris = _3mf(z)
    elif ext == ".stl": tris = _stl(raw)
    elif ext == ".obj": tris = _obj(raw)
    else: raise ValueError("Unterstützt: STL, 3MF, OBJ und G-Code")
    vol = area = 0.0; mn = [1e18] * 3; mx = [-1e18] * 3; n = 0
    for a, b, c in tris:
        n += 1
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
        ux, uy, uz, vx, vy, vz = b[0] - a[0], b[1] - a[1], b[2] - a[2], c[0] - a[0], c[1] - a[1], c[2] - a[2]
        area += math.sqrt((uy * vz - uz * vy) ** 2 + (uz * vx - ux * vz) ** 2 + (ux * vy - uy * vx) ** 2) / 2
        for v in (a, b, c):
            for k in (0, 1, 2):
                if v[k] < mn[k]: mn[k] = v[k]
                if v[k] > mx[k]: mx[k] = v[k]
    if not n: raise ValueError("Keine Geometrie gefunden")
    vol = abs(vol); shell = min(vol, area * 1.2); g = (shell + (vol - shell) * infill / 100) / 1000 * density(material)
    return {"grams": round(g, 1), "method": "mesh", "volume_cm3": round(vol / 1000, 2), "size_mm": [round(mx[k] - mn[k], 1) for k in range(3)],
            "note": f"Geschätzt aus dem Modell ({vol / 1000:.1f} cm³, {infill:g} % Infill, Wand 1,2 mm, {material}), ohne Support, ±20 %"}

def enabled(): return bool(BASE and MODEL)

def ai_label(img, media="image/jpeg"):
    if not enabled(): raise ValueError("LLM_BASE_URL und LLM_MODEL sind nicht gesetzt")
    prompt = ('Read the label or packaging of this 3D printer filament spool. Reply with ONLY a JSON object with the keys: brand, '
              'material (e.g. PLA, PLA+, PLA Silk, PLA Matte, PETG, TPU, ABS, ASA), color_name, color_hex (best guess #RRGGBB of the filament color), '
              'weight_total (grams as a number, e.g. 1000), barcode (digits of the EAN/UPC if readable, else ""), notes (e.g. diameter, print temperature). '
              'Use "" or 0 for unknown values.')
    url = BASE if BASE.endswith("/chat/completions") else BASE + "/chat/completions"
    r = httpx.post(url, timeout=120, verify=VERIFY, headers={"Authorization": f"Bearer {API_KEY}"} if API_KEY else {},
                   json={"model": MODEL, "max_tokens": 600, "temperature": 0, "messages": [{"role": "user", "content": [
                       {"type": "text", "text": prompt},
                       {"type": "image_url", "image_url": {"url": f"data:{media};base64,{base64.b64encode(img).decode()}"}}]}]})
    if r.status_code >= 400: raise ValueError(f"LLM-Fehler {r.status_code}: {r.text[:200]}")
    txt = r.json()["choices"][0]["message"]["content"]
    if isinstance(txt, list): txt = "".join(p.get("text", "") for p in txt)
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m: raise ValueError("Das Modell hat keine lesbare Antwort geliefert (Vision-Modell nötig)")
    d = json.loads(m.group(0)); hx = str(d.get("color_hex", ""))
    d["color_hex"] = hx if re.fullmatch(r"#[0-9a-fA-F]{6}", hx) else "#888888"
    try: d["weight_total"] = float(d.get("weight_total") or 1000) or 1000
    except (TypeError, ValueError): d["weight_total"] = 1000
    d["weight_remaining"] = d["weight_total"]
    return {k: d.get(k, "") for k in ("brand", "material", "color_name", "color_hex", "weight_total", "weight_remaining", "barcode", "notes")}
