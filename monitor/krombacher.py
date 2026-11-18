"""Conservative parsing of Krombacher's official hot food menu.

Supports WordPress menus where headings and prices may be separate text nodes.
Never treats a single draft-beer starting price as per-volume pricing.
"""
import re
from bs4 import BeautifulSoup
from .models import clean, normalized, deduplicate
from .parsers import make_item

FOOD_SECTIONS = {"Немецкая классика", "Пивная Азия", "Крылья", "Мидии",
                 "Стейки гриль", "Гриль", "Горячее"}
OTHER_SECTIONS = {"Разливное пиво и сидр. Коллекция пива Krombacher",
                  "Пиво", "Сидр", "Салаты", "Гарниры", "Супы", "Хлеб",
                  "К пиву и вину", "Пивная Сибирь", "Закуски", "Десерты",
                  "Коктейли", "Напитки", "Бутылочное пиво"}
AMOUNT = re.compile(r"^(.*?)\s*₽\s*(\d[\d\s]{1,5})$")
SIMPLE_PRICE = re.compile(r"^₽\s*(\d[\d\s]{1,5})$")
NAME = re.compile(r"^[^₽]{3,120}$")


def parse_krombacher(html, source):
    if source["kind"] != "food":
        raise ValueError("Krombacher: объёмы и цены пива не сопоставлены")
    soup = BeautifulSoup(html, "html.parser")
    for n in soup(["script", "style", "noscript"]):
        n.decompose()
    section, pending = "", ""
    seen = set()
    items = []
    for original in soup.stripped_strings:
        token = clean(original)
        if not token:
            continue
        # Section titles are matched exactly, not inferred from surrounding descriptions.
        if token in FOOD_SECTIONS:
            section, pending = token, ""
            continue
        if token in OTHER_SECTIONS:
            section, pending = "", ""
            continue
        if not section:
            continue
        m = AMOUNT.fullmatch(token)
        if m:
            name, price_text = clean(m[1]), m[2]
        else:
            m = SIMPLE_PRICE.fullmatch(token)
            if m:
                name, price_text = pending, m[1]
            else:
                if NAME.fullmatch(token) and not re.fullmatch(r"\d+(?:\s*\|\s*\d+)*", token):
                    pending = token
                continue
        pending = ""
        if not name or "дегустац" in normalized(name):
            continue
        price = float(price_text.replace(" ", ""))
        weight_match = re.search(r"(\d+)\s*г\b", name, re.I)
        portion = weight_match.group(0) if weight_match else "не указан"
        item = make_item(name, section, "food", price, portion,
                         weight=float(weight_match[1]) if weight_match else None,
                         evidence=f"{section} | {name} | ₽{price_text}")
        item.validate()
        items.append(item)
        seen.add(section)
    if not {"Стейки гриль", "Горячее"} <= seen:
        raise ValueError("Krombacher: не найдены основные разделы горячих блюд")
    if len(items) < source.get("min_items", 1):
        raise ValueError("Krombacher: недостаточно проверяемых горячих блюд")
    return deduplicate(items), []
