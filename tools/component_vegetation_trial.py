"""Isolated native ink topology; all prior cases are development here."""
import argparse,json,math,time
import cv2
import numpy as np
from PIL import Image,ImageDraw
import native_pattern_trial as prior
old=prior.old;ROOT=prior.ROOT;OUT=ROOT/'evidence/vegetation-components'

def rows():
    rr=old.read(prior.OUT/'dataset.json');labels=old.read(prior.OUT/'fresh/visual-labels.json')['labels']
    for r in old.read(prior.OUT/'fresh/dataset.json'):
        r['label']=labels[str(r['id'])];r['split']='previous-native-fresh';rr.append(r)
    return rr

def find(image,box,opening=False,footprint=False):
    gray=np.asarray(image.convert('L'));observations=[]
    for threshold in (120,145,170):
        ink=(gray<threshold).astype('uint8')
        if opening:ink=cv2.morphologyEx(ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
        n,labels,stats,centers=cv2.connectedComponentsWithStats(ink,8)
        contours,hierarchy=cv2.findContours(ink,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None:continue
        for i,c in enumerate(contours):
            parent=hierarchy[0][i][3]
            if parent<0:continue
            hx,hy,hw,hh=cv2.boundingRect(c);cx=hx+(hw-1)/2;cy=hy+(hh-1)/2;area=cv2.contourArea(c);perimeter=cv2.arcLength(c,True)
            if not (box[0]<=cx<=box[2] and box[1]<=cy<=box[3]):continue
            if not (5<=min(hw,hh)<=max(hw,hh)<=13 and 10<=area<=100 and min(hw,hh)/max(hw,hh)>=.65 and 4*math.pi*area/max(1,perimeter**2)>=.6):continue
            px,py,pw,ph=cv2.boundingRect(contours[parent]);point=contours[parent][0,0];component=int(labels[point[1],point[0]])
            children=int(np.sum(hierarchy[0,:,3]==parent));mask=(labels[py:py+ph,px:px+pw]==component).astype('uint8')
            below=py+ph-(hy+hh);above=hy-py
            stem=mask[max(0,hy+hh+1-py):min(ph,hy+hh+5-py),max(0,round(cx)-1-px):min(pw,round(cx)+2-px)]
            density=float(stem.mean()) if stem.size else 0;satellites=[]
            for j in range(1,n):
                if j==component:continue
                x,y,w,h,a=map(int,stats[j]);sx,sy=centers[j]
                if 2<=a<=45 and max(w,h)<=12 and 3<=abs(sx-cx)<=16 and hh/2+1<=sy-cy<=hh/2+14:satellites.append([x,y,w,h,a])
            limits=(32,40,10,20,8) if footprint else (28,38,6,15,6)
            isolated=bool(children==1 and 9<=pw<=limits[0] and 12<=ph<=limits[1] and 2<=above<=limits[2] and 4<=below<=limits[3] and abs((px+pw/2)-cx)<=limits[4])
            shape=bool(isolated and density>=.45)
            observations.append(dict(threshold=threshold,hole=[hx,hy,hw,hh],parent=[px,py,pw,ph],center=[cx,cy],children=children,above=above,below=below,stem_density=density,satellites=satellites,isolated=isolated,shape=shape,compound=bool(shape and satellites),mask=mask.tolist()))
    def stable(key):return [r for r in observations if r[key] and len({q['threshold'] for q in observations if q[key] and math.dist(q['center'],r['center'])<=2})>=2]
    return dict(observations=observations,isolated=bool(stable('isolated')),shape=bool(stable('shape')),compound=bool(stable('compound')))

def main(opening=False,footprint=False):
    rr=rows();output=[]
    for r in rr:
        assert old.digest(r['image'])==r['sha256'];im=Image.open(r['image']).convert('RGB');start=time.perf_counter();v=find(im,r['crop_box'],opening,footprint);ms=(time.perf_counter()-start)*1000
        output.append(dict(id=r['id'],label=r['label'],source=r.get('source'),ms=ms,**v))
    stem=('opening' if opening else 'evaluation')+('-footprint' if footprint else '')
    (OUT/f'{stem}.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({method:{label:dict(total=sum(r['label']==label for r in output),hits=[r['id'] for r in output if r['label']==label and r[method]]) for label in sorted({r['label'] for r in output})} for method in ['isolated','shape','compound']},indent=2))
    chosen=[r for r in output if r['isolated'] or r['label']=='vegetation-like'];lookup={str(r['id']):r for r in rr}
    for start in range(0,len(chosen),24):
        selected=chosen[start:start+24];sheet=Image.new('RGB',(1000,math.ceil(len(selected)/5)*220),'white');d=ImageDraw.Draw(sheet)
        for j,r in enumerate(selected):
            x=j%5*200;y=j//5*220;item=lookup[str(r['id'])];im=Image.open(item['image']).convert('RGB');dr=ImageDraw.Draw(im);dr.rectangle(item['crop_box'],outline='red',width=1)
            for q in r['observations']:
                if q['compound']:
                    a,b,w,h=q['parent'];dr.rectangle((a,b,a+w,b+h),outline='lime',width=1)
            im.thumbnail((190,170));sheet.paste(im.resize((190,170)),(x,y+45));d.text((x+3,y+3),str(r['id'])+' '+r['label'],fill='black');d.text((x+3,y+23),'shape '+str(r['shape'])+' dot '+str(r['compound']),fill='black')
        sheet.save(OUT/f'{stem}-inspection-{start//24}.jpg')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--opening',action='store_true');p.add_argument('--footprint',action='store_true');args=p.parse_args();main(args.opening,args.footprint)
