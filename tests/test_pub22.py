from pathlib import Path
import pytest
from monitor.pub22 import parse_pub22
from monitor.parsers import parse

HTML=(Path(__file__).parent/'fixtures/pub22.html').read_text(encoding='utf-8')
FOOD={'parser':'pub22','kind':'food','sections':['Горячие блюда','Бургеры и паста']}
BEER={'parser':'pub22','kind':'beer','sections':['Разливное пиво','Бутылочное пиво','Пиво безалкогольное']}


def test_official_food_sections_and_known_prices():
    rows,warnings=parse(HTML,FOOD,None)
    assert len(rows)==23 and not warnings
    prices={r.name:r.price for r in rows}
    assert prices['Томленые говяжьи щечки с картофельным пюре']==990
    assert prices['Бургер Джуси Люси']==830
    assert all(r.category=='Горячие блюда' for r in rows)


def test_beer_pairs_prices_without_inventing_units():
    rows,warnings=parse_pub22(HTML,BEER)
    assert len(rows)==33
    draft=[r for r in rows if r.name=='Фирменное светлое']
    assert {(r.portion,r.price) for r in draft}=={
        ('0,3 (единица не указана)',360),('0,5 (единица не указана)',420)}
    assert all(r.volume_ml is None and r.note for r in rows)
    assert len({r.key for r in rows})==33
    assert len([r for r in rows if r.alcohol_free])==2
    assert not any('сидр' in r.name.lower() or 'сет' in r.name.lower() for r in rows)
    assert warnings


def test_abv_not_used_as_portion():
    rows,_=parse_pub22(HTML,BEER)
    row=next(r for r in rows if 'Гиннесс' in r.name)
    assert '4,2%' in row.name and row.portion.startswith('0,44') and row.price==700


def test_missing_section_does_not_become_empty_success():
    with pytest.raises(ValueError,match='раздел'):
        parse_pub22('<html>Технические работы</html>',FOOD)


def test_unmatched_beer_prices_fail_instead_of_guessing():
    bad=HTML.replace('360/420','360',1)
    with pytest.raises(ValueError,match='Число порций'):
        parse_pub22(bad,BEER)
