from monitor.config import load_sources
from monitor.parsers import tilda_parts


def test_expanded_registry_unique_branch_ids_and_official_sources():
    pubs=load_sources()
    assert 1 <= len(pubs) <= 106
    assert all(p['sources'] for p in pubs)
    assert len({p['id'] for p in pubs})==len(pubs)
    assert len({p['name'] for p in pubs})==len(pubs)
    assert {p['district'] for p in pubs} <= {'ЦАО','САО','СВАО'}
    assert sum(bool(p['sources']) for p in pubs) == len(pubs)
    for p in pubs:
        for s in p['sources']:
            assert s['url'].startswith('https://')
            assert 'moscowpubs.ru' not in s['url'] and 'edanyama.ru' not in s['url']
        assert set(p['coverage']) == {'food','beer'}
        for kind, audit in p['coverage'].items():
            assert audit['reason'] and audit['checked_on'] and audit['evidence_url']
            assert (audit['state']=='connected') == any(s['kind']==kind for s in p['sources'])


def test_duplicate_irrelevant_tilda_sections_do_not_break_selected_menu():
    html='''<div class="r">Горячее</div><div class="r"><script>var x={storepart:'123'};</script></div>
    <div class="r">Другое</div><div class="r"><script>var x={storepart:'456'};</script></div>
    <div class="r">Другое</div><div class="r"><script>var x={storepart:'789'};</script></div>'''
    assert tilda_parts(html,{'Горячее'})=={'Горячее':'123'}


def test_invalid_official_edition_volume_is_not_corrected_by_guess():
    from monitor.parsers import parse_tilda_product
    p={'title':'Harp Irish Lager 4%, 0,44ml','editions':[{'price':'960'}]}
    rows,notes=parse_tilda_product(p,'Бутылочное пиво','beer')
    assert len(rows)==1 and rows[0].price==960
    assert rows[0].volume_ml is None and rows[0].note
    assert rows[0].portion=='0.44 мл (как на сайте)'
    rows[0].validate()


def test_removed_pubs_retained_in_separate_archive():
    import json
    from monitor.config import ROOT
    active={p["id"] for p in load_sources()}
    original=json.loads((ROOT/"archive"/"pubs_before_price_cleanup_2026-11-18.json").read_text(encoding="utf-8"))["pubs"]
    assert len(original)==106
    assert active <= {p["id"] for p in original}
    assert active
    if (ROOT/"price_audit_results.json").exists():
        audits=json.loads((ROOT/"price_audit_results.json").read_text(encoding="utf-8"))["results"]
        verified={r["source"] for r in audits if r["status"] in {"ok","partial"} and r["count"]>0}
        for pub in load_sources():
            assert all(s["id"] in verified for s in pub["sources"])
