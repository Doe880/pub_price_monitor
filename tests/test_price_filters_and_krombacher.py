import pytest
from monitor.krombacher import parse_krombacher


def test_krombacher_food_keeps_hot_dishes_without_beer_or_sides():
    html = """<html><body><h2>Разливное пиво и сидр. Коллекция пива Krombacher</h2>
    <h5>Кромбахер Пилс ₽230</h5><p>300 | 500 | 1000</p>
    <h2>Салаты</h2><h5>Салат ₽480</h5>
    <h2>Стейки гриль</h2><h5>Денвер стейк, 300г ₽1860</h5>
    <h2>Горячее</h2><h5>Стейк из лосося ₽1240</h5>
    <h5>Медальоны ₽680</h5>
    </body></html>"""
    rows, notes = parse_krombacher(html, {"kind": "food", "min_items": 3})
    assert [(r.name, r.price) for r in rows] == [
        ("Денвер стейк, 300г", 1860),
        ("Стейк из лосося", 1240),
        ("Медальоны", 680),
    ]
    assert rows[0].weight_g == 300
    assert not notes


def test_krombacher_rejects_beer_without_unambiguous_volume_prices():
    with pytest.raises(ValueError, match="не сопоставлены"):
        parse_krombacher("<h2>Пиво</h2>", {"kind": "beer"})


def test_krombacher_rejects_incomplete_menu():
    with pytest.raises(ValueError, match="основные разделы"):
        parse_krombacher("<h2>Горячее</h2><h5>Стейк ₽1230</h5>", {"kind": "food"})


def test_dashboard_has_comparison_filters_and_line_plot():
    from pathlib import Path
    code = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "key='price_pubs'" in code
    assert "key='price_names'" in code
    assert "key='price_portions'" in code
    assert "key='price_chart_type'" in code
    assert "px.line(plot_data" in code
