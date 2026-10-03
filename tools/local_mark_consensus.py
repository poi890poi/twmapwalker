"""Separate rank-based calibration pilot motivated by saturated sigmoid scores."""
import numpy as np
from .contour_learner_data import ROOT,read,write,sha
from .local_mark_data import OUT,SEEDS


def main():
    if (OUT/'consensus-lock.json').exists():raise RuntimeError('Consensus already locked')
    write(OUT/'consensus-contract.json',dict(reason='Absolute0.025 probability margin exceeds1 for saturated learned heads despite useful ranking. Test a separately declared calibration mechanism rather than claim all representations failed.',
        model='Fixed200-epoch max-pooling heads, same three seeds. Chosen for localized question; no search over architectures for this calibration pilot.',
        cutoff='Per seed maximum protected score across spatial OOF training targets,58 guard targets and30 protected/uncertain targets from consumed48 challenge. Require strict exceedance for all three seeds.',
        interpretation='Guards and consumed challenge now calibrate this pilot and are not independent safety evidence. No probabilistic or conformal guarantee. Rule is invariant to strictly monotonic score transforms except finite-precision ties, which retain.',
        gate='At least24/96 OOF contour hits and more than2/33 on1924 under these locked cutoffs; then evaluate this one candidate on40 fresh geographically excluded targets.',
        fresh_acceptance='At least25% confirmed contours removed,zero protected/uncertain flags. No threshold tuning. Kana/rare-symbol coverage still required before automatic hiding.',
        rationale='Replaces arbitrary score-unit buffer with agreement across independently seeded models; this is not independent expert agreement. Fresh evidence decides whether the change helps.'))
    rows=read(OUT/'training.json');guards=read(OUT/'guards.json');challenge=read(OUT/'challenge.json');allrows=rows+guards+challenge
    scores=np.load(OUT/'stage1-max-scores.npy');protect=np.array([not r['negative'] for r in allrows]);thresholds=scores[:,protect].max(1)
    flags=np.all(scores>thresholds[:,None],axis=0);n=len(rows)
    summary=dict(thresholds=thresholds.tolist(),contour_hits=sum(bool(f and r['negative']) for f,r in zip(flags[:n],rows)),
        hits1924=sum(bool(f and r['negative']) for f,r in zip(flags[:n],rows) if '1924' in r['source']),
        calibrated_protected_flags=int(flags[protect].sum()),calibrated_protected_count=int(protect.sum()),
        challenge_contour_hits=sum(bool(f and r['negative']) for f,r in zip(flags[n+len(guards):],challenge)))
    summary['eligible']=summary['contour_hits']>=24 and summary['hits1924']>2
    write(OUT/'consensus-summary.json',summary)
    write(OUT/'consensus-predictions.json',[dict(id=r['id'],negative=r['negative'],label=r['label'],reject=bool(f),scores=s.tolist()) for r,f,s in zip(allrows,flags,scores.T)])
    states={f'heads/max-s{s}-fall.pt':sha(OUT/'heads'/f'max-s{s}-fall.pt') for s in SEEDS}
    write(OUT/'consensus-lock.json',dict(thresholds=thresholds.tolist(),states=states,eligible=summary['eligible'],
        contract_sha256=sha(OUT/'consensus-contract.json'),code_sha256=sha(ROOT/'tools/local_mark_consensus.py'),
        fresh_sha256=sha(OUT/'fresh-inputs.json'),calibration_scores_sha256=sha(OUT/'stage1-max-scores.npy')))
    print(summary,flush=True)


if __name__=='__main__':main()
