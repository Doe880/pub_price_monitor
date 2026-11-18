import pytest
from monitor.chelsea import parse_chelsea


def build(section, name, price, desc=''):
    return (f'<h2>{section}</h2><ul><li><div class="menuPage-menuContent__title">{name}</div>'
            f'<div class="menuPage-menuContent__subtitle">{desc}</div>'
            f'<div class="menuPage-menuContent__priceContainer">{price} ₽</div></li></ul>')


def test_chelsea_hot_food_and_100g():
    html=('<html>'+build('Закуски','Тар-тар','970')
          +build('Блюда на огне','Рибай','1250','цена указана за 100гр.')
          +build('Горячие блюда','Филе лосося','2100')
          +build('Ром','Whisky','490')+'</html>')
    rows,notes=parse_chelsea(html,{'kind':'food','min_items':2})
    assert [(x.name,x.price) for x in rows]==[('Рибай',1250),('Филе лосося',2100)]
    assert rows[0].price_basis=='100 г'
    assert not notes


def test_chelsea_beer_and_cider_safety():
    html=('<html>'+build('Разливное пиво','Lager','520','Объем: 500мл')
          +build('Разливное пиво','Яблочный сидр','440','Объем: 500мл')
          +build('Бутылочное пиво','Stout','680','0,44л')+'</html>')
    rows,notes=parse_chelsea(html,{'kind':'beer','min_items':2})
    assert len(rows)==2
    assert [r.volume_ml for r in rows]==[500,440]
    assert not notes


def test_chelsea_missing_section_is_error():
    with pytest.raises(ValueError,match='не найдены разделы'):
        parse_chelsea(build('Горячие блюда','Рыба','980'),{'kind':'food'})
