"""Build a small active registry from actual, machine-readable live collection evidence.

No record is irreversibly lost: a separate archive holds the original 106 pubs.
Use only successful or partial real source snapshots with at least one observed price.
"""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

VALID = {"ok", "partial"}
FIELDS = ["Паб", "Округ", "Адрес", "Категория", "Статус",
          "Причина / ограничение", "Проверено", "Ссылка"]


def select_active(pubs, checks):
    valid = {c["source"] for c in checks
             if c.get("status") in VALID and int(c.get("count") or 0) > 0}
    kept, removed = [], []
    for pub in pubs:
        good_sources = [s for s in pub["sources"] if s["id"] in valid]
        if not good_sources:
            removed.append(pub)
            continue
        p = dict(pub)
        p["sources"] = good_sources
        p["registry_status"] = "Получены цены из опубликованного меню"
        for kind in ("food", "beer"):
            c = dict(p["coverage"][kind])
            matching = [s for s in good_sources if s["kind"] == kind]
            if matching:
                c["state"] = "connected"
                c["status"] = "Получены цены"
                c["reason"] = "Последний полный аудит подтвердил извлечение цен; см. price_audit_results.json."
                c["source_ids"] = [s["id"] for s in matching]
            else:
                c["state"] = "unavailable"
                c["status"] = "Нет подтверждённых цен"
                c["reason"] = "В полном аудите не получено валидных цен в этой категории"
                c["source_ids"] = []
            p["coverage"][kind] = c
        kept.append(p)
    return kept, removed


def coverage_rows(pubs):
    return [{
        "Паб":p["name"],"Округ":p["district"],"Адрес":p["address"],
        "Категория":label,"Статус":p["coverage"][k]["status"],
        "Причина / ограничение":p["coverage"][k]["reason"],
        "Проверено":p["coverage"][k]["checked_on"],
        "Ссылка":p["coverage"][k]["evidence_url"]
    } for p in pubs for k,label in (("food","Горячее"),("beer","Пиво"))]


def save_outputs(pubs, checks, root):
    kept, removed = select_active(pubs, checks)
    root.mkdir(parents=True, exist_ok=True)
    (root/"sources.json").write_text(json.dumps(kept,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (root/"archive"/"excluded_pubs.json").parent.mkdir(parents=True,exist_ok=True)
    (root/"archive"/"excluded_pubs.json").write_text(json.dumps(removed,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (root/"price_audit_results.json").write_text(json.dumps(checks,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    rows=coverage_rows(kept)
    (root/"coverage_audit.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (root/"COVERAGE_AUDIT.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return kept,removed


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--registry",default="archive/pubs_before_price_cleanup_2026-11-18.json")
    parser.add_argument("--audit",required=True,help="JSON array of actual collection results from all shards")
    parser.add_argument("--output-dir",required=True)
    args=parser.parse_args()
    archived=json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pubs=archived["pubs"] if isinstance(archived,dict) else archived
    checks=json.loads(Path(args.audit).read_text(encoding="utf-8"))
    kept,removed=save_outputs(pubs,checks,Path(args.output_dir))
    print(f"Active: {len(kept)}, removed: {len(removed)}, checked: {len(checks)}")
    if not kept:
        raise SystemExit("No verified prices: refusing to replace active registry with empty data")


if __name__=="__main__":
    main()
