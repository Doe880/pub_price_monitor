import pytest
from monitor.iggy import parse_iggy
from monitor.parsers import parse


def test_iggy_prices_portions_cider_exclusion_and_duplicate_conflicts():
    html = """<html><body>
    <h2>Разливное пиво</h2>
    <div>Dacha Weiss</div><div>0.5l | 470₽</div>
    <div>Green Killer IPA</div><div>0.5l | 590₽ 0.25l | 330₽</div>
    <div>Magners Cider</div><div>0.5l | 590₽</div>
    <div>Friday Avenue APA</div><div>0.5l | 470₽</div>
    <div>Friday Avenue APA</div><div>0.5l | 590₽</div>
    <h2>Бутылочное пиво</h2>
    <div>Guiness</div><div>0.44l | 690₽</div>
    <h2>Пиво Б/А</h2>
    <div>Estrella Б/А</div><div>0.33l | 390₽</div>
    <h2>Вино</h2><div>Merlot</div><div>0.125l | 490₽</div>
    </body></html>"""
    config = {"parser":"iggy","kind":"beer","min_items":4}
    rows, notes = parse(html, config, None)
    assert len(rows) == 5
    assert sorted((x.name, x.volume_ml, x.price) for x in rows) == [
        ("Dacha Weiss",500,470),
        ("Estrella Б/А",330,390),
        ("Green Killer IPA",250,330),
        ("Green Killer IPA",500,590),
        ("Guiness",440,690),
    ]
    assert any(x.alcohol_free for x in rows)
    assert not any("Cider" in x.name or "Friday Avenue" in x.name or "Merlot" in x.name for x in rows)
    assert len(notes) == 1 and "Friday Avenue" in notes[0]


def test_iggy_fails_closed_on_changed_menu():
    with pytest.raises(ValueError, match="не найдены основные"):
        parse_iggy("<html><body><h2>Вино</h2><div>Red</div><div>0.5l | 500₽</div></body></html>",
                   {"kind":"beer","min_items":1})


def test_iggy_does_not_publish_hot_food_from_snacks():
    with pytest.raises(ValueError, match="горячих блюд"):
        parse_iggy("<html><body>Закуски</body></html>", {"kind":"food"})
