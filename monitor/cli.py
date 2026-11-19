import argparse
import csv
import logging
import sys
from pathlib import Path
from .collector import collect
from .config import DATA,load_sources
from .storage import sync_sources,current_rows,diagnostics,review_check,approve_ocr_check


def main():
    parser = argparse.ArgumentParser(description='Мониторинг официальных меню пабов Москвы')
    parser.add_argument('command',choices=['collect','status','export','review','approve'])
    parser.add_argument('--only',nargs='+',help='ID пабов или источников из sources.json')
    parser.add_argument('--output',default='data/latest_prices.csv')
    parser.add_argument('--check-id',type=int,help='ID OCR-проверки для сверки или подтверждения')
    parser.add_argument('--approver',help='Имя человека, проверившего исходное меню')
    parser.add_argument('--confirm-reviewed',action='store_true',help='Подтвердить, что каждый ряд проверен по оригиналу')
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
        if args.command in ('review','approve'):
            if not args.check_id:
                raise ValueError('Нужно указать --check-id')
            check,rows=review_check(args.check_id)
            print(f"Источник: {check['source_id']}; снимок: {check['raw_path']}; статус: {check['status']}")
            for item in rows:
                print(f"{item['name']} | {item['portion']} | {item['price']} ₽ | {item['evidence']}")
            if args.command == 'approve':
                if not args.confirm_reviewed or not args.approver:
                    raise ValueError('После ручной сверки каждого ряда нужны --approver и --confirm-reviewed')
                approve_ocr_check(args.check_id,args.approver)
                print('OCR снимок подтверждён вручную; действие записано в approvals')
            return 0
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
