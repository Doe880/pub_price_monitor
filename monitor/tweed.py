"""Text food menu from Tweed & Stout's official pub page."""
import re
from bs4 import BeautifulSoup
from .models import clean, deduplicate
from .parsers import make_item

PRICE = re.compile(r'^(\d[\d ]{1,5})\s*руб\.?$', re.I)


def parse_tweed(html, source):
    if source['kind'] != 'food':
        raise ValueError('Tweed & Stout: проверяемой пивной карты с ценами здесь нет')
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    headings = soup.select('h2,h3')
    items = []
    for i, element in enumerate(headings):
        raw = clean(element.get_text(' ', strip=True))
        price = PRICE.fullmatch(raw)
        if not price or i == 0:
            continue
        previous = headings[i-1]
        name = clean(previous.get_text(' ', strip=True))
        if PRICE.fullmatch(name) or not 3 <= len(name) <= 110:
            continue
        item = make_item(name,'Меню кухни','food',float(price[1].replace(' ','')),
                         evidence=f'{name} | {raw}')
        item.validate()
        items.append(item)
    if len(items) < source.get('min_items', 1):
        raise ValueError('Tweed & Stout: недостаточно проверенных цен кухни')
    return deduplicate(items), []
