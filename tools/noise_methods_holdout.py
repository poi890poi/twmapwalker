"""Lock one development winner's unseen predictions before displaying targets."""
import cv2
import numpy as np
from .contour_learner_data import ROOT,read,write,sha,sheets
from .contour_learner_trial import extract,predict
from .noise_methods_features import OUT,BASE,WEIGHTS,extract_rows


def main():
    import torch
    from transformers import AutoModel
    from PIL import Image
    if (OUT/'holdout-lock.json').exists():raise RuntimeError('Holdout predictions already frozen')
    lock=read(OUT/'model-lock.json');summary=read(OUT/'development-summary.json')
    assert sha(ROOT/'tools/noise_methods_trial.py')==lock['code_sha256']
    assert sha(BASE/'holdout-inputs.json')==lock['holdout_sha256']
    eligible=[m for m in summary if summary[m]['eligible']]
    winner=max(eligible,key=lambda m:(sum(v['hits'] for k,v in summary[m]['by_edition'].items() if '1924' in k),summary[m]['contour_hits']))
    assert winner=='dino-structure-rf','Only the predetermined winning RF is implemented here'
    assert sha(OUT/f'{winner}.xml')==lock['models'][winner]['state_sha256']
    assert sha(WEIGHTS/'model.safetensors')==read(OUT/'contract.json')['weights_sha256']
    torch.set_num_threads(2);torch.manual_seed(7331)
    model=AutoModel.from_pretrained(str(WEIGHTS),local_files_only=True).eval().cuda()
    rows=read(BASE/'holdout-inputs.json');x,patches,timing=extract_rows(rows,model,torch)
    structure=[]
    for r in rows:
        with Image.open(ROOT/r['context']) as im:structure.append(extract(im.convert('RGB'),r['context_box'])['appearance-structure'][-18:])
    np.savez_compressed(OUT/'holdout-features.npz',vectors=x,structure=np.stack(structure))
    # Score in the same OpenCV runtime as development, in the second phase.
    write(OUT/'holdout-feature-lock.json',dict(winner=winner,arrays_sha256=sha(OUT/'holdout-features.npz'),
        code_sha256=sha(ROOT/'tools/noise_methods_holdout.py'),model_lock_sha256=sha(OUT/'model-lock.json'),timing=timing))
    print('Holdout features frozen; no target images or predictions displayed.',flush=True)


def freeze():
    lock=read(OUT/'model-lock.json');fl=read(OUT/'holdout-feature-lock.json');winner=fl['winner']
    if (OUT/'holdout-lock.json').exists():raise RuntimeError('Holdout already scored')
    assert sha(OUT/'holdout-features.npz')==fl['arrays_sha256']
    assert sha(OUT/'model-lock.json')==fl['model_lock_sha256']
    assert sha(OUT/f'{winner}.xml')==lock['models'][winner]['state_sha256']
    arrays=np.load(OUT/'holdout-features.npz');model=cv2.ml.RTrees_load(str(OUT/f'{winner}.xml'))
    scores=predict(model,np.column_stack([arrays['vectors'],arrays['structure']]).astype(np.float32))
    rows=read(BASE/'holdout-inputs.json');threshold=lock['models'][winner]['threshold']
    write(OUT/'holdout-predictions.json',[dict(id=r['id'],index=r['index'],score=float(s),reject=bool(s>threshold)) for r,s in zip(rows,scores)])
    write(OUT/'holdout-lock.json',dict(predictions_sha256=sha(OUT/'holdout-predictions.json'),
        model_lock_sha256=sha(OUT/'model-lock.json'),feature_lock_sha256=sha(OUT/'holdout-feature-lock.json'),
        threshold=threshold,winner=winner,opencv=cv2.__version__,numpy=np.__version__,
        acceptance='At least25% of visually confirmed contours removed; zero protected/uncertain flags. Names, numbers, Kana and rare symbols need independent coverage before automatic hiding.'))
    sheets(rows,OUT,'holdout')
    print('Predictions frozen. Four raw contact sheets ready for blind labeling; scores not printed.',flush=True)


if __name__=='__main__':
    import sys
    (freeze if len(sys.argv)>1 and sys.argv[1]=='freeze' else main)()
