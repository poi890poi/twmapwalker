"""Install the optional Japanese reader from RapidAI's published model registry."""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mapwalker.paths import default_data
from mapwalker.reading_suggestions import JAPANESE_FILE,JAPANESE_SHA256,JAPANESE_URL

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=default_data());args=parser.parse_args()
    target=args.data/'reading-models'/JAPANESE_FILE
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==JAPANESE_SHA256:
        print('Japanese reader already verified:',target)
    else:
        with urllib.request.urlopen(JAPANESE_URL,timeout=120) as response:payload=response.read(50_000_001)
        if hashlib.sha256(payload).hexdigest()!=JAPANESE_SHA256:raise ValueError('Downloaded model hash mismatch')
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix('.download');temporary.write_bytes(payload);temporary.replace(target)
        print('Installed verified Japanese reader:',target)
