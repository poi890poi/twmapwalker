"""Stage a new official Rudy theme archive; review the resulting Git diff before promotion."""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mapwalker.rudy_style import build_style


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, help='Downloaded official Rudy hs_style.zip')
    parser.add_argument('--source-url', required=True, help='Record the actual download URL')
    args = parser.parse_args()
    policy = json.loads((ROOT/'styles/rudy/enhancements.json').read_text())
    with tempfile.TemporaryDirectory() as temp:
        staging = Path(temp)
        with zipfile.ZipFile(args.archive) as archive:
            for member in archive.infolist():
                target = (staging / member.filename).resolve()
                if not target.is_relative_to(staging.resolve()):
                    raise ValueError('Archive path outside staging directory')
            archive.extractall(staging)
        report = build_style(staging/'MOI_OSM.xml', staging/'bochengsiong.xml', policy)
        # The current upstream directory remains intact until the new theme validates.
        upstream = ROOT/'styles/rudy/upstream'
        for path in staging.rglob('*'):
            if path.is_file() and path.suffix.lower() in ('.xml','.svg','.png','.txt'):
                destination = upstream/path.relative_to(staging)
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(path,destination)
        (upstream/'bochengsiong.build.json').write_text(json.dumps(report,indent=2)+'\n')
        provenance = json.loads((ROOT/'styles/rudy/provenance.json').read_text())
        provenance['rudy_theme'] = dict(url=args.source_url, archive_sha256=hashlib.sha256(args.archive.read_bytes()).hexdigest(),
                                        xml_sha256=report['upstream_sha256'])
        (ROOT/'styles/rudy/provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print('Theme staged. Review Git diff, run tests and render comparisons before restarting Mapwalker.')


if __name__ == '__main__':
    main()
