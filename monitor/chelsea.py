"""Official Chelsea GastroPub HTML menu parser with strict section matching."""
import re
from bs4 import BeautifulSoup
from .models import clean, normalized, volume, not_beer, deduplicate
from .parsers import make_item

FOOD = {'Блюда на огне', 'Горячие блюда', 'БУРГЕР'}
BEER = {'Разливное пиво', 'Бутылочное пиво'}
RUB = re.compile(r'^\s*(\d[\d ]{1,5})\s*₽\s*$')
BASIS100 = re.compile(r'(?:цена\s+указана\s+за|за)\s*100\s*гр?\b', re.I)


def parse_chelsea(html, source):
    soup = BeautifulSoup(html, 'html.parser')
    kind = source['kind']
    allowed = FOOD if kind == 'food' else BEER
    items, warnings, found = [], [], set()
    for card in soup.select('li'):
        title = card.select_one('.menuPage-menuContent__title')
        price_nodes = card.select('.menuPage-menuContent__priceContainer')
        if not title or not price_nodes:
            continue
        section_node = card.find_previous('h2')
        section = clean(section_node.get_text(' ', strip=True)) if section_node else ''
        if section not in allowed:
            continue
        name = clean(title.get_text(' ', strip=True))
        descr = card.select_one('.menuPage-menuContent__subtitle')
        description = clean(descr.get_text(' ', strip=True)) if descr else ''
        visible = [clean(x.get_text(' ', strip=True)) for x in price_nodes]
        priced = [RUB.fullmatch(x) for x in visible]
        prices = [float(m[1].replace(' ', '')) for m in priced if m]
        if len(prices) != 1:
            warnings.append('Нельзя сопоставить цену: ' + name)
            continue
        if kind == 'beer' and not_beer(name + ' ' + description):
            continue
        portion_match = re.search(r'(?:об[ъь]е?м\s*:\s*)?(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l)\b', name+' '+description, re.I)
        portion = (portion_match[1]+' '+portion_match[2]) if portion_match else 'не указан'
        serving = ('Разливное' if section=='Разливное пиво' else 'Бутылочное/баночное') if kind=='beer' else ''
        if kind=='food' and BASIS100.search(description):
            portion='за 100 г'
        if kind=='beer' and portion_match is None:
            warnings.append('Объём не указан: '+name)
        item=make_item(name,section,kind,prices[0],portion,
                       ml=volume(portion) if kind=='beer' else None,
                       serving=serving,evidence=f'{section} | {name} | {description} | {int(prices[0])} ₽')
        item.validate()
        items.append(item)
        found.add(section)
    required={'Блюда на огне','Горячие блюда'} if kind=='food' else BEER
    if not required <= found:
        raise ValueError('Chelsea: не найдены разделы меню: '+', '.join(sorted(required-found)))
    if len(items) < source.get('min_items',1):
        raise ValueError('Chelsea: извлечено слишком мало цен')
    return deduplicate(items), warnings
