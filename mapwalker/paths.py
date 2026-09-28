import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def default_data():
    configured=os.environ.get('MAPWALKER_DATA')
    local=ROOT/'.mapwalker-local.json'
    if not configured and local.exists():
        configured=json.loads(local.read_text('utf-8')).get('data_path')
    return Path(configured).expanduser().resolve() if configured else ROOT/'data'
