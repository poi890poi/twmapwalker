"""Post-run diagnostics; never change operational cutoffs or model selection."""
import numpy as np
from PIL import Image,ImageDraw,ImageOps,ImageFont
from .contour_learner_data import ROOT,read,write
from .local_mark_data import OUT


def main():
    rows=read(OUT/'training.json');guards=read(OUT/'guards.json');challenge=read(OUT/'challenge.json');n=len(rows);g=len(guards)
    y=np.array([r['negative'] for r in rows]);cy=np.array([r['negative'] for r in challenge]);result={}
    for path in sorted(OUT.glob('*-scores.npy')):
        v=np.load(path).mean(0);s=v[:n];no_margin=float(s[~y].max());atquarter=float(np.sort(s[y])[-24]-1e-8)
        def operating(t):
            return dict(threshold=t,contour_hits=int(np.sum(s[y]>t)),protected_flags=int(np.sum(s[~y]>t)),
                protected_flag_labels=[dict(id=r['id'],label=r['label']) for r,p in zip(rows,s) if not r['negative'] and p>t],
                guard_flags=int(np.sum(v[n:n+g]>t)),challenge_contour_hits=int(np.sum(v[n+g:][cy]>t)),challenge_protected_flags=int(np.sum(v[n+g:][~cy]>t)))
        pairs=s[y,None]-s[None,~y]
        worst=sorted([i for i,r in enumerate(rows) if not r['negative']],key=lambda i:-s[i])[:5]
        result[path.stem]=dict(auc=float(np.mean((pairs>0)+.5*(pairs==0))),zero_margin=operating(no_margin),quarter_removal=operating(atquarter),
            largest_protected_scores=[dict(id=rows[i]['id'],label=rows[i]['label'],score=float(s[i])) for i in worst])
    write(OUT/'diagnostics.json',dict(scope='Descriptive sensitivity analysis after fixed experiments. No cutoff changes; no fresh evaluation; apparent development safety is not independent.',models=result))
    v=np.load(OUT/'nested-max-scores.npy').mean(0);worst=sorted([i for i,r in enumerate(rows) if not r['negative']],key=lambda i:-v[i])[:3]
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
    board=Image.new('RGB',(960,380),'#fafaf5');draw=ImageDraw.Draw(board)
    for j,i in enumerate(worst):
        r=rows[i]
        with Image.open(ROOT/r['context']) as im:im=im.convert('RGB')
        ImageDraw.Draw(im).rectangle(r['context_box'],outline='#cf3333',width=1)
        draw.text((j*320+8,8),f"POI {r['id']}: {r['label']}",font=font,fill='#203b32')
        board.paste(ImageOps.contain(im,(304,304),Image.Resampling.NEAREST),(j*320+8,38))
        draw.text((j*320+8,350),f"Noise score {v[i]:.3f}; keep label unchanged",font=font,fill='#203b32')
    board.save(OUT/'limiting-cases.png')
    print('Diagnostics recorded. Fixed decision rules remain unchanged.')


if __name__=='__main__':main()
