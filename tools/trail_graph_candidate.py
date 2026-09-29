"""Trace accepted dash edges; no reference paths or semantic labels enter this module."""
import cv2
import numpy as np

def dash_graph(image,config):
 ink=(cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY)<config['ink_threshold']).astype(np.uint8)
 count,labels,stats,centers=cv2.connectedComponentsWithStats(ink,8)
 dashes=[]
 for i in range(1,count):
  x,y,w,h,area=map(int,stats[i])
  if not (4<=area<=220 and 3<=max(w,h)<=38):continue
  if area/max(w,h)<config.get('min_dash_width',0):continue
  yy,xx=np.nonzero(labels[y:y+h,x:x+w]==i);points=np.column_stack((xx,yy)).astype(float)
  values,vectors=np.linalg.eigh(np.cov(points,rowvar=False))
  if values[1]<max(1,values[0]*3):continue
  dashes.append(dict(center=centers[i],axis=vectors[:,1],length=max(w,h),box=[x,y,x+w,y+h]))
 graph=[set() for _ in dashes]
 for i,a in enumerate(dashes):
  for j in range(i+1,len(dashes)):
   b=dashes[j];delta=b['center']-a['center'];distance=np.linalg.norm(delta)
   if not (4<distance<min(44,2*(a['length']+b['length'])+8)):continue
   direction=delta/distance
   if abs(direction@a['axis'])<.82 or abs(direction@b['axis'])<.82 or abs(a['axis']@b['axis'])<.75:continue
   graph[i].add(j);graph[j].add(i)
 return dashes,graph

def edge_paths(graph):
 """Maximal nonbranching walks; each undirected edge occurs exactly once."""
 used=set();paths=[]
 def walk(start,neighbor):
  path=[start,neighbor];used.add(tuple(sorted((start,neighbor))))
  while len(graph[neighbor])==2:
   nxt=next(n for n in sorted(graph[neighbor]) if n!=path[-2])
   edge=tuple(sorted((neighbor,nxt)))
   if edge in used:break
   used.add(edge);path.append(nxt);neighbor=nxt
  paths.append(path)
 for start,neighbors in enumerate(graph):
  if len(neighbors)==2:continue
  for neighbor in sorted(neighbors):
   if tuple(sorted((start,neighbor))) not in used:walk(start,neighbor)
 # Remaining components are closed loops.
 for start,neighbors in enumerate(graph):
  for neighbor in sorted(neighbors):
   if tuple(sorted((start,neighbor))) not in used:walk(start,neighbor)
 return paths

def graph_trails(image,config):
 dashes,graph=dash_graph(image,config);out=[]
 for nodes in edge_paths(graph):
  if len(set(nodes))<3:continue
  points=np.array([dashes[i]['center'] for i in nodes]);length=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
  if length<22:continue
  boxes=np.array([dashes[i]['box'] for i in nodes]);box=[int(boxes[:,0].min()),int(boxes[:,1].min()),int(boxes[:,2].max()),int(boxes[:,3].max())]
  out.append(dict(kind='trail',text='',score=.4,box=box,repeating=False,details=dict(method='connected dash graph walk',dash_count=len(set(nodes)),pixel_path=points.tolist(),path_length_px=length,closed=nodes[0]==nodes[-1],interpretation='Candidate trail segment; semantic class and route continuity unverified')))
 return out

def safe_trails(image,config):
 from mapwalker.trails import trail_proposals
 baseline=trail_proposals(image,config);dashes,graph=dash_graph(image,config);lookup={tuple(d['center']):i for i,d in enumerate(dashes)};out=[]
 for p in baseline:
  nodes=[lookup[tuple(c)] for c in p['details']['pixel_path']];segments=[];segment=[nodes[0]]
  for node in nodes[1:]:
   if node not in graph[segment[-1]]:segments.append(segment);segment=[]
   segment.append(node)
  segments.append(segment)
  for nodes in segments:
   if len(nodes)<3:continue
   points=np.array([dashes[i]['center'] for i in nodes])
   if np.linalg.norm(points[-1]-points[0])<22:continue
   boxes=np.array([dashes[i]['box'] for i in nodes]);box=[int(boxes[:,0].min()),int(boxes[:,1].min()),int(boxes[:,2].max()),int(boxes[:,3].max())]
   out.append({**p,'box':box,'details':{**p['details'],'method':'aligned dash chain; supported edges only','dash_count':len(nodes),'pixel_path':points.tolist()}})
 return out
