"""On-demand pixel readings. No annotations, modern names, or database writes."""
import hashlib
import io
import math
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np
from PIL import Image

JAPANESE_FILE = 'japan_PP-OCRv4_rec_mobile.onnx'
JAPANESE_SHA256 = 'e1075a67dba758ecfc7ebc78a10ae61c95ac8fb66a9c86fab5541e33f085cb7a'
JAPANESE_URL = 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/rec/' + JAPANESE_FILE


def evidence_crop(data, item, padding, *, cover_box=True):
    """Read exactly the recorded imagery; never fetch missing tiles or use labels."""
    box = item['box']
    if len(box)!=4 or not all(math.isfinite(v) for v in box):
        raise ValueError('Invalid detection box')
    # The recognition-only baseline truncates the right/bottom edges. Preserve
    # those exact pixels; even one background row changes isolated-glyph scores.
    end=math.ceil if cover_box else math.floor
    bounds = [math.floor(box[0])-padding, math.floor(box[1])-padding,
              end(box[2])+padding, end(box[3])+padding]
    width,height = bounds[2]-bounds[0],bounds[3]-bounds[1]
    if not (0<width<=768 and 0<height<=768):
        raise ValueError('Select a smaller text fragment to read')
    records = {(m['source'],m['z'],m['x'],m['y']):m for m in item['manifest']}
    root = Path(data)/'tiles'/item['spec']['snapshot']
    image = Image.new('RGB',(width,height),'white');provenance=[]
    for dy in range(math.floor(bounds[1]/256),math.ceil(bounds[3]/256)):
        for dx in range(math.floor(bounds[0]/256),math.ceil(bounds[2]/256)):
            key = (item['source'],item['z'],item['x']+dx,item['y']+dy)
            record = records.get(key)
            if record is None:raise ValueError('The recorded map context does not cover this crop')
            path = root/key[0]/str(key[1])/str(key[2])/record['file']
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=record['sha256']:
                raise ValueError('Original evidence input hash mismatch')
            with Image.open(io.BytesIO(payload)) as tile:
                if tile.size!=(256,256):raise ValueError('Unexpected tile size')
                rgba=tile.convert('RGBA');rgb=Image.new('RGB',tile.size,'white');rgb.paste(rgba,mask=rgba.getchannel('A'))
                image.paste(rgb,(dx*256-bounds[0],dy*256-bounds[1]))
            provenance.append({k:record[k] for k in ('source','z','x','y','sha256')})
    local=[box[0]-bounds[0],box[1]-bounds[1],box[2]-bounds[0],box[3]-bounds[1]]
    return image,local,provenance


def unrotate_box(box,angle,width,height):
    x0,y0,x1,y1=box
    if angle==90:return [width-y1,x0,width-y0,x1]
    if angle==180:return [width-x1,height-y1,width-x0,height-y0]
    if angle==270:return [y0,height-x1,y1,height-x0]
    return list(box)


def overlaps(a,b):
    area=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    smaller=min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
    return area/max(1,smaller)>=.25


def read_pixels(image,box,mode,engine):
    """Keep uncertainty visible: exact transcripts, no digit repairs or name lookup."""
    readings=[]
    for angle in (0,90,180,270):
        patch=image.rotate(angle,expand=True,fillcolor='white')
        if mode=='numbers':
            rows=engine(patch)
            for row in rows:
                mapped=unrotate_box(row['box'],angle,*image.size)
                text=row['text'].strip()
                if (row['score']>=.65 and re.fullmatch(r'[0-9]{2,5}(?:[.,][0-9]+)?[.,]?',text)
                        and overlaps(mapped,box)):
                    readings.append(dict(text=text,score=row['score'],angle=angle,box=mapped))
        else:
            rows,_=engine(np.asarray(patch)[:,:,::-1].copy(),use_det=False,use_cls=False)
            for text,score in rows or []:
                if score>=.65 and len(text)<=40 and re.search(r'[\u3041-\u3096\u30a1-\u30fa]',text):
                    readings.append(dict(text=text,score=float(score),angle=angle))
    seen=set();result=[]
    for row in sorted(readings,key=lambda r:r['score'],reverse=True):
        if row['text'] not in seen:result.append(row);seen.add(row['text'])
    return result[:8]


class ReadingSuggestions:
    def __init__(self,data):
        self.data=Path(data);self.lock=threading.Lock();self.engines={};self.cache=OrderedDict()

    def _engine(self,mode):
        if mode not in self.engines:
            if mode=='numbers':
                from .detectors import TextDetector
                import rapidocr_onnxruntime
                engine=TextDetector()
                hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                        (Path(rapidocr_onnxruntime.__file__).parent/'models').glob('*.onnx')}
            else:
                from rapidocr_onnxruntime import RapidOCR
                path=self.data/'reading-models'/JAPANESE_FILE
                if not path.exists():raise ValueError('Optional Japanese reader is not installed')
                if hashlib.sha256(path.read_bytes()).hexdigest()!=JAPANESE_SHA256:
                    raise ValueError('Japanese reader model hash mismatch')
                engine=RapidOCR(rec_model_path=str(path),intra_op_num_threads=2,inter_op_num_threads=1,text_score=0)
                hashes={JAPANESE_FILE:JAPANESE_SHA256}
            self.engines[mode]=(engine,hashes)
        return self.engines[mode]

    def suggest(self,item,mode):
        if mode not in ('numbers','kana'):raise ValueError('Unknown reading mode')
        if item['kind']=='trail':raise ValueError('Select a text or symbol fragment to read')
        if not self.lock.acquire(blocking=False):raise RuntimeError('Another map reading is in progress. Try again shortly.')
        try:
            start=time.perf_counter()
            image,box,provenance=evidence_crop(self.data,item,64 if mode=='numbers' else 8,cover_box=mode=='numbers')
            digest=hashlib.sha256(image.tobytes()).hexdigest()
            key=(mode,image.size,digest,tuple(box))
            if key in self.cache:
                self.cache.move_to_end(key);return {**self.cache[key],'cached':True}
            decoded=time.perf_counter();engine,hashes=self._engine(mode);ready=time.perf_counter()
            readings=read_pixels(image,box,mode,engine)
            result=dict(mode=mode,readings=readings,model_hashes=hashes,pixels=provenance,pixel_sha256=digest,
                        cached=False,note='Unverified alternatives. Compare the complete map label; numbers do not establish a peak.',
                        timing_ms=dict(input=(decoded-start)*1000,model_init=(ready-decoded)*1000,
                                       recognition=(time.perf_counter()-ready)*1000))
            self.cache[key]=result
            if len(self.cache)>128:self.cache.popitem(last=False)
            return result
        finally:self.lock.release()
