"""Bounded named OSM path snapshot, outside production discovery."""
import hashlib,json,time,urllib.request,urllib.parse
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'evidence/trail-area-comparison'
QUERY='[out:json][timeout:60];way["name"~"哈盆|能高|浸水營"](21.8,120.0,25.4,122.0);out body geom;'
if __name__=='__main__':
    target=OUT/'overpass.json'
    if target.exists():
        print('Reusing frozen snapshot')
    else:
        endpoint='https://overpass-api.de/api/interpreter'
        req=urllib.request.Request(endpoint,data=urllib.parse.urlencode({'data':QUERY}).encode(),headers={'User-Agent':'Mapwalker historical map research'})
        with urllib.request.urlopen(req,timeout=100) as response:raw=response.read()
        data=json.loads(raw)
        if data.get('remark'):raise RuntimeError(data['remark'])
        target.write_bytes(raw)
        (OUT/'provenance.json').write_text(json.dumps(dict(query=QUERY,endpoint=endpoint,fetched_at=time.time(),sha256=hashlib.sha256(raw).hexdigest(),osm_base=data.get('osm3s')),indent=2),encoding='utf8')
    data=json.loads(target.read_bytes())
    for e in data['elements']:
        g=e.get('geometry',[])
        print(e['id'],e.get('tags',{}).get('name'),e.get('tags',{}).get('highway'),len(g),g[len(g)//2] if g else '')
