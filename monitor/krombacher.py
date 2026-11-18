"""Krombacher Beer Kitchen: conservative hot-dish parsing from official HTML.

The beer section displays one starting price for multiple volumes, and must not
be converted into per-volume prices without a verified price table.
"""
import re
from bs4 import BeautifulSoup
from .models import clean, deduplicate
from .parsers import make_item

FOOD_SECTIONS = {"Немецкая классика", "Пивная Азия", "Крылья", "Мидии",
                 "Стейки гриль", "Гриль", "Горячее"}
PRICE = re.compile(r"^(.*?)\s*₽\s*([\d\s]{2,6})\s*$")


def parse_krombacher(html, source):
    if source["kind"] != "food":
        raise ValueError("Krombacher: объёмы и цены пива не сопоставлены")
    soup = BeautifulSoup(html, "html.parser")
    for n in soup(["script", "style", "noscript"]):
        n.decompose()
    section = ""
    seen = set()
    items = []
    for node in soup.find_all(re.compile(r"^h[2-6]$")):
        label = clean(node.get_text(" ", strip=True))
        if node.name in {"h2", "h3"}:
            section = label
            continue
        if node.name not in {"h4", "h5", "h6"} or section not in FOOD_SECTIONS:
            continue
        match = PRICE.fullmatch(label)
        if not match:
            continue
        name = clean(match[1])
        if not name or "сет" in name.lower() and "дегустац" in name.lower():
            continue
        amount = float(match[2].replace(" ", ""))
        weight_match = re.search(r"(\d+)\s*г\b", name, re.I)
        portion = weight_match.group(0) if weight_match else "не указан"
        item = make_item(name, section, "food", amount, portion,
                         weight=float(weight_match[1]) if weight_match else None,
                         evidence=label)
        item.validate()
        items.append(item)
        seen.add(section)
    if not {"Стейки гриль", "Горячее"} <= seen:
        raise ValueError("Krombacher: не найдены основные разделы горячих блюд")
    if len(items) < source.get("min_items", 1):
        raise ValueError("Krombacher: недостаточно проверяемых горячих блюд")
    return deduplicate(items), []
