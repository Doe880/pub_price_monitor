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
