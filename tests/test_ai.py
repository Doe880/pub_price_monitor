import pandas as pd
import pytest
from monitor import ai


def df():
    return pd.DataFrame([dict(fresh=True,pub='Паб',district='ЦАО',name='Лагер',category='Пиво',
        subcategory='Разливное',price=500,portion='500 мл',price_basis='порция',serving_type='Разливное',
        alcohol_free=False,price_500ml=500,previous_price=None,change_pct=None,source_url='https://example.org',
        change_rub=None,series_key='s:1')])


def test_no_key_is_clear_error(monkeypatch):
    monkeypatch.delenv('AI_API_KEY',raising=False)
    with pytest.raises(RuntimeError,match='AI_API_KEY'):
        ai.summarize(df())


def test_ai_request_bounded_and_cached(monkeypatch,tmp_path):
    monkeypatch.setenv('AI_API_KEY','test-key')
    monkeypatch.setattr(ai,'DATA',tmp_path)
    calls=[]
    class Response:
        status_code=200
        def json(self):
            return {'choices':[{'finish_reason':'stop','message':{'content':'Тестовая сводка'}}]}
    def post(url,**kwargs):
        calls.append(kwargs)
        assert kwargs['allow_redirects'] is False
        assert kwargs['json']['max_completion_tokens']==1800
        return Response()
    monkeypatch.setattr(ai.requests,'post',post)
    assert ai.summarize(df())=='Тестовая сводка'
    assert ai.summarize(df())=='Тестовая сводка'
    assert len(calls)==1


def test_truncated_ai_not_presented_as_complete(monkeypatch,tmp_path):
    monkeypatch.setenv('AI_API_KEY','test-key')
    monkeypatch.setattr(ai,'DATA',tmp_path)
    class Response:
        status_code=200
        def json(self):
            return {'choices':[{'finish_reason':'length','message':{'content':'Неполный'}}]}
    monkeypatch.setattr(ai.requests,'post',lambda *a,**kw:Response())
    with pytest.raises(RuntimeError,match='неполный'):
        ai.summarize(df())


def deal_df():
    rows=[]
    for i in range(6):
        common=dict(fresh=True,pub=f'Паб {i}',pub_id=f'p{i}',district='ЦАО',
            category='Пиво',subcategory='Разливное',price=300+i*20,portion='500 мл',
            price_basis='порция',serving_type='Разливное',alcohol_free=False,
            volume_ml=500,price_500ml=300+i*20,previous_price=None,change_pct=None,
            source_url=f'https://example.org/{i}',change_rub=None,series_key=f's{i}:beer',
            price_channel='venue',source_id=f's{i}',name=f'Лагер {i}')
        rows.append(common)
        burger=common.copy()
        burger.update(category='Горячие блюда',subcategory='Бургеры',
            name=f'Бургер {i}',price=450+i*50,portion='300 г',price_basis='порция',
            volume_ml=None,price_500ml=None,serving_type='',series_key=f's{i}:burger')
        rows.append(burger)
    return pd.DataFrame(rows)


def test_best_deals_are_separate_and_ranked_by_comparable_price():
    data=deal_df()
    beer=ai.best_deal_rows(data,'beer',5)
    burgers=ai.best_deal_rows(data,'burgers',5)
    assert len(beer)==5 and len(burgers)==5
    assert beer['deal_price'].tolist()==[300,320,340,360,380]
    assert burgers['deal_price'].tolist()==[450,500,550,600,650]
    assert set(beer['category'])=={'Пиво'}
    assert set(burgers['category'])=={'Горячие блюда'}


def test_best_deals_exclude_stale_and_delivery_prices():
    data=deal_df()
    data.loc[data.index[0:2], 'fresh']=False
    data.loc[data.index[2:4], 'price_channel']='delivery'
    assert len(ai.best_deal_rows(data,'beer',5))==4


def test_burger_ranking_requires_five_positions():
    data=deal_df()
    data=data[data['category']!='Горячие блюда']
    with pytest.raises(RuntimeError,match='требуется минимум 5'):
        ai.summarize_best_deals(data,'burgers',5)


def test_ai_settings_can_read_streamlit_secrets(monkeypatch):
    monkeypatch.delenv('AI_API_KEY',raising=False)
    class Secrets:
        def get(self,key,default=''):
            return {'AI_API_KEY':'cloud-secret','AI_BASE_URL':'https://api.example.org/v1'}.get(key,default)
    class FakeStreamlit:
        secrets=Secrets()
    monkeypatch.setitem(__import__('sys').modules,'streamlit',FakeStreamlit())
    assert ai.setting('AI_API_KEY')=='cloud-secret'
    assert ai.setting('AI_BASE_URL')=='https://api.example.org/v1'


def test_best_deals_accept_localized_venue_label_after_ui_formatting():
    data=deal_df()
    data['price_channel']='В заведении'
    assert len(ai.best_deal_rows(data,'beer',5))==5
    assert len(ai.best_deal_rows(data,'burgers',5))==5


def test_burger_shortlist_detects_burger_section_even_if_name_is_generic():
    data=deal_df()
    mask=data['category']=='Горячие блюда'
    data.loc[mask,'name']=[f'Фирменный сэндвич {i}' for i in range(mask.sum())]
    data.loc[mask,'subcategory']='Бургеры'
    assert len(ai.best_deal_rows(data,'burgers',5))==5


def test_deal_scope_ignores_ui_category_and_search_filters_but_honors_pubs():
    data=deal_df()
    data['district']='ЦАО'
    scoped=ai.deal_scope(data,districts=['ЦАО'],pubs=['Паб 0','Паб 1'])
    assert set(scoped['pub'])=={'Паб 0','Паб 1'}
    assert len(ai.best_deal_rows(scoped,'beer',5))==2
    assert len(ai.best_deal_rows(scoped,'burgers',5))==2


def test_deal_scope_excludes_delivery_even_if_selected_pub_has_delivery_prices():
    data=deal_df()
    data['district']='ЦАО'
    data.loc[data.index[0:4],'price_channel']='delivery'
    scoped=ai.deal_scope(data,districts=['ЦАО'],pubs=None)
    assert not scoped['price_channel'].eq('delivery').any()
    assert len(ai.best_deal_rows(scoped,'beer',5))==4
