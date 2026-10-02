"""Render automatic regions for independent visual assessment after locked runs."""
import sys
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.run_detection_proposals import load,OUT,crop,owner
for split in ('development','holdout','number-holdout'):
    tiles=[]
    for s in load(OUT/f'{split}-inputs.json'):
        im=Image.open(OUT/s['path']).convert('RGB')
        for p in s['proposals']:
            if not owner(p):continue
            patch,local=crop(im,p['box'],24);ImageDraw.Draw(patch).rectangle(local,outline='red',width=1)
            tiles.append((str(p['id']),patch))
        g=next(g for g in load(OUT/f'{split}-geometry.json') if g['id']==s['id'])
        for proposal in g['groups']:
            patch,local=crop(im,proposal['box'],12);draw=ImageDraw.Draw(patch)
            for n,box in enumerate(proposal['details']['member_boxes']):
                b=[box[0]-proposal['box'][0]+local[0],box[1]-proposal['box'][1]+local[1],box[2]-proposal['box'][0]+local[0],box[3]-proposal['box'][1]+local[1]]
                draw.rectangle(b,outline='red',width=1);draw.text(b[:2],str(n),fill='red')
            tiles.append((proposal['id'],patch))
    for offset in range(0,len(tiles),24):
        sheet=Image.new('RGB',(1200,6*205),'white');draw=ImageDraw.Draw(sheet)
        for i,(name,im) in enumerate(tiles[offset:offset+24]):
            x=i%4*300;y=i//4*205;scale=min(290/im.width,175/im.height)
            patch=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.NEAREST)
            sheet.paste(patch,(x,y+24));draw.text((x+4,y+3),name,fill='black')
        sheet.save(OUT/f'{split}-review-{offset//24}.png')
