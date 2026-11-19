import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import DB


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@contextmanager
def connect(path=DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA journal_mode=WAL')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init(path=DB):
    with connect(path) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS sources (
          id TEXT PRIMARY KEY, pub_id TEXT NOT NULL, pub TEXT NOT NULL, district TEXT NOT NULL,
          area TEXT NOT NULL, address TEXT NOT NULL, url TEXT NOT NULL, enabled INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS checks (
          id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
          checked_at TEXT NOT NULL, status TEXT NOT NULL, count INTEGER NOT NULL,
          message TEXT NOT NULL, raw_path TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS observations (
          check_id INTEGER NOT NULL REFERENCES checks(id), item_key TEXT NOT NULL,
          name TEXT NOT NULL, category TEXT NOT NULL, subcategory TEXT NOT NULL,
          price REAL NOT NULL CHECK(price>0), portion TEXT NOT NULL, volume_ml REAL,
          weight_g REAL, price_basis TEXT NOT NULL, serving_type TEXT NOT NULL,
          alcohol_free INTEGER NOT NULL, evidence TEXT NOT NULL, note TEXT NOT NULL,
          PRIMARY KEY(check_id,item_key));
        CREATE INDEX IF NOT EXISTS idx_checks_source ON checks(source_id,id);
        CREATE INDEX IF NOT EXISTS idx_obs_key ON observations(item_key,check_id);
        ''')


def sync_sources(pubs, path=DB):
    init(path)
    with connect(path) as c:
        c.execute('UPDATE sources SET enabled=0')
        for pub in pubs:
            for s in pub['sources']:
                c.execute('''INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)
                  ON CONFLICT(id) DO UPDATE SET pub_id=excluded.pub_id,pub=excluded.pub,
                  district=excluded.district,area=excluded.area,address=excluded.address,
                  url=excluded.url,enabled=excluded.enabled''',
                  (s['id'],pub['id'],pub['name'],pub['district'],pub['area'],pub['address'],
                   s['url'],int(pub.get('enabled', True) and s.get('enabled',True))))


def save_check(source_id, status, items, message='', raw_path='', checked_at=None, path=DB):
    with connect(path) as c:
        cur = c.execute('INSERT INTO checks(source_id,checked_at,status,count,message,raw_path) VALUES(?,?,?,?,?,?)',
                        (source_id,checked_at or now(),status,len(items),message,raw_path))
        check_id = cur.lastrowid
        for item in items:
            r = item.record()
            c.execute('''INSERT INTO observations VALUES(:check_id,:item_key,:name,:category,:subcategory,
              :price,:portion,:volume_ml,:weight_g,:price_basis,:serving_type,:alcohol_free,:evidence,:note)''',
              dict(r,check_id=check_id))
        return check_id


def last_good(source_id, path=DB):
    with connect(path) as c:
        row = c.execute("SELECT * FROM checks WHERE source_id=? AND status='ok' ORDER BY id DESC LIMIT 1",(source_id,)).fetchone()
        return dict(row) if row else None



def review_check(check_id, path=DB):
    """Read a quarantined OCR check and its evidence without approving anything."""
    with connect(path) as c:
        check = c.execute('SELECT * FROM checks WHERE id=?', (check_id,)).fetchone()
        if not check:
            raise ValueError('Проверка не найдена')
        rows = [dict(r) for r in c.execute(
            'SELECT name,category,portion,price,evidence FROM observations WHERE check_id=? '
            'ORDER BY name,portion', (check_id,))]
        return dict(check), rows


def approve_ocr_check(check_id, approver, path=DB):
    """Explicit user validation is required; all decisions are audit logged."""
    approver = str(approver).strip()
    if not 2 <= len(approver) <= 100:
        raise ValueError('Укажите проверяющего (2–100 символов)')
    with connect(path) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS approvals (
          check_id INTEGER PRIMARY KEY REFERENCES checks(id),
          approved_at TEXT NOT NULL, approved_by TEXT NOT NULL,
          original_status TEXT NOT NULL)''')
        check = c.execute('SELECT * FROM checks WHERE id=?', (check_id,)).fetchone()
        if not check:
            raise ValueError('Проверка не найдена')
        if check['status'] != 'review' or 'OCR требует ручной сверки' not in check['message']:
            raise ValueError('Подтверждение допускается только для OCR-проверок со статусом review')
        if check['count'] <= 0:
            raise ValueError('В OCR-проверке нет позиций')
        c.execute("INSERT INTO approvals VALUES (?, ?, ?, ?)",
                  (check_id, now(), approver, check['status']))
        c.execute("UPDATE checks SET status='ok', message=message||? WHERE id=?",
                  ('\\nПроверено вручную: '+approver, check_id))
        return check_id


def selected_check(c, source_id):
    # A partially parsed source cannot silently replace a complete historical menu.
    row = c.execute("SELECT * FROM checks WHERE source_id=? AND status='ok' ORDER BY id DESC LIMIT 1",(source_id,)).fetchone()
    return row or c.execute("SELECT * FROM checks WHERE source_id=? AND status='partial' ORDER BY id DESC LIMIT 1",(source_id,)).fetchone()


def current_rows(path=DB):
    rows = []
    with connect(path) as c:
        for s in c.execute('SELECT * FROM sources WHERE enabled=1').fetchall():
            selected = selected_check(c,s['id'])
            if not selected:
                continue
            latest = c.execute('SELECT * FROM checks WHERE source_id=? ORDER BY id DESC LIMIT 1',(s['id'],)).fetchone()
            prev = c.execute("SELECT id FROM checks WHERE source_id=? AND status='ok' AND id<? ORDER BY id DESC LIMIT 1",(s['id'],selected['id'])).fetchone()
            old = {r['item_key']:r['price'] for r in c.execute('SELECT item_key,price FROM observations WHERE check_id=?',(prev['id'],))} if prev else {}
            for r in c.execute('SELECT * FROM observations WHERE check_id=?',(selected['id'],)):
                d = dict(r)
                d.update(pub=s['pub'], pub_id=s['pub_id'], district=s['district'], area=s['area'],
                         address=s['address'], source_id=s['id'], source_url=s['url'],
                         checked_at=selected['checked_at'], last_attempt=latest['checked_at'],
                         source_status=latest['status'], snapshot_status=selected['status'],
                         raw_path=selected['raw_path'], previous_price=old.get(r['item_key']))
                d['change_rub'] = round(d['price']-d['previous_price'],2) if d['previous_price'] else None
                d['change_pct'] = round(100*d['change_rub']/d['previous_price'],2) if d['previous_price'] else None
                d['price_500ml'] = round(d['price']*500/d['volume_ml'],2) if d['volume_ml'] else None
                d['series_key'] = s['id'] + ':' + d['item_key']
                rows.append(d)
    return rows


def history_rows(path=DB):
    with connect(path) as c:
        return [dict(r) for r in c.execute('''SELECT o.*, c.checked_at,c.source_id,c.status,
          s.pub,s.district,s.url source_url FROM observations o JOIN checks c ON c.id=o.check_id
          JOIN sources s ON s.id=c.source_id WHERE s.enabled=1 AND c.status IN ('ok','partial') ORDER BY c.id''')]


def diagnostics(path=DB):
    with connect(path) as c:
        return [dict(r) for r in c.execute('''SELECT s.*,c.checked_at,c.status,c.count,c.message,
          (SELECT max(checked_at) FROM checks g WHERE g.source_id=s.id AND g.status='ok') last_success
          FROM sources s LEFT JOIN checks c ON c.id=(SELECT max(id) FROM checks WHERE source_id=s.id)
          WHERE s.enabled=1 ORDER BY s.pub,s.id''')]


def events(path=DB):
    out = []
    with connect(path) as c:
        for s in c.execute('SELECT * FROM sources WHERE enabled=1').fetchall():
            previous = None
            for check in c.execute("SELECT * FROM checks WHERE source_id=? AND status='ok' ORDER BY id",(s['id'],)).fetchall():
                current = {r['item_key']:dict(r) for r in c.execute('SELECT * FROM observations WHERE check_id=?',(check['id'],))}
                if previous is not None:
                    for key in sorted(set(current)|set(previous)):
                        a,b = previous.get(key),current.get(key)
                        change = ('Появилась в меню' if not a else 'Не найдена в новом меню' if not b
                                  else 'Цена изменилась' if a['price']!=b['price'] else '')
                        if change:
                            item = b or a
                            out.append(dict(pub=s['pub'],district=s['district'],source_id=s['id'],
                                checked_at=check['checked_at'],event=change,name=item['name'],
                                category=item['category'],portion=item['portion'],item_key=key,
                                old_price=a['price'] if a else None,new_price=b['price'] if b else None,
                                source_url=s['url']))
                previous = current
    return out
