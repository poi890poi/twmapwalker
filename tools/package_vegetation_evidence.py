"""Package the verified evidence with repository-relative byte identities."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/vegetation-components'

def main():
    # Editorial spacing is shared by the rendered report and its generator.
    for p in [OUT/'report.html',ROOT/'tools/report_vegetation_components.py']:
        text=p.read_text('utf-8')
        for a,b in [('final36','final 36'),('contain15','contain 15'),('marks,10','marks, 10'),('POIs,2','POIs, 2'),('labels,6','labels, 6'),('and3','and 3'),('includes16','includes 16'),('and20','and 20'),('so15/15','so 15/15'),('the64px','the 64px'),('Controls9','Control 9'),('spring),8','spring), 8'),('and7','and 7'),(').33495','). 33495'),('digit9','digit 9'),('loop53137','loop 53137'),('removes44253','removes 44253'),('blocks100885','blocks 100885'),('POI95054','POI 95054'),('noise17117','noise 17117'),('same252','same 252'),('all36','all 36'),('distinct4x4','distinct 4x4'),('including64px','including 64px')]:text=text.replace(a,b)
        for a,b in [('suggestion.33495','suggestion. 33495'),('All36','All 36'),('sheet1','sheet 1'),('sheet2','sheet 2'),('·252','· 252'),('·296','· 296'),('·44','· 44'),('·36','· 36'),('/49','/ 49'),('/62','/ 62')]:text=text.replace(a,b)
        text=text.replace('Desktop CPU full-service time:', 'Desktop CPU audit wall time (service plus frozen crop encoding/writing):')
        text=text.replace('No browser/network latency or throughput claim.', 'Includes audit crop encoding/writing; no browser/network latency or throughput claim.')
        p.write_text(text,encoding='utf-8',newline='\n')
    timing=json.loads((OUT/'timing-summary.json').read_text('utf-8'))
    timing['scope']='Sequential desktop CPU audit; includes cold model startup once, service input decoding/analysis/preview and frozen crop encoding/writing. Component timings exclude audit writes. No browser/network latency or throughput claim.'
    (OUT/'timing-summary.json').write_text(json.dumps(timing,indent=2),'utf-8')
    files=[p for p in OUT.rglob('*') if p.is_file() and p.name!='artifact-manifest.json' and '__pycache__' not in p.parts]
    files += [ROOT/'mapwalker'/n for n in ['vegetation.py','vegetation_evidence.py']]
    files += [ROOT/'tools'/n for n in ['component_vegetation_trial.py','evaluate_vegetation_components.py','vegetation_component_holdout.py','vegetation_v2_holdout.py','audit_vegetation_evidence.py','report_vegetation_components.py','package_vegetation_evidence.py']]
    records=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(files)]
    (OUT/'artifact-manifest.json').write_text(json.dumps(dict(files=records,note='Exact repository bytes; compressed telemetry also records uncompressed hashes in trial-summary.json. App/UI integration is reviewed in the feature commit.'),indent=2),'utf-8')
    print('Packaged',len(files),'artifacts;',sum(r['bytes'] for r in records),'bytes')

if __name__=='__main__':main()
