"""Containment suppression for duplicate mark boxes; no semantic references."""
def suppress(proposals,threshold=.95):
    kept=[]
    for p in sorted(proposals,key=lambda p:-p['score']):
        if p['score']<threshold:continue
        a=p['box'];duplicate=False
        for q in kept:
            b=q['box'];intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
            area=min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
            if intersection/max(1,area)>=.70:
                duplicate=True;break
        if not duplicate:kept.append(p)
    return kept
