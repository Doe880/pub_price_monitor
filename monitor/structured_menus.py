"""Declarative CSS recipes for rendered or ordinary official HTML menus.

Site-specific selectors must be configured explicitly. Never scrape generic
page numbers, promotional banners or shopping basket prices.
"""
import re
from bs4 import BeautifulSoup
from .models import clean, volume, not_beer, deduplicate
from .parsers import make_item

PRICE = re.compile(r"^\s*(\d[\d ]{1,5})(?:[,.]00)?\s*(?:₽|руб\.?|р\.)\s*$", re.I)


def parse_structured_html(html, source):
    fields = source.get("selectors") or {}
    required = ("card", "name", "price", "section")
    if any(not fields.get(k) for k in required):
        raise ValueError("Нужны точные CSS-селекторы card/name/price/section")
    sections = source.get("sections")
    if not sections:
        raise ValueError("Нужно перечислить допустимые разделы меню")
    soup = BeautifulSoup(html, "html.parser")
    allowed = {clean(x) for x in sections}
    rows, notes, found = [], [], set()
    for card in soup.select(fields["card"]):
        name_node = card.select_one(fields["name"])
        price_node = card.select_one(fields["price"])
        section_node = card.select_one(fields["section"])
        if not name_node or not price_node or not section_node:
            continue
        section = clean(section_node.get_text(" ", strip=True))
        if section not in allowed:
            continue
        found.add(section)
        name = clean(name_node.get_text(" ", strip=True))
        price_text = clean(price_node.get_text(" ", strip=True))
        match = PRICE.fullmatch(price_text)
        if not match or not name:
            notes.append("Пропущена неоднозначная цена: " + name[:70])
            continue
        if source["kind"] == "beer" and not_beer(name):
            continue
        portion_node = card.select_one(fields["portion"]) if fields.get("portion") else None
        portion = clean(portion_node.get_text(" ", strip=True)) if portion_node else "не указан"
        ml = volume(portion) if source["kind"] == "beer" else None
        if source["kind"] == "beer" and ml is None:
            notes.append("Объём не указан: " + name)
        item = make_item(name, section, source["kind"],
                         float(match[1].replace(" ", "")), portion, ml=ml,
                         serving=source.get("serving_type", ""),
                         evidence=f"{section} | {name} | {price_text} | {portion}")
        item.validate()
        rows.append(item)
    if set(allowed) - found:
        raise ValueError("Не найдены ожидаемые разделы HTML-меню")
    if len(rows) < source.get("min_items", 1):
        raise ValueError("Слишком мало проверенных цен в HTML")
    return deduplicate(rows), notes
