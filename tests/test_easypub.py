import pytest
from monitor.easypub import parse_easypub


def config():
    return dict(kind="food", parser="easypub", price_channel="delivery", min_items=3)


def test_easy_pub_delivery_hot_food_only():
    html = """<html><body>
      <a>Раскаленная сковородка</a><a>Гриль/ пасты</a><a>Колбаски</a>
      <h2>Раскаленная сковородка</h2><article>
      <b>Скоблянка с рваной свининой</b><span>400 г</span><div>795 Р</div>
      <b>Картофель с грибами</b><span>320 г</span><div>545 Р</div>
      </article>
      <h2>Гриль/ пасты</h2><article>
      <b>новинка</b><h3>Стейк Стриплойн со свежим салатом</h3>
      <small>305гр.</small><strong>1495 Р</strong>
      <b>Паста Карбонара</b><small>280 г</small><div>595 Р</div>
      </article><h2>Колбаски</h2>
      <b>Ассорти колбасок</b><small>1000 гр.</small><div>3195 Р</div>
      <h2>Напитки</h2><b>Лимонад</b><small>1000 мл</small><div>595 Р</div>
    </body></html>"""
    rows, warnings = parse_easypub(html, config())
    assert [(x.name, x.price) for x in rows] == [
        ("Скоблянка с рваной свининой", 795),
        ("Картофель с грибами", 545),
        ("Стейк Стриплойн со свежим салатом", 1495),
        ("Паста Карбонара", 595),
        ("Ассорти колбасок", 3195),
    ]
    assert all("доставки" in x.note for x in rows)
    assert not warnings


def test_easy_pub_never_relabels_delivery_as_venue():
    with pytest.raises(ValueError, match="доставки"):
        parse_easypub("<h2>Гриль/ пасты</h2>", dict(kind="food", price_channel="venue"))
    with pytest.raises(ValueError, match="доставки"):
        parse_easypub("<h2>Гриль/ пасты</h2>", dict(kind="beer", price_channel="delivery"))


def test_easy_pub_changed_catalogue_fails_closed():
    with pytest.raises(ValueError, match="основные разделы"):
        parse_easypub("<h2>Напитки</h2><p>Лимонад</p><p>595 Р</p>", config())


def test_easy_pub_price_channel_in_storage(tmp_path):
    from monitor import storage
    p = dict(id="easy", name="Easy", district="САО", area="Хорошёвский",
             address="Москва", sources=[dict(id="easy_food", kind="food",
             url="https://easypub.ru/menu/goryachie-blyuda", price_channel="delivery")])
    db=tmp_path/"data.sqlite"
    storage.sync_sources([p], db)
    with storage.connect(db) as c:
        channel=c.execute("SELECT price_channel FROM sources WHERE id='easy_food'").fetchone()[0]
    assert channel=="delivery"
    storage.sync_sources([p], db)
    with storage.connect(db) as c:
        assert c.execute("SELECT count(*) FROM sources WHERE price_channel='delivery'").fetchone()[0]==1
