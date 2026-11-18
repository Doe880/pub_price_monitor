"""Parser for the public, text-based Iggy Pub beer menu.

Only explicitly priced beer within known beer sections is accepted.
Conflicting duplicate prices are excluded, not guessed.
"""
import re
from bs4 import BeautifulSoup
from .models import clean, normalized, not_beer, deduplicate
from .parsers import make_item

SECTIONS = {
    "разливное пиво": ("Разливное пиво", "Разливное"),
    "бутылочное пиво": ("Бутылочное пиво", "Бутылочное/баночное"),
    "пиво б/а": ("Пиво Б/А", "Бутылочное/баночное"),
    "пиво б.а.": ("Пиво Б/А", "Бутылочное/баночное"),
    "пиво б.а": ("Пиво Б/А", "Бутылочное/баночное"),
}
STOP = {"вино", "коктейли", "крепкий алкоголь", "закуски", "контакты", "безалкогольные напитки"}
PRICE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|мл|l|л)\s*[|/]\s*(\d[\d\s]{1,5})\s*₽", re.I)


def parse_iggy(html, source):
    if source.get("kind") != "beer":
        raise ValueError("Iggy Pub: раздел горячих блюд не опубликован")
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    tokens = [clean(s) for s in soup.stripped_strings if clean(s)]
    candidates = []
    section, serving, name = "", "", ""
    found = set()
    for token in tokens:
        key = normalized(token).replace("\\", "/")
        if key in SECTIONS:
            section, serving = SECTIONS[key]
            name = ""
            continue
        if key in STOP:
            section, name = "", ""
            continue
        if not section:
            continue
        matches = list(PRICE.finditer(token))
        if not matches:
            if "₽" in token:
                # Do not reuse an old name after an unrecognized price.
                name = ""
            elif len(token) < 160 and "|" not in token:
                name = token
            continue
        prefix = clean(token[:matches[0].start()])
        if prefix:
            name = prefix
        if not name or not_beer(name):
            name = ""
            continue
        for match in matches:
            amount = float(match[1].replace(",", "."))
            ml = amount * (1000 if match[2].lower() in {"l", "л"} else 1)
            price = float(match[3].replace(" ", ""))
            evidence = f"{name} | {match.group(0)}"
            item = make_item(name, section, "beer", price, f"{ml:g} мл",
                             ml=ml, serving=serving, evidence=evidence)
            item.alcohol_free = section == "Пиво Б/А"
            item.validate()
            candidates.append(item)
            found.add(section)
        name = ""
    if "Разливное пиво" not in found or "Бутылочное пиво" not in found:
        raise ValueError("Iggy Pub: не найдены основные пивные разделы с ценами")
    by_key = {}
    conflicts = set()
    for item in candidates:
        if item.key in by_key and by_key[item.key].price != item.price:
            conflicts.add(item.key)
        by_key[item.key] = item
    warnings = []
    if conflicts:
        warnings.append("Конфликт цен одинаковой позиции: " +
                        ", ".join(sorted({by_key[k].name for k in conflicts})))
    rows = deduplicate([item for key, item in by_key.items() if key not in conflicts])
    if len(rows) < source.get("min_items", 1):
        raise ValueError("Iggy Pub: недостаточно однозначных цен")
    return rows, warnings
