from monitor.models import Item
from monitor import storage
from monitor.analytics import frame, comparable_beer


def setup_db(tmp_path):
    path=tmp_path/'test.sqlite3'
    pub=dict(id='p',name='Паб',district='ЦАО',area='Тверской',address='Москва',sources=[dict(id='s',url='https://example.org/')])
    storage.sync_sources([pub],path)
    return path


def item(price=500,portion='500 мл',name='Лагер'):
    return Item(name,'Пиво','Разливное пиво',price,portion,500 if portion=='500 мл' else 250,
                serving_type='Разливное',evidence=f'{name} {price}')


def test_first_snapshot_has_no_invented_history(tmp_path):
    path=setup_db(tmp_path)
    storage.save_check('s','ok',[item()],path=path)
    rows=storage.current_rows(path)
    assert rows[0]['previous_price'] is None
    assert rows[0]['change_rub'] is None
    assert storage.events(path)==[]


def test_error_does_not_delete_prices_or_create_removals(tmp_path):
    path=setup_db(tmp_path)
    storage.save_check('s','ok',[item()],path=path)
    storage.save_check('s','error',[],message='Timeout',path=path)
    rows=storage.current_rows(path)
    assert len(rows)==1 and rows[0]['price']==500
    assert rows[0]['source_status']=='error'
    assert not frame(rows).iloc[0]['fresh']
    assert storage.events(path)==[]


def test_partial_and_review_cannot_overwrite_complete_snapshot(tmp_path):
    path=setup_db(tmp_path)
    storage.save_check('s','ok',[item()],path=path)
    storage.save_check('s','partial',[item(600)],path=path)
    storage.save_check('s','review',[item(900)],path=path)
    assert storage.current_rows(path)[0]['price']==500
    assert storage.events(path)==[]


def test_changes_compare_same_portion_and_failed_runs_are_skipped(tmp_path):
    path=setup_db(tmp_path)
    storage.save_check('s','ok',[item(),item(300,'250 мл')],path=path)
    storage.save_check('s','error',[],path=path)
    storage.save_check('s','ok',[item(600)],path=path)
    row=storage.current_rows(path)[0]
    assert row['previous_price']==500 and row['change_pct']==20
    ev=storage.events(path)
    assert {x['event'] for x in ev}=={'Цена изменилась','Не найдена в новом меню'}


def test_beer_comparison_does_not_double_count_servings(tmp_path):
    path=setup_db(tmp_path)
    storage.save_check('s','ok',[item(),item(300,'250 мл')],path=path)
    df=comparable_beer(frame(storage.current_rows(path)))
    assert len(df)==1
    assert df.iloc[0]['price_500ml']==500


def test_old_observation_excluded_from_fresh_comparison(tmp_path):
    path=setup_db(tmp_path)
    storage.save_check('s','ok',[item()],checked_at='2020-01-01T00:00:00+00:00',path=path)
    assert comparable_beer(frame(storage.current_rows(path))).empty
