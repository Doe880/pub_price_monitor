import json
from pathlib import Path
import pytest
from monitor.parsers import parse_dubliner, parse_beeftime, parse_tilda_product, parse_tilda, tilda_parts
from monitor.models import Item, volume, deduplicate

FIX = Path(__file__).parent/'fixtures'


def fixture(name):
    return (FIX/name).read_text(encoding='utf-8')


def test_dubliner_food_separates_hot_food_from_snacks_and_salads():
    rows, notes = parse_dubliner(fixture('dubliner_food.html'),{'kind':'food'})
    by_name = {i.name:i for i in rows}
    assert len(rows)==17 and not notes
    assert by_name['Пастуший пирог'].price==920
    assert by_name['Рибай'].price==2980
    assert 'Цезарь с курицей' not in by_name
    assert not any('гренки' in r.name.lower() for r in rows)


def test_dubliner_pairs_prices_with_correct_volumes_and_uptitles():
    rows, notes = parse_dubliner(fixture('dubliner_beer.html'),{'kind':'beer'})
    assert not notes
    guinness = [r for r in rows if r.name=='Гиннесс']
    assert {(r.volume_ml,r.price) for r in guinness}=={(280,700),(568,900)}
    assert any(r.name=='Локал Крик' for r in rows)
    assert any(r.name=='БрюДог Панк ИПА' for r in rows)
    assert not any('Galipette' in r.name for r in rows)
    assert all(r.alcohol_free for r in rows if r.name=='Guinness')


def test_beeftime_per_100g_not_same_as_portion_and_no_wine():
    food, notes = parse_beeftime(fixture('beeftime.html'),{'kind':'food'})
    assert not notes and len(food)==39
    by100 = [r for r in food if r.price_basis=='100 г']
    assert len(by100)==4
    assert all(r.weight_g is None for r in by100)
    beer, notes = parse_beeftime(fixture('beeftime.html'),{'kind':'beer'})
    assert not notes
    assert len(beer)==14
    beef = [r for r in beer if 'Биф Тайм' in r.name]
    assert {(r.volume_ml,r.price) for r in beef}=={(300,319),(400,419),(800,739)}


def test_tilda_uses_variant_price_not_minimum_price():
    p = json.loads(fixture('tilda_draft.json'))['products'][0]
    rows,w = parse_tilda_product(p,'Разливное пиво','beer')
    assert {(r.volume_ml,r.price) for r in rows}=={(500,590),(250,390)}
    assert not w


def test_delirium_food_description_prices_and_component_weight():
    p = json.loads(fixture('delirium_food.json'))['products'][1]
    rows,w = parse_tilda_product(p,'Горячее','food')
    assert rows[0].price==1150 and rows[0].portion=='170/150/80 г'
    assert rows[0].weight_g==400
    assert not w


def test_bad_source_volume_is_preserved_but_not_normalized():
    p={'title':'Tripel Lefort','descr':'0,33 мл -610 р','editions':[]}
    rows,w = parse_tilda_product(p,'Светлый эль','beer')
    assert rows[0].price==610
    assert rows[0].volume_ml is None
    assert rows[0].note and w
    rows[0].validate()


def test_volume_does_not_use_abv_or_unitless_value():
    assert volume('5,4% 0,33') is None
    assert volume('5,4%, 0,33л')==330
    assert volume('568 мл')==568


def test_conflicting_duplicate_prices_fail():
    a=Item('Тест','Пиво','Пиво',500,evidence='Тест 500')
    b=Item('Тест','Пиво','Пиво',600,evidence='Тест 600')
    with pytest.raises(ValueError,match='Конфликт'):
        deduplicate([a,b])


def test_changed_page_cannot_be_empty_success():
    with pytest.raises(ValueError):
        parse_dubliner('<html>Ошибка сайта</html>',{'kind':'food'})
    with pytest.raises(ValueError):
        parse_tilda('<html>Ошибка сайта</html>',{'sections':['Горячее'],'kind':'food'},None)


def test_incomplete_tilda_catalog_is_rejected():
    html="<div class='r'>Горячее</div><div class='r'><script>var x={storepart:'123'};</script></div>"
    class Fetch:
        def get(self,*args,**kwargs):
            return {'partuid':123,'total':20,'products':[]}
    with pytest.raises(ValueError,match='не полностью'):
        parse_tilda(html,{'kind':'food','sections':['Горячее']},Fetch())


def test_unpriced_variant_never_inherits_another_variants_price():
    product = {'title':'Ламбик','descr':'', 'price':'680', 'editions':[
        {'price':'680','Объем':'250мл','Вкус':'Вишня'},
        {'price':'','Объем':'','Вкус':'Малина'}]}
    rows,warnings = parse_tilda_product(product,'Фруктовое пиво','beer')
    assert len(rows)==1 and rows[0].price==680
    assert 'Вишня' in rows[0].portion
    assert any('без цены' in w for w in warnings)
