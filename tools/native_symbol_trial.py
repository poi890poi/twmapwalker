"""Native ring/stem geometry with spatially calibrated shape and local peers."""
import argparse,json,math,time
import cv2
import numpy as np
from PIL import Image
import native_pattern_trial as trial
old=trial.old;OUT=trial.OUT
HOG=cv2.HOGDescriptor((32,40),(8,8),(4,4),(4,4),9)


def holes(gray):
    result=[]
    for threshold in (120,145,170):
        cs,hierarchy=cv2.findContours((gray<threshold).astype('uint8'),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None:continue
        for i,c in enumerate(cs):
            if hierarchy[0][i][3]<0:continue
            x,y,w,h=cv2.boundingRect(c);area=cv2.contourArea(c);perim=cv2.arcLength(c,True)
            if not (5<=min(w,h)<=max(w,h)<=13 and 10<=area<=100 and min(w,h)/max(w,h)>=.65 and 4*math.pi*area/max(1,perim**2)>=.6):continue
            cx=x+(w-1)/2;cy=y+(h-1)/2
            if any(math.hypot(cx-r['center'][0],cy-r['center'][1])<=2 for r in result):continue
            result.append(dict(center=[cx,cy],size=[w,h],threshold=threshold))
    return result


def descriptor(gray,hole):
    cx,cy=hole['center'];patch=np.asarray(Image.fromarray(gray).crop((round(cx)-16,round(cy)-12,round(cx)+16,round(cy)+28)))
    v=HOG.compute(patch).ravel();v=v/max(1e-8,np.linalg.norm(v))
    # Native occupancy retains ink/stem topology; no scale or aspect normalization.
    ink=cv2.resize((patch<145).astype('float32'),(16,20),interpolation=cv2.INTER_AREA).ravel()
    ink=ink/max(1e-8,np.linalg.norm(ink))
    return np.concatenate([v,ink])/np.sqrt(2)


def extract(r):
    gray=np.asarray(Image.open(r['image']).convert('L'));b=r['crop_box'];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
    hh=[h for h in holes(gray) if b[0]<=h['center'][0]<=b[2] and b[1]<=h['center'][1]<=b[3] and math.dist(h['center'],[cx,cy])<=12]
    if not hh:return None,None
    h=min(hh,key=lambda h:math.dist(h['center'],[cx,cy]));return descriptor(gray,h),h


def run():
    if (OUT/'symbol-lock.json').exists():raise RuntimeError('Frozen method exists')
    rr=old.read(OUT/'dataset.json');xx=[];locations=[];timings=[]
    for r in rr:
        start=time.perf_counter();v,h=extract(r);timings.append((time.perf_counter()-start)*1000);locations.append(h);xx.append(v)
    dimension=next(len(v) for v in xx if v is not None)
    x=np.stack([v if v is not None else np.zeros(dimension) for v in xx]);np.savez_compressed(OUT/'symbol-features.npz',features=x)
    base=old.read(trial.PRIOR/'locked-model.json');ids=np.array([i for i in base['fit_indices'] if locations[i] is not None]);y=np.array([1 if rr[i]['label']=='vegetation-like' else -1 for i in ids]);oof=[]
    for block in sorted({rr[i]['block'] for i in ids}):
        test=np.array([j for j,i in enumerate(ids) if rr[i]['block']==block]);fit=np.array([j for j,i in enumerate(ids) if rr[i]['block']!=block and not any(old.near(rr[i],rr[ids[k]]) for k in test)])
        assert len(set(y[fit]))==2
        score,ratio=old.predict(old.train(x[ids[fit]],y[fit]),x[ids[test]])
        oof.extend(dict(id=rr[ids[j]]['id'],target=int(y[j]),score=float(s),ratio=float(q)) for j,s,q in zip(test,score,ratio))
    threshold=max(r['score'] for r in oof if r['target']==-1)+.05
    lock=dict(threshold=threshold,guard_ratio=.8,fit_indices=ids.tolist(),fit_labels=y.tolist(),code_sha256=old.digest(__file__),features_sha256=old.digest(OUT/'symbol-features.npz'),dataset_sha256=old.digest(OUT/'dataset.json'))
    trial.write('symbol-lock.json',lock)
    model=old.train(x[ids],y);results=[]
    for i,r in enumerate(rr):
        if r['split']=='development':continue
        score,ratio=old.predict(model,x[i:i+1]);s=float(score[0]);q=float(ratio[0]);reject=bool(locations[i] is not None and s>threshold and q<.8)
        results.append(dict(id=r['id'],label=r['label'],split=r['split'],score=s,ratio=q,hole=locations[i],reject=reject))
    trial.write('symbol-evaluation.json',dict(oof=oof,samples=results,locations=locations,feature_ms=timings))
    print(json.dumps(dict(threshold=threshold,train_count=len(ids),vegetation=int((y==1).sum()),hits=[r for r in results if r['reject']]),indent=2))


def peers():
    rr=old.read(OUT/'dataset.json');out=[]
    for r in rr:
        if 'source' not in r:continue
        gray=np.asarray(Image.open(OUT/'contexts'/f"{r['id']}.png").convert('L'));start=time.perf_counter()
        hh=holes(gray);near=[h for h in hh if math.dist(h['center'],[192,192])<=12]
        if not near:out.append(dict(id=r['id'],matches=[],supported=False,reason='No central hole',ms=(time.perf_counter()-start)*1000));continue
        anchor=min(near,key=lambda h:math.dist(h['center'],[192,192]));v=descriptor(gray,anchor);matches=[]
        for h in hh:
            if math.dist(h['center'],anchor['center'])<20:continue
            if any(min(a,b)/max(a,b)<.8 for a,b in zip(h['size'],anchor['size'])):continue
            similarity=float(v@descriptor(gray,h))
            if similarity>=.90 and all(math.dist(h['center'],p['center'])>=20 for p in matches):matches.append(dict(**h,similarity=similarity))
        out.append(dict(id=r['id'],anchor=anchor,matches=matches,supported=len(matches)>=2,ms=(time.perf_counter()-start)*1000))
    trial.write('symbol-peers.json',out);print(json.dumps([(r['id'],len(r['matches'])) for r in out if r['supported']]))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['run','peers']);globals()[p.parse_args().stage]()
