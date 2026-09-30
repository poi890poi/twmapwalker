"""No invented paths on empty evidence, bounded links, and real paper control."""
import hashlib,json,sys,urllib.request
from pathlib import Path
import cv2,numpy as np,torch
from PIL import Image
from synthetic_dash_model import DashNet,connect,infer
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/trail-round5'

def main():
    empty=np.zeros((256,256),np.float32);mask,paths=connect(empty);assert not paths and not mask.any()
    solid=empty.copy();cv2.line(solid,(10,80),(245,80),.9,3);_,paths=connect(solid);assert not paths
    dashes=empty.copy()
    for y in (50,170):
        for x in range(20,225,14):cv2.rectangle(dashes,(x,y),(x+7,y+2),.9,-1)
    mask,paths=connect(dashes);assert len(paths)==2
    for p in paths:assert np.linalg.norm(np.diff(np.asarray(p['points']),axis=0),axis=1).max()<=32
    _,zero=connect(dashes*np.zeros_like(dashes));assert not zero
    src=ROOT/'evidence/batongguan-review/JM50K_1924_new-original.png'
    torch.set_num_threads(2);model=DashNet().cuda().eval();model.load_state_dict(torch.load(ROOT/'data/trail-round5/dashnet.pt',weights_only=True,map_location='cuda'))
    gray=np.asarray(Image.open(src).convert('L'));prob=infer(model,gray);kept,paths=connect(prob)
    Image.fromarray((prob*255).astype(np.uint8)).save(OUT/'blank-paper-likelihood.png')
    with urllib.request.urlopen('http://127.0.0.1:8765/api/status',timeout=10) as r:status=json.load(r)
    result=dict(empty_evidence_no_paths=True,solid_line_no_dash_chain=True,two_separate_synthetic_chains=True,max_link_px=32,zero_corridor_cannot_create_paths=True,blank_paper_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),blank_paper_above_half=int((prob>=.5).sum()),blank_paper_paths=len(paths),worker_paused=status['paused'])
    (OUT/'controls.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()
