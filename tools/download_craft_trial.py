import json,urllib.request,hashlib
from pathlib import Path
repo='boomb0om/CRAFT-text-detector'
info=json.load(urllib.request.urlopen('https://huggingface.co/api/models/'+repo,timeout=25));revision=info['sha']
url=f'https://huggingface.co/{repo}/resolve/{revision}/craft_mlt_25k.pth'
path=Path('data/model-trials/models/easyocr/craft_mlt_25k.pth')
with urllib.request.urlopen(url,timeout=60) as r,path.open('wb') as f:
 while True:
  b=r.read(1024*1024)
  if not b:break
  f.write(b)
payload=path.read_bytes();md5=hashlib.md5(payload).hexdigest()
if md5!='2f8227d2def4037cdb3b34389dcf9ec1':raise RuntimeError('CRAFT checkpoint does not match EasyOCR official checksum; do not load')
Path('evidence/model-trials/craft-download.json').write_text(json.dumps(dict(url=url,revision=revision,sha256=hashlib.sha256(payload).hexdigest(),official_easyocr_md5=md5,checksum_match=True,reason='Official GitHub release download stalled; mirror verified before use'),indent=2),'utf-8')
print('CRAFT checkpoint verified against official EasyOCR checksum')
