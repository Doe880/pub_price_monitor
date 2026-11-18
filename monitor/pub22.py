"""Official 22pub.ru menu; never infer units missing from the source."""
import re
from bs4 import BeautifulSoup
from .models import clean, deduplicate, not_beer
from .parsers import make_item, money


def parse_pub22(html, source):
    soup = BeautifulSoup(html, 'html.parser')
    rows, warnings = [], []
    for section in source['sections']:
        links = [a for a in soup.select('a[data-bs-target]') if clean(a.text) == section]
        if not links or len({a['data-bs-target'] for a in links}) != 1:
            raise ValueError('Не найден однозначный раздел 2:2: '+section)
        target = links[0]['data-bs-target']
        if not re.fullmatch(r'#tab-\d+', target):
            raise ValueError('Изменилась навигация меню 2:2')
        blocks = soup.select(target)
        if len(blocks) != 1 or not blocks[0].select('.menu-item'):
            raise ValueError('Пустой или неоднозначный раздел 2:2: '+section)
        for card in blocks[0].select('.menu-item'):
            content = card.select_one('.menu-content')
            spans = content.find_all('span', recursive=False) if content else []
            if len(spans) != 2 or 'item-name' not in spans[0].get('class', []):
                raise ValueError('Изменилась структура строки 2:2')
            name, raw = (clean(s.get_text(' ', strip=True)) for s in spans)
            evidence = clean(card.get_text(' ', strip=True))
            if source['kind'] == 'beer' and (not_beer(evidence) or 'пивной сет' in name.casefold()):
                continue
            if not re.fullmatch(r'\d[\d ]*(?:/\d[\d ]*)*', raw):
                raise ValueError('Неоднозначная цена 2:2: '+evidence)
            prices = [money(p) for p in raw.split('/')]
            if source['kind'] == 'food':
                if len(prices) != 1:
                    raise ValueError('Несколько цен блюда 2:2: '+name)
                rows.append(make_item(name, section, 'food', prices[0], evidence=evidence))
                continue
            # The site prints 0,3/0,5 without litres/ml. Preserve both values and
            # pair their prices in order, but leave volume_ml unknown.
            match = re.search(r'(?<![\d.,])(0[,.]\d+(?:\s*/\s*0[,.]\d+)*)\s*$', name)
            if not match:
                raise ValueError('Не распознана порция пива 2:2: '+name)
            quantities = re.split(r'\s*/\s*', match[1])
            if len(quantities) != len(prices):
                raise ValueError('Число порций и цен не совпадает: '+evidence)
            base = name[:match.start()].rstrip(' ,')
            for quantity, price in zip(quantities, prices):
                rows.append(make_item(base, section, 'beer', price,
                    portion=quantity+' (единица не указана)',
                    serving='Разливное' if section == 'Разливное пиво' else 'Бутылочное/баночное',
                    evidence=evidence,
                    note='На сайте не указана единица объёма. Пересчёт на 0,5 л отключён.'))
            warnings.append('Объём не указан: '+name+' — сохранены исходные значения без единицы')
    return deduplicate(rows), warnings
