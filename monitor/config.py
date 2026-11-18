import json
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
DATA = Path(os.getenv('DATA_DIR', 'data'))
if not DATA.is_absolute():
    DATA = ROOT / DATA
DB = DATA / 'monitor.sqlite3'
ALLOWED_DISTRICTS = {'ЦАО', 'САО', 'СВАО'}


def load_sources():
    pubs = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
    ids = set()
    for pub in pubs:
        if pub['district'] not in ALLOWED_DISTRICTS:
            raise ValueError(f"Недопустимый округ: {pub['district']}")
        for source in pub['sources']:
            if source['id'] in ids:
                raise ValueError('Повтор идентификатора источника')
            ids.add(source['id'])
    return pubs
