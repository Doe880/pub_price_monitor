from monitor.config import load_sources
from monitor.parsers import tilda_parts


def test_expanded_registry_unique_branch_ids_and_official_sources():
    pubs=load_sources()
    assert len(pubs)==100
    assert len({p['id'] for p in pubs})==len(pubs)
    assert len({p['name'] for p in pubs})==len(pubs)
    assert {p['district'] for p in pubs}=={'ЦАО','САО','СВАО'}
    assert sum(bool(p['sources']) for p in pubs) >= 21
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
