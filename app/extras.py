"""Verbrauchs-Schätzung aus Druckdateien und KI-Etikettenerkennung (OpenAI-kompatible API)."""
import os, re, io, json, math, base64, struct, zipfile, hashlib
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

def _mime(data):
    if data.startswith(b"\x89PNG"): return "image/png"
    if data.startswith(b"\xFF\xD8"): return "image/jpeg"
    if data.startswith(b"\x89PNG"): return "image/png"
    return "application/octet-stream"

def _dur(s):
    hours = minutes = seconds = 0
    m = re.search(r"(\d+)\s*h", s)
    if m: hours = int(m.group(1))
    m = re.search(r"(\d+)\s*m", s)
    if m: minutes = int(m.group(1))
    m = re.search(r"(\d+)\s*s", s)
    if m: seconds = int(m.group(1))
    return hours * 3600 + minutes * 60 + seconds

def slicer_info(path, cache_dir=None):
    """Extract slicer information from 3MF and G-Code files with caching."""
    if cache_dir:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        
    try:
        p = Path(path)
        if not p.is_file():
            return {"data": {}, "image": None}
        
        # Create cache key based on file content and metadata
        st = p.stat()
        cache_key = hashlib.sha1(f"{p.absolute()}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()
        
        # Try to load from cache
        cached_data = None
        cached_image = None
        if cache_dir:
            json_cache = cache_dir / f"{cache_key}.json"
            img_cache = cache_dir / f"{cache_key}.img"
            
            if json_cache.exists() and img_cache.exists():
                try:
                    cached_data = json.loads(json_cache.read_text("utf-8"))
                    cached_image = img_cache.read_bytes()
                except:
                    pass
        
        if cached_data is not None:
            return {"data": cached_data, "image": cached_image is not None}
        
        # Extract data from file
        data = {}
        image_data = None
        
        ext = p.suffix.lower()
        raw = p.read_bytes()
        
        if ext == ".3mf":
            z = zipfile.ZipFile(io.BytesIO(raw))
            
            # Extract embedded thumbnail
            for n in z.namelist():
                if n.startswith("thumbnails/") and n.endswith((".png", ".jpg", ".jpeg")):
                    image_data = z.read(n)
                elif "thumbnail" in n.lower():
                    image_data = z.read(n)
            
            # Extract slicer data from metadata
            for n in z.namelist():
                if n.lower().startswith("metadata/"):
                    content = z.read(n).decode("utf-8", "replace")
                    
                    if "slice_info.config" in n.lower():
                        # Parse slice info
                        root = ET.fromstring(content)
                        for elem in root.iter():
                            tag = elem.tag.split("}")[-1]
                            if tag == "prediction":
                                try:
                                    data["time_s"] = int(float(elem.text) * 3600) if float(elem.text) > 1000 else int(float(elem.text))
                                except:
                                    pass
                            elif tag == "weight":
                                try:
                                    data["grams"] = float(elem.text)
                                except:
                                    pass
                            elif tag == "filament" and elem.get("used_g"):
                                try:
                                    data["grams"] = float(elem.get("used_g"))
                                except:
                                    pass
                    
                    elif "project_settings.config" in n.lower():
                        # Parse project settings
                        settings = json.loads(content)
                        if "layer_height" in settings:
                            data["layer_h"] = settings["layer_height"]
                        if "printer_model" in settings:
                            data["printer"] = settings["printer_model"]
                        if "nozzle_diameter" in settings:
                            data["nozzle"] = settings["nozzle_diameter"]
                        if "filament_type" in settings:
                            data["material"] = settings["filament_type"]
                    
                    elif "slic3r_pe.config" in n.lower():
                        # Parse Prusa slicer settings
                        for line in content.split("\n"):
                            line = line.strip()
                            if line.startswith("layer_height ="):
                                data["layer_h"] = float(line.split("=", 1)[1].strip())
                            elif line.startswith("filament_type ="):
                                data["material"] = line.split("=", 1)[1].strip()
        
        elif ext == ".gcode":
            # Extract thumbnail from first/last 400KB
            preview_raw = raw[:400000] + b"\n" + raw[-400000:]
            
            # Find thumbnail
            thumb_match = re.search(r";\s*thumbnail(?:_JPG)? begin\s+(\d+)x(\d+)\s+\d+\s*\r?\n(.*?);\s*thumbnail(?:_JPG)? end", 
                                   preview_raw.decode("utf-8", "replace"), re.DOTALL | re.IGNORECASE)
            if thumb_match:
                width, height = int(thumb_match.group(1)), int(thumb_match.group(2))
                thumb_base64 = re.sub(r"\s*; ?", "", thumb_match.group(3))
                import base64
                try:
                    image_data = base64.b64decode(thumb_base64)
                except:
                    pass
            
            # Extract time estimation
            time_patterns = [
                r"estimated printing time \(normal mode\) = ([\d.]+(?:h|m|s)+)",
                r"total estimated time: ([\d.]+(?:h|m|s)+)",
                r";TIME:(\d+)"
            ]
            for pattern in time_patterns:
                time_match = re.search(pattern, raw.decode("utf-8", "replace"), re.IGNORECASE)
                if time_match:
                    time_str = time_match.group(1)
                    try:
                        data["time_s"] = _dur(time_str)
                        break
                    except:
                        pass
            
            # Extract grams
            grams_match = re.search(r";\s*filament used\s*:\s*([\d.]+)\s*g", raw.decode("utf-8", "replace"), re.IGNORECASE)
            if grams_match:
                try:
                    data["grams"] = float(grams_match.group(1))
                except:
                    pass
            
            # Extract other settings
            content = raw.decode("utf-8", "replace")
            if "layer_height" in content:
                layer_match = re.search(r";\s*layer_height\s*:\s*([\d.]+)\s*mm", content)
                if layer_match:
                    try:
                        data["layer_h"] = float(layer_match.group(1))
                    except:
                        pass
            
            nozzle_match = re.search(r";\s*nozzle_diameter\s*:\s*([\d.]+)\s*mm", content)
            if nozzle_match:
                try:
                    data["nozzle"] = float(nozzle_match.group(1))
                except:
                    pass
            
            filament_match = re.search(r";\s*filament_type\s*:\s*(.+)", content)
            if filament_match:
                data["material"] = filament_match.group(1).strip()
            
            printer_match = re.search(r";\s*printer_model\s*:\s*(.+)", content)
            if printer_match:
                data["printer"] = printer_match.group(1).strip()
        
        # Clean up data - only include non-empty fields
        data = {k: v for k, v in data.items() if v is not None}
        
        # Save to cache
        if cache_dir:
            try:
                json_cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
                if image_data:
                    img_cache.write_bytes(image_data)
            except:
                pass
        
        return {"data": data, "image": image_data is not None}
    
    except Exception as e:
        # Return empty data instead of error
        return {"data": {}, "image": None}

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
