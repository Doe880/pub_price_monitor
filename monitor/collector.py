import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4
from filelock import FileLock, Timeout
from .config import DATA, DB, load_sources
from .fetch import Fetcher
from .parsers import parse
from .storage import sync_sources, save_check, last_good

log = logging.getLogger(__name__)


def collect(only=None, progress=None):
    pubs = load_sources()
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(DATA/'collector.lock'), timeout=0):
            sync_sources(pubs)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:6]
            run_dir = DATA / 'snapshots' / stamp
            hosts = {urlsplit(s['url']).hostname for p in pubs for s in p['sources']}
            fetcher = Fetcher(run_dir, hosts)
            results = []
            sources = [(p,s) for p in pubs if p.get('enabled',True) for s in p['sources']
                       if s.get('enabled',True) and (not only or p['id'] in only or s['id'] in only)]
            if only and not sources:
                raise ValueError('Не найден выбранный паб/источник')
            try:
                for index,(pub,s) in enumerate(sources):
                    if progress:
                        progress(index,len(sources),pub['name']+' / '+s['kind'])
                    rows = []
                    try:
                        html = (fetcher.get_dynamic(s['url'], s) if s.get('format') == 'browser'
                                else fetcher.get(s['url'], kind=s.get('format','html')))
                        rows,notes = parse(html,s,fetcher)
                        old = last_good(s['id'])
                        if len(rows) < s.get('min_items',1):
                            status = 'review'
                            notes.insert(0,'Подозрительно мало позиций; данные не заменили прошлый снимок')
                        elif old and len(rows) < old['count']*0.65:
                            status = 'review'
                            notes.insert(0,'Число позиций упало более чем на 35%; нужна проверка')
                        else:
                            # Missing volume is transparent but does not invalidate a price.
                            serious = [n for n in notes if not n.startswith(('Объём не указан:', 'Объём требует проверки:'))]
                            status = 'partial' if serious else 'ok'
                        message = '\n'.join(notes)
                    except Exception as exc:
                        status = 'error'
                        message = type(exc).__name__ + ': ' + str(exc)
                        log.warning('%s: %s',s['id'],message)
                    raw_path = str(run_dir.relative_to(DATA))
                    save_check(s['id'],status,rows,message,raw_path)
                    result = dict(source=s['id'],pub=pub['name'],status=status,count=len(rows),message=message)
                    results.append(result)
                    log.info('%s: %s, %s позиций',s['id'],status,len(rows))
                (run_dir/'run.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
                if progress:
                    progress(len(sources),len(sources),'Готово')
                return results
            finally:
                fetcher.close()
    except Timeout as exc:
        raise RuntimeError('Сбор уже выполняется другим процессом. Дождитесь его завершения.') from exc
