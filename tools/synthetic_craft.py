"""Synthetic-only CRAFT head adaptation. No real maps or reference access."""
import hashlib,json,math,os,random,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import cv2,numpy as np,torch
from PIL import Image,ImageDraw,ImageFont,ImageFilter
from easyocr.detection import get_detector
from easyocr.imgproc import normalizeMeanVariance

OUT=ROOT/'data/model-trials/synthetic-craft-v1'
FONTS=[Path('C:/Windows/Fonts')/s for s in ['msmincho.ttc','yumin.ttf','BIZ-UDMinchoM.ttc','simkai.ttf','mingliub.ttc','msgothic.ttc']]
SIDE=384

def sample(rng):
    yy,xx=np.mgrid[:SIDE,:SIDE].astype('float32')
    field=np.zeros((SIDE,SIDE),'float32')
    for _ in range(rng.randint(3,7)):
        cx,cy=rng.uniform(-150,530),rng.uniform(-150,530);sx,sy=rng.uniform(70,260),rng.uniform(70,260)
        field+=rng.uniform(-1,1)*np.exp(-((xx-cx)**2/sx**2+(yy-cy)**2/sy**2))
    field+=rng.uniform(-.4,.4)*xx/SIDE+rng.uniform(-.4,.4)*yy/SIDE
    field=(field-field.min())/max(.01,field.max()-field.min())
    bg=rng.choice([(225,202,162),(225,217,198),(242,241,232),(245,245,245)])
    canvas=np.full((SIDE,SIDE,3),bg,'uint8')
    lines=np.zeros((SIDE,SIDE),'uint8')
    for level in np.arange(.05,.99,rng.uniform(.025,.07)):
        cs,_=cv2.findContours((field>level).astype('uint8'),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(lines,cs,-1,255,rng.choice([1,1,2,2,3]))
    line_dark=rng.randint(65,155)
    canvas[lines>0]=[min(c,line_dark+rng.randint(-8,8)) for c in bg]
    # Repeated loops are background. They receive no positive labels.
    if rng.random()<.5:
        for y in range(rng.randint(0,30),SIDE,rng.randint(24,55)):
            for x in range(rng.randint(0,30),SIDE,rng.randint(24,55)):
                cv2.ellipse(canvas,(x+rng.randint(-4,4),y+rng.randint(-4,4)),(rng.randint(2,5),rng.randint(3,7)),rng.randint(0,180),0,360,(line_dark,)*3,1)
    target=np.zeros((SIDE,SIDE),'float32');boxes=[]
    for _ in range(0 if rng.random()<.20 else rng.randint(1,6)):
        # Sample glyph identities independently; never supply a known map label.
        ch=chr(rng.choice([rng.randint(0x30A1,0x30FA),rng.randint(0x4E00,0x9FA0),rng.randint(0x3041,0x3096)]))
        size=rng.randint(22,115);font=ImageFont.truetype(str(rng.choice(FONTS)),size)
        mask=Image.new('L',(size*2,size*2));d=ImageDraw.Draw(mask);d.text((size//2,size//3),ch,font=font,fill=255,stroke_width=rng.choice([0,0,1,2]))
        bbox=mask.getbbox()
        if not bbox:continue
        mask=mask.crop(bbox);mask=mask.rotate(rng.choice([0,0,0,45,-45,90,180,270,rng.randint(-180,180)]),Image.Resampling.BICUBIC,expand=True)
        bbox=mask.getbbox()
        if not bbox:continue
        mask=mask.crop(bbox);w,h=mask.size
        if w>=SIDE-12 or h>=SIDE-12:continue
        x,y=rng.randint(6,SIDE-w-6),rng.randint(6,SIDE-h-6)
        if any(x<b[2]+5 and x+w>b[0]-5 and y<b[3]+5 and y+h>b[1]-5 for b in boxes):continue
        boxes.append([x,y,x+w,y+h]);alpha=np.asarray(mask).astype('float32')/255
        dark=rng.randint(35,130);paper=canvas[y:y+h,x:x+w].astype('float32')
        # Dark transparent ink naturally intersects preexisting contours.
        opacity=rng.uniform(.60,1)
        canvas[y:y+h,x:x+w]=np.clip(paper*(1-alpha[:,:,None]*opacity)+np.minimum(paper,dark)*alpha[:,:,None]*opacity,0,255)
        sigma_x=max(3,w*.23);sigma_y=max(3,h*.23)
        g=np.exp(-.5*((xx-(x+w/2))**2/sigma_x**2+(yy-(y+h/2))**2/sigma_y**2))
        target=np.maximum(target,g)
    im=Image.fromarray(canvas).filter(ImageFilter.GaussianBlur(rng.uniform(.15,1.3)))
    if rng.random()<.25:im=im.resize((192,192),Image.Resampling.BILINEAR).resize((SIDE,SIDE),Image.Resampling.BILINEAR)
    return im,cv2.resize(target,(192,192)),boxes

def main():
    if (OUT/'adapted.pth').exists():raise RuntimeError('Preserve completed checkpoint')
    OUT.mkdir(parents=True,exist_ok=True);torch.set_num_threads(2);torch.manual_seed(3081);rng=random.Random(3081)
    weights=ROOT/'data/model-trials/models/easyocr/craft_mlt_25k.pth'
    model=get_detector(str(weights),device='cuda');net=model.module if hasattr(model,'module') else model
    net.eval()
    for p in net.parameters():p.requires_grad_(False)
    for p in net.conv_cls.parameters():p.requires_grad_(True)
    torch.cuda.reset_peak_memory_stats();features=[];targets=[];tick=time.perf_counter()
    # Freeze a small generated corpus in feature space; only the score head learns.
    for i in range(256):
        im,target,boxes=sample(rng)
        if i<12:
            im.save(OUT/f'sample-{i:02}.png')
            (OUT/f'sample-{i:02}.json').write_text(json.dumps(boxes))
        x=torch.from_numpy(normalizeMeanVariance(np.asarray(im)).transpose(2,0,1)[None]).cuda()
        with torch.no_grad():_,feat=net(x)
        features.append(feat[0].half().cpu());targets.append(torch.from_numpy(target).half())
        if i%32==0:print('generated',i,flush=True)
    prepare_seconds=time.perf_counter()-tick;opt=torch.optim.Adam(net.conv_cls.parameters(),lr=1e-4)
    losses=[];tick=time.perf_counter()
    for step in range(1200):
        indices=rng.sample(range(len(features)),4)
        x=torch.stack([features[i] for i in indices]).float().cuda();target=torch.stack([targets[i] for i in indices]).float().cuda()
        pred=net.conv_cls(x)[:,0]
        loss_map=(pred-target).square();positive=target>.10
        pos=loss_map[positive].mean() if positive.any() else pred.sum()*0
        neg=loss_map[~positive];hard=neg.topk(min(neg.numel(),max(500,int(positive.sum())*3))).values.mean()
        loss=pos+hard;opt.zero_grad();loss.backward();opt.step()
        if step%100==0:
            losses.append(dict(step=step,loss=float(loss)));print('step',step,round(float(loss),4),flush=True)
    torch.save(net.state_dict(),OUT/'adapted.pth')
    meta=dict(seed=3081,samples=256,steps=1200,batch=4,learning_rate=1e-4,trainable='conv_cls only',prepare_seconds=prepare_seconds,train_seconds=time.perf_counter()-tick,losses=losses,peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,base_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),checkpoint_sha256=hashlib.sha256((OUT/'adapted.pth').read_bytes()).hexdigest(),fonts={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in FONTS},harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/'run.json').write_text(json.dumps(meta,indent=2));(OUT/'harness.py').write_bytes(Path(__file__).read_bytes())
    print('complete',meta['train_seconds'],meta['peak_allocated_mib'],flush=True)
if __name__=='__main__':main()
