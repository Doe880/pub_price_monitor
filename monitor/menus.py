"""Explicit DOM recipes for public official menus; no inferred prices."""
import re
from bs4 import BeautifulSoup
from .models import clean, volume, not_beer, deduplicate
from .parsers import make_item, money


def text(node):
    return clean(node.get_text(' ', strip=True)) if node else ''


def number(raw):
    match = re.fullmatch(r'\s*(\d[\d ]*(?:[.,]\d+)?)\s*(?:₽|руб\.?|р\.?)?\s*', raw)
    if not match:
        raise ValueError('Неоднозначная цена: ' + raw)
    return money(match[1])


def row(name, section, kind, price, portion='', serving='', evidence=''):
    ml = volume(portion) if kind == 'beer' else None
    weight = None
    if kind == 'food':
        m = re.search(r'(\d+(?:/\d+)*)\s*(?:гр|г)\b', portion)
        weight = sum(map(float, m[1].split('/'))) if m else None
    return make_item(name, section, kind, price, portion or 'не указан', ml=ml,
                     weight=weight, serving=serving, evidence=evidence)


def parse_dom(html, source):
    soup = BeautifulSoup(html, 'html.parser')
    mode, kind = source['recipe'], source['kind']
    sections = set(source.get('sections', []))
    items, notes, seen = [], [], set()
    candidates = []
    if mode == '4brewers_food':
        for card in soup.select('.dish'):
            section = text(card.find_previous(class_='section'))
            if section in sections:
                candidates.append((section, text(card.select_one('.card-title')), card.get('price',''),
                                   text(card.select_one('.card-footer .text-muted')), ''))
    elif mode in {'collins', 'oneill', 'zolberg'}:
        for block in soup.select('.r'):
            if mode == 'collins':
                cards = block.select('.t772__textwrapper')
                section = text(block.find_previous(class_='r'))
                for card in cards:
                    if section in sections:
                        name = text(card.select_one('.t-card__uptitle'))
                        if name.lower().startswith('дополнительные'): continue
                        candidates.append((section,name,text(card.select_one('.t-card__descr')),
                                           text(card.select_one('.t-card__title')), ''))
            elif mode == 'oneill':
                section = text(block.select_one('.t-section__title'))
                for card in block.select('.t812__pricelist-item'):
                    if section in sections:
                        candidates.append((section,text(card.select_one('.t812__pricelist-item__title')),
                                           text(card.select_one('.t812__pricelist-item__price')),
                                           text(card.select_one('.t812__pricelist-item__descr')), ''))
            else:
                section = text(block.select_one('.t-section__title'))
                for card in block.select('.t1196__content-inner'):
                    if section in sections:
                        candidates.append((section,text(card.select_one('.t-card__title')),
                                           text(card.select_one('.t-btnflex__text')),
                                           text(card.select_one('.t-card__title')), 'Бутылочное/баночное' if 'банках' in section.lower() else 'Разливное'))
    elif mode == 'purkin':
        for card in soup.select('.food-info' if kind == 'food' else '.drink-item'):
            section = text(card.find_previous('h2', class_='category-title'))
            if section not in sections: continue
            name = text(card.select_one('.food-name,.drink-name'))
            if kind == 'beer' and not_beer(name+' '+text(card.select_one('.drink-details'))):continue
            if kind == 'food':
                candidates.append((section,name,text(card.select_one('.food-price')),text(card.select_one('.food-portion')), ''))
            else:
                for price in card.select('.price-item'):
                    raw = text(price)
                    m = re.fullmatch(r'(\d+(?:[,.]\d+)?)\s*(л|мл)\.?\s*/\s*(\d+)₽',raw)
                    if not m:raise ValueError('Изменился формат цены Purkin: '+raw)
                    candidates.append((section,name,m[3],m[1]+' '+m[2],'Разливное'))
    elif mode == 'brasserie033':
        section = text(soup.find('h1'))
        if section not in sections:raise ValueError('Изменился раздел меню 0.33: '+section)
        for card in soup.select('.item-card'):
            name = text(card.select_one('.item-card__title'))
            if kind == 'beer' and not_beer(name+' '+text(card.select_one('.beer-meta'))):continue
            buttons = card.select('[data-wishlist-base-price]')
            if not buttons:
                notes.append('Позиция без однозначной цены: '+name)
            for button in buttons:
                portion = button.get('data-wishlist-volume-label','') if kind == 'beer' else button.get('data-wishlist-meta','')
                serving = 'Разливное' if button.get('data-wishlist-serving-label') == 'разлив.' else 'Бутылочное/баночное'
                candidates.append((section,name,button['data-wishlist-base-price'],portion,serving if kind=='beer' else ''))
    elif mode == 'bobby_beer':
        for card in soup.select('.food-drink h4'):
            price = card.find('strong')
            if not price:continue
            raw = text(price); price.extract(); name = text(card)
            if not_beer(name):continue
            following = card.find_next_sibling()
            portion = text(following.find('em')) if following else ''
            candidates.append(('Пиво',name,raw,portion,''))
    else:
        raise ValueError('Неизвестный рецепт меню: '+mode)
    for section,name,raw,portion,serving in candidates:
        if not name:raise ValueError('Пустое название блюда')
        seen.add(section)
        ev = ' | '.join((section,name,raw,portion))
        if kind == 'beer':
            if not_beer(name):continue
            prices = [number(x) for x in raw.split('/')]
            # Explicit units, including "300/500 мл" and "0,3 л / 0,5 л".
            pair = re.search(r'(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*(мл|л)',portion)
            sizes = [x+' '+pair[3] for x in [pair[1],pair[2]]] if pair else re.findall(r'\d+(?:[.,]\d+)?\s*(?:мл|л)\b',portion)
            if len(prices) != len(sizes):
                if len(prices) == 1:
                    items.append(row(name,section,kind,prices[0],portion,serving,ev))
                    notes.append('Объём не указан: '+name)
                    continue
                raise ValueError('Не совпали число цен и объёмов: '+ev)
            for price,size in zip(prices,sizes):items.append(row(name,section,kind,price,size,serving,ev))
        else:
            # Keep portion only, not ingredient descriptions.
            m = re.search(r'\d+(?:/\d+)*\s*(?:гр|г)\b',portion)
            items.append(row(name,section,kind,number(raw),m[0] if m else '',serving,ev))
    missing = sections - seen
    if missing:raise ValueError('Не найдены разделы: '+', '.join(sorted(missing)))
    if not items:raise ValueError('Цены в меню не найдены')
    return deduplicate(items), notes
