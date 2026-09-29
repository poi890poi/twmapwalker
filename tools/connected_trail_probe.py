"""Experimental long dash paths. Inputs are historical pixels only."""
import numpy as np
from trail_graph_candidate import dash_graph


def connected_trails(image,threshold=135,min_width=0):
    dashes,graph=dash_graph(image,{'ink_threshold':threshold,'min_dash_width':min_width})
    # Select the nearest aligned neighbor at either end. Skip-edge cliques must
    # not turn one ordinary chain into dozens of apparent junctions.
    chosen=[]
    for i,a in enumerate(dashes):
        sides={-1:[],1:[]}
        for j in graph[i]:
            delta=dashes[j]['center']-a['center'];side=1 if delta@a['axis']>=0 else -1
            sides[side].append((np.linalg.norm(delta),j))
        chosen.append({min(v)[1] for v in sides.values() if v})
    mutual=[{j for j in neighbors if i in chosen[j]} for i,neighbors in enumerate(chosen)]
    from trail_graph_candidate import edge_paths
    paths=[]
    for nodes in edge_paths(mutual):
        points=np.array([dashes[i]['center'] for i in nodes]);steps=np.diff(points,axis=0)
        length=float(np.linalg.norm(steps,axis=1).sum())
        if len(nodes)<8 or length<120:continue
        if nodes[0]==nodes[-1]:continue
        paths.append(dict(points=points.tolist(),length_px=length,dashes=len(nodes),max_gap_px=float(np.linalg.norm(steps,axis=1).max())))
    return paths,dict(dashes=len(dashes),edges=sum(map(len,mutual))//2)
