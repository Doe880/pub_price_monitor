import argparse
import csv
import logging
import sys
from pathlib import Path
from .collector import collect
from .config import DATA,load_sources
from .storage import sync_sources,current_rows,diagnostics


def main():
    parser = argparse.ArgumentParser(description='Мониторинг официальных меню пабов Москвы')
    parser.add_argument('command',choices=['collect','status','export'])
    parser.add_argument('--only',nargs='+',help='ID пабов или источников из sources.json')
    parser.add_argument('--output',default='data/latest_prices.csv')
    args = parser.parse_args()
    DATA.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',handlers=[
        logging.StreamHandler(),logging.FileHandler(DATA/'monitor.log',encoding='utf-8')])
    try:
        if args.command == 'collect':
            results = collect(args.only)
            for r in results:
                print(f"{r['source']}: {r['status']} | {r['count']} позиций")
            return 0 if results and all(r['status']=='ok' for r in results) else 2
        sync_sources(load_sources())
        if args.command == 'status':
            for r in diagnostics():
                print(f"{r['pub']} | {r['id']} | {r['status'] or 'не проверен'} | {r['checked_at'] or '—'}")
        else:
            rows = current_rows()
            if not rows:
                print('Нет наблюдений для экспорта')
                return 2
            path = Path(args.output).resolve()
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('w',encoding='utf-8-sig',newline='') as f:
                writer = csv.DictWriter(f,fieldnames=list(rows[0]),delimiter=';')
                writer.writeheader()
                writer.writerows(rows)
            print(path)
        return 0
    except Exception as exc:
        logging.error('%s',exc)
        return 1


if __name__ == '__main__':
    sys.exit(main())
