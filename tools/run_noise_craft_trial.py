"""Reproduce the fixed learned-feature classifier comparison after feature extraction.

Run once using the project Python runtime. Subsequent read-only verification is
available through report_noise_verifier.py; never overwrite a locked model.
"""
import noise_verifier_trial as trial


if __name__ == '__main__':
    base = trial.OUT
    trial.OUT = base / 'craft'
    trial.OUT.mkdir(exist_ok=True)
    if (trial.OUT / 'locked-model.json').exists():
        raise RuntimeError('Frozen model exists; use report_noise_verifier.py for replay')
    for source, destination in [('dataset.json','dataset.json'),
                                ('craft-features.npz','features.npz'),
                                ('new-visual-labels.json','new-visual-labels.json')]:
        (trial.OUT / destination).write_bytes((base / source).read_bytes())
    trial.PARAMS = {**trial.PARAMS, 'features':['craft-mark','craft-context']}
    trial.develop()
    trial.evaluate()
