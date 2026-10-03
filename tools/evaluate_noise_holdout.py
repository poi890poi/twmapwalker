"""Join visually frozen labels to locked predictions; no threshold changes."""
from collections import Counter
import numpy as np
import cv2
from .contour_learner_data import ROOT,sha,read,write
from .contour_learner_trial import predict,extract
from .noise_methods_features import OUT,BASE


def main():
    lock=read(OUT/'holdout-lock.json');labels=read(OUT/'holdout-labels.json')
    assert sha(OUT/'holdout-predictions.json')==lock['predictions_sha256']
    inverse={i:label for label,ids in labels.items() if isinstance(ids,list) for i in ids}
    assert len(inverse)==48 and sorted(inverse)==list(range(1,49))
    rows=read(BASE/'holdout-inputs.json');predictions=read(OUT/'holdout-predictions.json')
    joined=[dict(**p,source=r['source'],label=inverse[r['index']],negative=inverse[r['index']]=='contour-fragment') for r,p in zip(rows,predictions)]
    assert all(a['id']==b['id'] for a,b in zip(rows,predictions))
    bylabel={lab:dict(count=sum(p['label']==lab for p in joined),flags=sum(p['label']==lab and p['reject'] for p in joined)) for lab in sorted(set(inverse.values()))}
    noise=[p for p in joined if p['negative']];protected=[p for p in joined if not p['negative']]
    hits=sum(p['reject'] for p in noise);loss=sum(p['reject'] for p in protected)
    byedition={s:dict(contours=sum(p['negative'] for p in joined if p['source']==s),hits=sum(p['negative'] and p['reject'] for p in joined if p['source']==s),protected_flags=sum(not p['negative'] and p['reject'] for p in joined if p['source']==s)) for s in sorted({p['source'] for p in joined})}
    # Reload and reproduce held-out predictions. Re-extract structural features in CPU runtime.
    from PIL import Image
    arr=np.load(OUT/'holdout-features.npz');ss=[]
    for r in rows:
        with Image.open(ROOT/r['context']) as im:ss.append(extract(im.convert('RGB'),r['context_box'])['appearance-structure'][-18:])
    np.testing.assert_array_equal(np.array(ss),arr['structure'])
    model=cv2.ml.RTrees_load(str(OUT/f"{lock['winner']}.xml"))
    repeated=predict(model,np.column_stack([arr['vectors'],ss]).astype(np.float32))
    np.testing.assert_array_equal(repeated,[p['score'] for p in predictions])
    summary=dict(contours=len(noise),contour_hits=hits,protected=len(protected),protected_flags=loss,
        by_label=bylabel,by_edition=byedition,removal_gate=hits>=.25*len(noise) and loss==0,
        deployment='Offline only: no confirmed Kana or rare POI symbols in this holdout; safety coverage insufficient even if removal gate passes.',
        labels_sha256=sha(OUT/'holdout-labels.json'),predictions_sha256=lock['predictions_sha256'],
        verification='All48 saved-model scores exactly reproduced; CPU/GPU runtime structural features identical',
        limitation='48 targets from frozen geography; only one tested model; assistant visual labels, not independently human-verified; single small holdout, not a population guarantee.')
    write(OUT/'holdout-evaluation.json',dict(summary=summary,rows=joined));print(__import__('json').dumps(summary,indent=2))


if __name__=='__main__':main()
