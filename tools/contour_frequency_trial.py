"""Predeclared Fourier-axis experiment; offline and abstaining."""
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/contour-frequency'
SAMPLES=ROOT/'evidence/contour-samples'
PARAMETERS=dict(native_pixels=True,window='separable Hann; demean before windowing',
                radial_band_cycles_per_pixel=[1/64,1/4],axis_bins=72,
                lobe_width_degrees=20,second_axis_min_separation_degrees=25,
                single_axis_fraction=.70,two_axes_fraction=.90,
                methods=['mark','context','joint'],
                acceptance='No protected glyph/symbol or uncertain mark rejected; meaningful contour hits required. Failures stop before reserved evaluation.')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def spectrum(im):
    a=np.asarray(im.convert('L'),dtype=float)/255
    if min(a.shape)<12:return dict(available=False,reason='mark too small for the declared spectral band')
    h,w=a.shape
    a=(a-a.mean())*np.outer(np.hanning(h),np.hanning(w))
    energy=np.abs(np.fft.fft2(a))**2
    fy,fx=np.meshgrid(np.fft.fftfreq(h),np.fft.fftfreq(w),indexing='ij')
    radius=np.hypot(fx,fy);angle=np.mod(np.arctan2(fy,fx),np.pi)
    valid=(radius>=1/64)&(radius<=1/4)
    bins=np.floor(angle/(np.pi/72)).astype(int)%72
    mass=np.bincount(bins[valid],weights=energy[valid],minlength=72)
    if mass.sum()<1e-8:return dict(available=False,reason='no spectral energy')
    mass/=mass.sum()
    lobes=np.array([sum(mass[(i+j)%72] for j in range(-4,4)) for i in range(72)])
    first=int(np.argmax(lobes));allowed=[i for i in range(72) if min((i-first)%72,(first-i)%72)>=10]
    second=max(allowed,key=lambda i:lobes[i])
    one=float(lobes[first]);two=float(lobes[first]+lobes[second])
    entropy=float(-np.sum(mass[mass>0]*np.log(mass[mass>0]))/np.log(72))
    return dict(available=True,axis_fraction=one,two_axes_fraction=two,entropy=entropy,
                score=max(one/.70,two/.90),axis_degrees=first*2.5,second_axis_degrees=second*2.5,
                angular_energy=mass.tolist())


def main():
    if OUT.exists():raise RuntimeError('Preserve the frozen frequency trial')
    OUT.mkdir()
    write('parameters.json',PARAMETERS) # Thresholds fixed before running or seeing outputs.
    samples=json.loads((SAMPLES/'dataset.json').read_text(encoding='utf8'))
    labels={r['id']:r for r in json.loads((SAMPLES/'visual-labels.json').read_text(encoding='utf8'))['labels']}
    rows=[]
    for r in samples:
        if r['split']!='development':continue
        lab=labels[r['id']]['label']
        rows.append(dict(id=str(r['id']),origin='new-development',label=lab,negative=lab=='contour-fragment',
                         context=str((SAMPLES/r['context']).relative_to(ROOT)),mark=str((SAMPLES/r['mark']).relative_to(ROOT)),
                         context_sha256=r['context_sha256'],mark_sha256=r['mark_sha256'],context_box=r['context_box']))
    # These are deliberately protection probes, not calibration positives or new holdouts.
    base=ROOT/'evidence/noise-verifier'
    old=json.loads((base/'dataset.json').read_text(encoding='utf8'))
    updated=json.loads((base/'new-visual-labels.json').read_text(encoding='utf8'))['labels']
    for r in old:
        lab=updated.get(str(r['id']),r['label'])
        if lab not in ('poi','numeric','protected-symbol'):continue
        rows.append(dict(id=str(r['id']),origin='reused-protection',label=lab,negative=False,
                         context=str((base/r['crop']).relative_to(ROOT)),context_sha256=r['sha256'],context_box=r['crop_box']))
    results=[]
    for row in rows:
        path=ROOT/row['context'];assert sha(path)==row['context_sha256']
        with Image.open(path) as source:context=source.convert('RGB')
        if 'mark' in row:
            path=ROOT/row['mark'];assert sha(path)==row['mark_sha256']
            with Image.open(path) as source:mark=source.convert('RGB')
        else:
            a,b,c,d=row['context_box'];mark=context.crop((math.floor(a)-4,math.floor(b)-4,math.ceil(c)+4,math.ceil(d)+4))
        start=time.perf_counter();m=spectrum(mark);c=spectrum(context)
        scores={name:values.get('score',0) for name,values in [('mark',m),('context',c)]}
        scores['joint']=min(scores.values())
        results.append({**row,'features':dict(mark=m,context=c),'scores':scores,
                        'rejected':{k:v>=1 for k,v in scores.items()},'feature_ms':(time.perf_counter()-start)*1000})
    summary={}
    for method in PARAMETERS['methods']:
        hits=[r for r in results if r['rejected'][method]]
        false=[dict(id=r['id'],origin=r['origin'],label=r['label'],score=r['scores'][method]) for r in hits if not r['negative']]
        count=sum(r['negative'] for r in hits)
        summary[method]=dict(contour_hits=count,contour_total=sum(r['negative'] for r in results),
                             protected_or_uncertain_hits=len(false),protected_or_uncertain_total=sum(not r['negative'] for r in results),
                             false_rejections=false,decision='reject' if false or not count else 'eligible for a later reserved test')
    write('samples.json',rows);write('results.json',results);write('summary.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
