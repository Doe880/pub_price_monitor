import pytest
from monitor.tweed import parse_tweed


def test_tweed_menu_mixed_h2_h3_price_nodes():
    html='''<html><body><h4>Корзина</h4>
    <h2>Пастуший пирог</h2><h3><span>600 руб</span></h3>
    <h2>Свиные ребра су-вид</h2><h3>700 руб</h3>
    <h3>Начос с сыром</h3><h2>500 руб</h2>
    <h3>Хот-дог</h3><h3>500 руб</h3></body></html>'''
    rows,notes=parse_tweed(html,{'kind':'food','min_items':4})
    assert [(x.name,x.price) for x in rows]==[('Пастуший пирог',600),('Свиные ребра су-вид',700),('Начос с сыром',500),('Хот-дог',500)]
    assert not notes


def test_tweed_fails_if_menu_removed():
    with pytest.raises(ValueError,match='недостаточно'):
        parse_tweed('<h3>Корзина</h3><h3>120 руб</h3>',{'kind':'food','min_items':5})


def test_tweed_does_not_infer_beer_prices():
    with pytest.raises(ValueError,match='пивной карты'):
        parse_tweed('<h2>Лагер</h2><h3>500 руб</h3>',{'kind':'beer'})
