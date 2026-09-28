import json,hashlib,urllib.request,time
from pathlib import Path
root=Path('data/model-trials/models');root.mkdir(exist_ok=True)
manifest=[]
for repo,files in [('kha-white/manga-ocr-base',['config.json','preprocessor_config.json','pytorch_model.bin','vocab.txt','tokenizer_config.json','special_tokens_map.json']),('facebook/dinov2-small',['config.json','preprocessor_config.json','model.safetensors'])]:
 info=json.load(urllib.request.urlopen('https://huggingface.co/api/models/'+repo));revision=info['sha'];folder=root/repo.split('/')[-1];folder.mkdir(exist_ok=True)
 for name in files:
  url=f'https://huggingface.co/{repo}/resolve/{revision}/{name}';path=folder/name
  if not path.exists():
   with urllib.request.urlopen(url,timeout=120) as r,path.open('wb') as f:
    while True:
     block=r.read(1024*1024)
     if not block:break
     f.write(block)
  manifest.append(dict(repo=repo,revision=revision,file=name,url=url,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
  print(repo,name,path.stat().st_size,flush=True)
Path('evidence/model-trials/downloads.json').write_text(json.dumps(manifest,indent=2),'utf-8')
