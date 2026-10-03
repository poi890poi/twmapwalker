"""Offline native-scale shape/repetition experiment; no production writes."""
import argparse,json,math,statistics,time
import cv2
import numpy as np
from PIL import Image,ImageDraw
import noise_verifier_trial as old

ROOT=old.ROOT;OUT=ROOT/'evidence/native-patterns';PRIOR=old.OUT
HOG=cv2.HOGDescriptor((96,96),(16,16),(8,8),(8,8),9)
PARAMS=dict(canvas=96,padding=4,ridge=.1,margin=.05,guard_ratio=.8,repetitions=2,correlation=.80,scene_side=384,native_zoom=16)


def write(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),'utf-8')


def rows():
    result=[];newer=old.read(PRIOR/'new-visual-labels.json')['labels'];fresh=old.read(PRIOR/'fresh/visual-labels.json')['labels']
    for r in old.read(PRIOR/'dataset.json'):
        r=r.copy();r['label']=newer.get(str(r['id']),r['label']);r['image']=str(PRIOR/r['crop']);result.append(r)
    for r in old.read(PRIOR/'fresh/dataset.json'):
        r=r.copy();r['label']=fresh[str(r['id'])];r['split']='prior-fresh';r['image']=str(PRIOR/'fresh'/r['crop']);result.append(r)
    for r in result:
        if r['id']==33495:r.update(label='noise',label_provenance='Explicit user correction; known diagnostic, not fresh')
    return result


def views(r):
    assert old.digest(r['image'])==r['sha256']
    im=Image.open(r['image']).convert('L');a,b,c,d=r['crop_box']
    patch=im.crop((math.floor(a)-4,math.floor(b)-4,math.ceil(c)+4,math.ceil(d)+4));w,h=patch.size
    valid=max(w,h)<=96
    native=Image.new('L',(96,96),255);native.paste(patch,((96-w)//2,(96-h)//2))
    factor=min(96/w,96/h);aspect=patch.resize((max(1,round(w*factor)),max(1,round(h*factor))),Image.Resampling.BILINEAR)
    letter=Image.new('L',(96,96),255);letter.paste(aspect,((96-aspect.width)//2,(96-aspect.height)//2))
    return {'stretch':patch.resize((96,96),Image.Resampling.BILINEAR),'aspect':letter,'native':native},valid


def features():
    if (OUT/'features.npz').exists():raise RuntimeError('Frozen features exist')
    rr=rows();out={k:[] for k in ('stretch','aspect','native')};timing=[]
    for r in rr:
        imgs,valid=views(r);r['in_scope']=valid;start=time.perf_counter()
        for key,im in imgs.items():
            v=HOG.compute(np.asarray(im)).ravel();out[key].append(v/max(1e-8,np.linalg.norm(v)))
        timing.append((time.perf_counter()-start)*1000)
    np.savez_compressed(OUT/'features.npz',**{k:np.stack(v) for k,v in out.items()})
    write('dataset.json',rr);write('parameters.json',PARAMS)
    write('label-corrections.json',{'33495':dict(previous='uncertain',current='noise',source='Explicit user correction; no inference-based relabeling')})
    write('feature-timing.json',dict(unit='ms HOG computation for all three views; excludes decode and patch construction',raw=timing,mean=statistics.mean(timing),median=statistics.median(timing),p95=float(np.percentile(timing,95)),maximum=max(timing),numpy=np.__version__,opencv=cv2.__version__))
    board=Image.new('RGB',(700,900),'white');d=ImageDraw.Draw(board)
    for i,key in enumerate(['control-9',38819,99624,33495]):
        r=next(r for r in rr if r['id']==key);vv,_=views(r)
        for j,(name,im) in enumerate(vv.items()):
            x=j*230;y=i*225;board.paste(im.resize((192,192)),(x,y+30));d.text((x+3,y+3),f'{key}: {name}',fill='black')
    board.save(OUT/'scale-comparison.png')


def run():
    if (OUT/'locked-model.json').exists():raise RuntimeError('Never retune locked thresholds')
    rr=old.read(OUT/'dataset.json');xx=np.load(OUT/'features.npz');base=old.read(PRIOR/'locked-model.json')
    ids=np.array([i for i in base['fit_indices'] if rr[i]['in_scope']]);results={};models={};locks={}
    for method in ['stretch-broad','aspect-broad','native-broad','native-vegetation']:
        representation,task=method.split('-');x=xx[representation][ids]
        y=np.array([(1 if r['label']=='vegetation-like' else -1) if task=='vegetation' else old.target(r) for r in [rr[i] for i in ids]])
        oof=[]
        for block in sorted({rr[i]['block'] for i in ids}):
            test=np.array([j for j,i in enumerate(ids) if rr[i]['block']==block])
            fit=np.array([j for j,i in enumerate(ids) if rr[i]['block']!=block and not any(old.near(rr[i],rr[ids[k]]) for k in test)])
            assert len(set(y[fit]))==2
            score,ratio=old.predict(old.train(x[fit],y[fit]),x[test])
            for j,s,q in zip(test,score,ratio):oof.append(dict(id=rr[ids[j]]['id'],target=int(y[j]),label=rr[ids[j]]['label'],score=float(s),ratio=float(q),fit_count=len(fit)))
        threshold=max(r['score'] for r in oof if r['target']==-1)+.05
        for r in oof:r['reject']=r['score']>threshold and r['ratio']<.8
        locks[method]=dict(threshold=threshold,fit_indices=ids.tolist(),fit_labels=y.tolist())
        models[method]=old.train(x,y);results[method]=dict(oof=oof,threshold=threshold,development_hits=sum(r['reject'] and r['target']==1 for r in oof),samples=[])
    write('locked-model.json',dict(parameters=PARAMS,methods=locks,code_sha256=old.digest(__file__),features_sha256=old.digest(OUT/'features.npz'),dataset_sha256=old.digest(OUT/'dataset.json')))
    for method,model in models.items():
        rep=method.split('-')[0]
        for i,r in enumerate(rr):
            if r['split']=='development':continue
            start=time.perf_counter();score,ratio=old.predict(model,xx[rep][i:i+1]);ms=(time.perf_counter()-start)*1000
            s=float(score[0]);q=float(ratio[0]);reject=bool(r['in_scope'] and s>locks[method]['threshold'] and q<.8)
            results[method]['samples'].append(dict(id=r['id'],split=r['split'],label=r['label'],score=s,ratio=q,in_scope=r['in_scope'],reject=reject,ms=ms))
    write('evaluation.json',results)
    print(json.dumps({k:dict(threshold=v['threshold'],development_hits=v['development_hits'],hits=[(r['id'],r['label']) for r in v['samples'] if r['reject']]) for k,v in results.items()},indent=2))


def context(r):
    if 'source' not in r:return None,None
    assert r['z']==16
    cx=(r['box'][0]+r['box'][2])/2;cy=(r['box'][1]+r['box'][3])/2
    left=round(256+cx-192);top=round(256+cy-192)
    canvas=Image.new('RGB',(768,768),'white');provenance=[]
    for dy in (-1,0,1):
        for dx in (-1,0,1):
            if left+384<=(dx+1)*256 or left>=(dx+2)*256 or top+384<=(dy+1)*256 or top>=(dy+2)*256:continue
            folder=ROOT/'data/tiles/2026-09-28-v1'/r['source']/str(r['z'])/str(r['x']+dx)
            meta=old.read(folder/f"{r['y']+dy}.json");path=folder/meta['file'];assert old.digest(path)==meta['sha256']
            canvas.paste(Image.open(path).convert('RGB'),((dx+1)*256,(dy+1)*256));provenance.append(dict(path=str(path.relative_to(ROOT)),sha256=meta['sha256']))
    return canvas.crop((left,top,left+384,top+384)),provenance


def repetition(im,width,height):
    gray=np.asarray(im.convert('L')).astype('float32')
    field=cv2.GaussianBlur(gray,(0,0),.6)-cv2.GaussianBlur(gray,(0,0),2.0)
    w=max(8,min(88,math.ceil(width)+8));h=max(8,min(88,math.ceil(height)+8))
    x=(384-w)//2;y=(384-h)//2;template=field[y:y+h,x:x+w]
    if float(template.std())<1:return dict(matches=[],supported=False,template=[x,y,w,h],reason='flat template')
    response=cv2.matchTemplate(field,template,cv2.TM_CCOEFF_NORMED)
    response[max(0,y-h):y+h+1,max(0,x-w):x+w+1]=-1
    matches=[]
    for _ in range(12):
        _,score,_,where=cv2.minMaxLoc(response)
        if score<.80:break
        xx,yy=where;matches.append(dict(box=[xx,yy,xx+w,yy+h],correlation=float(score)))
        response[max(0,yy-h):yy+h+1,max(0,xx-w):xx+w+1]=-1
    return dict(matches=matches,supported=len(matches)>=2,template=[x,y,w,h])


def repeat():
    rr=old.read(OUT/'dataset.json');result=[];(OUT/'contexts').mkdir(exist_ok=True)
    for r in rr:
        if 'source' not in r:continue
        im,provenance=context(r);path=OUT/'contexts'/f"{r['id']}.png";im.save(path)
        b=r['box'];start=time.perf_counter();v=repetition(im,b[2]-b[0],b[3]-b[1]);ms=(time.perf_counter()-start)*1000
        result.append(dict(id=r['id'],label=r['label'],split=r['split'],context_sha256=old.digest(path),provenance=provenance,ms=ms,**v))
    write('repetition.json',result)
    print(json.dumps([(r['id'],r['label'],len(r['matches'])) for r in result if r['supported']]))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['features','run','repeat']);globals()[p.parse_args().stage]()
