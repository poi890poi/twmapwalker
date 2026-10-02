"""Install the exact public source snapshots used by the multi-evidence trial.

Downloads ~269 MB once. Run with the project Python and requirements-terrain.txt.
Updated upstream content is rejected until a new provenance record is reviewed.
"""
import argparse
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mapwalker.paths import default_data

CSV_URLS={
    'natural-places.csv':'https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/50ACF0B4-D215-463F-8813-5164027D59D3/resource/612C5E23-CB53-44BE-87DA-9E72F0032661/download',
    'dtm-catalog.csv':'https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/A964612F-0D64-4C81-BFE5-6C1F2BA61DED/resource/A0B94F67-8ADF-48A1-8DF0-C60719AD2B28/download',
}


def verified(path,expected):
    if not path.is_file() or path.stat().st_size!=expected['bytes']:return False
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()==expected['sha256']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=default_data())
    args=parser.parse_args();folder=args.data/'multi-evidence';folder.mkdir(parents=True,exist_ok=True)
    provenance=json.loads((ROOT/'evidence/multi-evidence/provenance.json').read_text('utf-8'))
    files={f['file']:f for f in provenance['files']}
    for name in ('natural-places.csv','dtm-catalog.csv','taiwan-20m-2025.zip'):
        entry=files[name];target=folder/name
        if verified(target,entry):continue
        print('Downloading',name,flush=True)
        url=CSV_URLS.get(name,entry['url'])
        from urllib.parse import quote,urlsplit,urlunsplit
        parts=urlsplit(url);url=urlunsplit((parts.scheme,parts.netloc,quote(parts.path),parts.query,''))
        temporary=target.with_suffix(target.suffix+'.partial');size=0
        with urllib.request.urlopen(url,timeout=120) as response,temporary.open('wb') as out:
            while chunk:=response.read(1024*1024):
                size+=len(chunk)
                if size>entry['bytes']:raise ValueError('Upstream source changed size; review before installing')
                out.write(chunk)
        if not verified(temporary,entry):raise ValueError('Upstream source changed hash; review before installing')
        temporary.replace(target)
    name='DEM_tawiwan_V2025.tif';target=folder/name
    if not verified(target,files[name]):
        temporary=target.with_suffix('.partial')
        with zipfile.ZipFile(folder/'taiwan-20m-2025.zip') as archive,archive.open(name) as source,temporary.open('wb') as out:
            import shutil
            shutil.copyfileobj(source,out,1024*1024)
        if not verified(temporary,files[name]):raise ValueError('Terrain extraction hash mismatch')
        temporary.replace(target)
    manifest={key:{**files[name],'license':provenance['license'],'attribution':attribution} for key,name,attribution in [
        ('gazetteer','natural-places.csv','Taiwan Ministry of the Interior, natural geographical names, 2026'),
        ('terrain','DEM_tawiwan_V2025.tif','Taiwan Ministry of the Interior, 2025 mainland DTM')]}
    temporary=folder/'sources.json.partial';temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    temporary.replace(folder/'sources.json')
    print('Installed verified gazetteer and native 20 m DTM. Restart the viewer to reload sources.')


if __name__=='__main__':main()
