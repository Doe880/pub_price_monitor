import json
from monitor.prune_registry import select_active, save_outputs


def candidate(id, sources):
    return dict(id=id,name=id,district='ЦАО',area='Арбат',address='Москва',
                website='https://official.example',sources=sources,
                coverage={k:dict(state='connected',status='Подключено',
                                reason='Проверялось',checked_on='2026-11-18',
                                evidence_url='https://official.example',
                                source_ids=[s['id'] for s in sources if s['kind']==k])
                          for k in ('food','beer')})


def test_prune_removes_no_prices_and_bad_sources_but_preserves_original(tmp_path):
    original=[
        candidate('success',[dict(id='a_food',kind='food',url='https://official.example/a'),
                             dict(id='a_beer',kind='beer',url='https://official.example/b')]),
        candidate('missing',[dict(id='b_food',kind='food',url='https://official.example/c')]),
        candidate('empty',[])
    ]
    checks=[dict(source='a_food',status='ok',count=5),
            dict(source='a_beer',status='error',count=0),
            dict(source='b_food',status='review',count=7)]
    kept,deleted=save_outputs(original,checks,tmp_path)
    assert [p['id'] for p in kept]==['success']
    assert [p['id'] for p in deleted]==['missing','empty']
    assert [s['id'] for s in kept[0]['sources']]==['a_food']
    assert kept[0]['coverage']['beer']['state']=='unavailable'
    assert len(json.loads((tmp_path/'archive'/'excluded_pubs.json').read_text()))==2
    assert len(json.loads((tmp_path/'coverage_audit.json').read_text()))==2
    assert len(original)==3


def test_partial_with_real_rows_counts_as_prices():
    kept,_=select_active([candidate('pub',[dict(id='x',kind='beer')])],
                         [dict(source='x',status='partial',count=12)])
    assert len(kept)==1


def test_zero_price_or_review_does_not_count():
    pubs=[candidate('a',[dict(id='one',kind='beer')])]
    for status,count in [('ok',0),('review',18),('error',18)]:
        kept,_=select_active(pubs,[dict(source='one',status=status,count=count)])
        assert kept==[]
