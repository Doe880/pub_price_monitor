"""Official Easy Pub delivery-menu extractor (NOT in-venue menu prices).

The network's public delivery catalogue is not evidence of prices at a specific
bar. Keep that channel explicit in source metadata and comparative charts.
"""
import re
from bs4 import BeautifulSoup
from .models import clean, deduplicate
from .parsers import make_item

SECTIONS = {"Раскаленная сковородка", "Гриль/ пасты", "Колбаски"}
STOP = {"Салаты", "Супы", "Закуски", "Римская пицца",
        "Бургеры и сэндвичи", "Японское меню", "Гарниры",
        "Десерты", "Соусы", "Напитки", "Бронирование"}
BADGES = {"хит", "новинка", "новинки", "популярное", "в корзину", "подробнее"}
PORTION = re.compile(r"^\d+(?:\s*/\s*\d+)*(?:\s*(?:г|гр|грамм)(?:\.)?)?$", re.I)
PRICE = re.compile(r"^(\d[\d\s]{1,5})\s*[₽Рр]\.?\s*$")


def parse_easypub(html, source):
    if source["kind"] != "food" or source.get("price_channel") != "delivery":
        raise ValueError("Easy Pub: доступен только отдельный прайс доставки горячих блюд")
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "template"]):
        node.decompose()
    tokens = [clean(s) for s in soup.stripped_strings if clean(s)]
    # The page contains navigation labels before product cards. Prices only
    # qualify when an explicit portion precedes them in a known menu section.
    section = None
    pending_name = None
    pending_portion = None
    seen_sections = set()
    rows = []
    for token in tokens:
        if token in SECTIONS:
            section, pending_name, pending_portion = token, None, None
            continue
        if token in STOP:
            section, pending_name, pending_portion = None, None, None
            continue
        if section is None:
            continue
        if token.casefold() in BADGES:
            continue
        match = PRICE.fullmatch(token)
        if match:
            if pending_name and pending_portion:
                price = float(match[1].replace(" ", ""))
                evidence = f"Доставка | {section} | {pending_name} | {pending_portion} | {token}"
                grams = [float(n) for n in re.findall(r"\d+", pending_portion)]
                item = make_item(
                    pending_name, section, "food", price, pending_portion,
                    weight=sum(grams) if grams else None,
                    evidence=evidence)
                item.note = "Цена доставки сети Easy Pub; цена в зале Ходынки не подтверждена"
                item.validate()
                rows.append(item)
                seen_sections.add(section)
            pending_name = pending_portion = None
            continue
        if PORTION.fullmatch(token) and pending_name:
            pending_portion = token
            continue
        if pending_portion:
            pending_name = pending_portion = None
        if 4 <= len(token) <= 140 and not token.isdigit():
            pending_name = token
    if not {"Раскаленная сковородка", "Гриль/ пасты"} <= seen_sections:
        raise ValueError("Easy Pub: не обнаружены основные разделы с ценами доставки")
    rows = deduplicate(rows)
    if len(rows) < source.get("min_items", 1):
        raise ValueError("Easy Pub: слишком мало цен в официальном меню")
    return rows, []
