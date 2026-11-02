import io, re, json, base64, zipfile, hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

def slicer_info(path,cache_dir=None):
    p=Path(path); empty={'data':{},'image':None}
    if not p.is_file() or p.stat().st_size>300*1048576: return empty
    cache=Path(cache_dir) if cache_dir else None
    key=hashlib.sha256(f'{p.resolve()}|{p.stat().st_mtime_ns}|{p.stat().st_size}'.encode()).hexdigest()
    if cache:
        cache.mkdir(parents=True,exist_ok=True); meta=cache/(key+'.json'); image=cache/(key+'.img')
        if meta.exists():
            try: return {'data':json.loads(meta.read_text()),'image':image.read_bytes() if image.exists() else None}
            except (ValueError,OSError): pass
    data={}; thumb=None
    try:
        if p.suffix.lower()=='.3mf':
            with zipfile.ZipFile(p) as z:
                if len(z.infolist())>2000: return empty
                budget=0
                for info in z.infolist():
                    n=info.filename.lower()
                    if info.file_size>5*1048576: continue
                    if not ('thumbnail' in n or n.endswith(('slice_info.config','project_settings.config'))): continue
                    budget+=info.file_size
                    if budget>20*1048576: break
                    raw=z.read(info)
                    if 'thumbnail' in n and n.endswith(('.png','.jpg','.jpeg')): thumb=raw
                    elif n.endswith('slice_info.config'):
                        xml=ET.fromstring(raw); grams=[]
                        for e in xml.iter():
                            if e.get('used_g'): grams.append(float(e.get('used_g')))
                            if e.get('key')=='prediction' and e.get('value'): data['time_s']=int(float(e.get('value')))
                            if e.tag.split('}')[-1]=='prediction' and e.text: data['time_s']=int(float(e.text))
                        if grams: data['grams']=sum(grams)
                    elif n.endswith('project_settings.config'):
                        cfg=json.loads(raw)
                        for source,target in [('layer_height','layer_h'),('printer_model','printer'),('nozzle_diameter','nozzle'),('filament_type','material')]:
                            if source in cfg: data[target]=cfg[source]
        elif p.suffix.lower() in ('.gcode','.gco'):
            with p.open('rb') as f:
                raw=f.read(400000)
                if p.stat().st_size>400000: f.seek(max(400000,p.stat().st_size-400000)); raw+=b'\n'+f.read(400000)
            text=raw.decode('utf-8','replace')
            match=re.search(r';TIME:(\d+)',text)
            if match: data['time_s']=int(match.group(1))
            else:
                match=re.search(r'estimated printing time.*?=([^\r\n]+)',text,re.I)
                if match: data['time_s']=sum(int(n)*{'h':3600,'m':60,'s':1}[u.lower()] for n,u in re.findall(r'(\d+)\s*([hms])',match.group(1),re.I))
            match=re.search(r'filament used \[g\]\s*=\s*([\d., ]+)',text,re.I)
            if match: data['grams']=sum(float(x) for x in re.findall(r'\d+(?:\.\d+)?',match.group(1)))
            else:
                match=re.search(r';\s*filament used\s*:\s*([\d.]+)\s*g',text,re.I)
                if match: data['grams']=float(match.group(1))
            match=re.search(r';\s*thumbnail(?:_JPG)? begin[^\n]*\n(.*?);\s*thumbnail(?:_JPG)? end',text,re.S|re.I)
            if match: thumb=base64.b64decode(''.join(line.lstrip('; ').strip() for line in match.group(1).splitlines()),validate=True)
        if thumb and not thumb.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff')): thumb=None
        if cache:
            if thumb: image.write_bytes(thumb)
            meta.write_text(json.dumps(data,allow_nan=False))
    except (ValueError,OSError,zipfile.BadZipFile,ET.ParseError): return empty
    return {'data':data,'image':thumb}
