"""Experimental pixel-only candidates; no annotation or place-name access."""
import cv2
import numpy as np
from PIL import Image
from mapwalker.trails import trail_proposals
from run_symbol_first import iou,deduplicate

def thick_mask(image,threshold=135):
 gray=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY)
 ink=(gray<threshold).astype('uint8')
 distance=cv2.distanceTransform(ink,cv2.DIST_L2,5)
 core=(distance>=2).astype('uint8')
 return core,ink

def thick_symbols(image,config):
 core,ink=thick_mask(image,config['ink_threshold'])
 groups=cv2.dilate(core,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9)))
 count,labels,stats,_=cv2.connectedComponentsWithStats(groups,8);out=[]
 for i,(x,y,w,h,area) in enumerate(stats[1:],1):
  yy,xx=np.nonzero((labels==i)&(core!=0))
  if len(xx)<8:continue
  x0,y0,x1,y1=int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)
  if min(x1-x0,y1-y0)<4 or max(x1-x0,y1-y0)>80 or max(x1-x0,y1-y0)>4*min(x1-x0,y1-y0):continue
  out.append(dict(kind='symbol',text='',score=.35,repeating=False,box=[max(0,x0-5),max(0,y0-5),min(image.width,x1+5),min(image.height,y1+5)],details=dict(method='thick ink core groups',core_pixels=len(xx))))
 return out

def thick_trails(image,config):
 core,ink=thick_mask(image,config['ink_threshold'])
 # Change only ink representation; use the same dash graph, size and angle rules.
 restored=cv2.dilate(core,np.ones((3,3),'uint8'))&ink
 raster=Image.fromarray(np.repeat((255-restored*255)[:,:,None],3,axis=2))
 out=trail_proposals(raster,config)
 for p in out:p['details']['method']='aligned dash chain from thick ink cores'
 return out

def selective_scale(base,large):
 # Scale2 remains intact; added regions need support in two distinct rotations.
 passes=large['passes'];all_items=[(r['angle'],p) for r in passes for p in r['proposals']]
 additions=[]
 for p in large['proposals']:
  angles=sorted({a for a,q in all_items if iou(p['box'],q['box'])>=.4})
  if len(angles)<2 or any(iou(p['box'],q['box'])>=.25 for q in base['proposals']):continue
  additions.append({**p,'details':{**p['details'],'method':'scale3 addition; rotation agreement','support_angles':angles}})
 return base['proposals']+deduplicate(additions)

def compact_scale(base,large):
 additions=[]
 for p in large['proposals']:
  x,y,x1,y1=p['box']
  if p['score']<.5 or max(x1-x,y1-y)>96:continue
  if any(iou(p['box'],q['box'])>=.25 for q in base['proposals']):continue
  additions.append({**p,'details':{**p['details'],'method':'compact scale3 addition','selection':'peak >= .5; maximum side 96 native pixels'}})
 return base['proposals']+deduplicate(additions)
