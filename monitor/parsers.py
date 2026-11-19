"""Site-specific parsers. Fail explicitly if a menu layout becomes ambiguous."""
import re
from bs4 import BeautifulSoup
from .models import Item, clean, normalized, volume, not_beer, deduplicate

FOOD = {'горячие блюда', 'горячее', 'стейк меню', 'бургеры', 'бургеры и сэндвичи',
        'гриль', 'хоспер', 'сэндвичи', 'шашлык', 'стейки',
        'бургеры, блюда из мяса или птицы, ризотто', 'рыба и морепродукты',
        'римская пицца', 'паста и лапша'}


def txt(html):
    return clean(BeautifulSoup(str(html), 'html.parser').get_text(' ', strip=True)) if '<' in str(html) else clean(html)


def money(value):
    return float(clean(value).replace(' ', '').replace(',', '.'))


def make_item(name, section, kind, price, portion='не указан', ml=None, weight=None,
              serving='', evidence='', note=''):
    basis = '100 г' if re.search(r'за\s*100\s*г', name + ' ' + portion, re.I) else 'порция'
    return Item(clean(name), 'Пиво' if kind == 'beer' else 'Горячие блюда', section,
                float(price), portion, ml, weight, basis, serving,
                bool(re.search(r'безалког|alcohol.?free|\bб/а\b|\bn/a\b', name + ' ' + section, re.I)),
                evidence, note)


def parse_dubliner(html, source):
    soup = BeautifulSoup(html, 'html.parser')
    section = ''
    serving = ''
    free = False
    items, warnings = [], []
    seen_sections = set()
    for record in soup.select('.r'):
        wrappers = record.select('.t792__wrapper')
        if not wrappers:
            label = clean(record.get_text(' ', strip=True))
            low = normalized(label)
            if label and len(label) < 80:
                section = label
                if low == 'бутылочное пиво':
                    serving, free = 'Бутылочное/баночное', False
                elif low == 'разливное пиво':
                    serving, free = 'Разливное', False
                elif low == 'безалкогольное':
                    free = True
                elif low == 'быстрые закуски':
                    serving = ''
            continue
        if source['kind'] == 'food' and normalized(section) not in FOOD:
            continue
        if source['kind'] == 'beer' and not serving:
            continue
        seen_sections.add(normalized(section))
        for card in wrappers:
            title = card.select_one('.t792__title')
            price_el = card.select_one('.t792__price')
            if not title or not price_el:
                raise ValueError('Изменилась структура карточек Дублинца')
            for sup in title.select('sup'):
                sup.decompose()
            name = clean(title.get_text(' ', strip=True))
            uptitle = card.select_one('.t792__uptitle')
            if uptitle and clean(uptitle.get_text(' ', strip=True)):
                name = clean(uptitle.get_text(' ', strip=True)) + ', ' + name
            price_text = clean(price_el.get_text(' ', strip=True))
            ev = name + ' | ' + price_text
            if source['kind'] == 'beer' and not_beer(name):
                continue
            price_parts = price_text.replace('₽', '').split('/')
            try:
                prices = [money(p) for p in price_parts]
            except ValueError:
                warnings.append('Цена не распознана: ' + ev)
                continue
            if source['kind'] == 'food':
                if len(prices) != 1:
                    warnings.append('Неоднозначная порция: ' + ev)
                    continue
                items.append(make_item(name, section, 'food', prices[0], evidence=ev))
                continue
            pair = re.search(r'(\d+)\s*/\s*(\d+)\s*мл', name)
            if pair:
                sizes = [float(pair[1]), float(pair[2])]
                base = clean(name[:pair.start()].rstrip(', '))
            else:
                # This specific page uses litres without a unit before '/ ABV'.
                single = re.search(r',\s*(0[,.]\d+)\s*/', name)
                sizes = [float(single[1].replace(',', '.')) * 1000] if single else []
                base = clean(name[:single.start()]) if single else name
            if len(sizes) != len(prices):
                warnings.append('Не удалось сопоставить объём и цену: ' + ev)
                continue
            for ml, price in zip(sizes, prices):
                item = make_item(base, 'Безалкогольное' if free else section, 'beer', price,
                                 f'{ml:g} мл', ml=ml, serving=serving, evidence=ev)
                item.alcohol_free = free
                items.append(item)
    if source['kind'] == 'food' and 'горячие блюда' not in seen_sections:
        raise ValueError('Не найден раздел горячих блюд')
    return deduplicate(items), warnings


def tilda_parts(html, required=None):
    soup = BeautifulSoup(html, 'html.parser')
    tab_labels = {b.get('aria-controls'):clean(b.get_text(' ', strip=True))
                  for b in soup.select('button[aria-controls]')}
    result = {}
    for block in soup.select('.r'):
        match = re.search(r"storepart:\s*['\"](\d+)['\"]", str(block))
        if not match:
            continue
        label = tab_labels.get(block.get('id'))
        if not label:
            prev = block.find_previous(class_='r')
            label = clean(prev.get_text(' ', strip=True)) if prev else ''
        if not label or (required is not None and label not in required):
            continue
        if label in result and result[label] != match[1]:
            raise ValueError('Повтор раздела Tilda: ' + label)
        result[label] = match[1]
    return result


def parse_tilda_product(p, section, kind):
    name = txt(p.get('title', ''))
    desc = txt(p.get('descr', ''))
    ev = name + ' | ' + desc
    if kind == 'beer' and not_beer(name + ' ' + desc):
        return [], []
    serving = 'Разливное' if 'разливное' in section.lower() else 'Бутылочное/баночное'
    if kind == 'food':
        serving = ''
    out, warnings = [], []
    editions = p.get('editions') or []
    valued = [e for e in editions if e.get('price') not in {None, ''}]
    if valued:
        if len(valued) != len(editions):
            warnings.append('Часть вариантов без цены: ' + name)
        for edition in valued:
            options = {k: str(v) for k,v in edition.items()
                       if k not in {'uid','externalid','sku','price','priceold','quantity','img'} and v}
            portion = '; '.join(f'{k}: {v}' for k,v in sorted(options.items())) or 'не указан'
            ml = volume(portion) or volume(name) or volume(desc)
            weight = None
            note = ''
            if kind == 'beer' and ml is not None and not 50 <= ml <= 5000:
                portion = f'{ml:g} мл (как на сайте)'
                note = 'Некорректный объём в источнике. Цена сохранена; пересчёт на 0,5 л отключён.'
                warnings.append('Объём требует проверки: ' + name)
                ml = None
            if kind == 'beer':
                if ml is not None:
                    # Keep non-volume options to preserve distinct variants.
                    other = '; '.join(f'{k}: {v}' for k,v in options.items()
                                      if 'объ' not in k.lower() and 'volume' not in k.lower())
                    portion = f'{ml:g} мл' + ('; ' + other if other else '')
                else:
                    warnings.append('Объём не указан: ' + name)
            elif portion == 'не указан':
                m = re.search(r'(\d+(?:/\d+)*)\s*(?:гр|г)\b', name + ' ' + desc)
                if m:
                    portion = m[1] + ' г'
                    weight = sum(float(x) for x in m[1].split('/'))
            out.append(make_item(name, section, kind, money(edition['price']), portion,
                                 ml=ml if kind == 'beer' else None, weight=weight,
                                 serving=serving, evidence=ev + ' | ' + str(options) + ' | цена ' + str(edition['price']),note=note))
        return out, warnings
    # Delirium publishes prices in the official product description instead of price.
    if kind == 'beer':
        pairs = list(re.finditer(r'(\d+(?:[.,]\d+)?)\s*(мл|л|ml|l)\s*[-–—:|]?\s*(\d[\d ]*)\s*(?:р\b|руб|₽)', desc, re.I))
        for match in pairs:
            ml = float(match[1].replace(',', '.')) * (1000 if match[2].lower() in {'л','l'} else 1)
            note = ''
            if not 50 <= ml <= 5000:
                note = 'Некорректный объём в источнике: ' + match[1] + ' ' + match[2] + '. Не пересчитывается на 0,5 л.'
                warnings.append('Объём требует проверки: ' + name + ' — ' + note)
            out.append(make_item(name, section, kind, money(match[3]), f'{ml:g} мл (как на сайте)' if note else f'{ml:g} мл',
                                 ml=None if note else ml, serving=serving, evidence=ev, note=note))
    else:
        m = re.search(r'(\d+(?:/\d+)*)\s*(?:гр|г)\b\s*[-–—:|]?\s*(\d[\d ]*)\s*(?:р\b|руб|₽)', desc, re.I)
        if m:
            out.append(make_item(name, section, kind, money(m[2]), m[1]+' г',
                                 weight=sum(float(x) for x in m[1].split('/')), evidence=ev))
    if not out:
        warnings.append('Нет однозначной цены: ' + ev)
    return out, warnings


def parse_tilda(html, source, fetcher):
    parts = source.get('part_ids') or tilda_parts(html, set(source['sections']))
    if source.get('part_ids'):
        actual = set(re.findall(r"storepart:\s*['\"](\d+)['\"]", html))
        if not set(parts.values()) <= actual:
            raise ValueError('Изменились разделы каталога; нужна проверка привязки')
    missing = set(source['sections']) - set(parts)
    if missing:
        raise ValueError('Не найдены разделы: ' + ', '.join(sorted(missing)))
    items, warnings = [], []
    for section in source['sections']:
        uid = parts[section]
        # Full-page check. Fail rather than silently drop later catalogue pages.
        url = 'https://store.tildaapi.com/api/getproductslist/?storepartuid=' + uid + '&size=500'
        payload = fetcher.get(url, kind='json')
        if str(payload.get('partuid')) != uid or not isinstance(payload.get('products'), list):
            raise ValueError('Неверный ответ каталога ' + section)
        products = payload['products']
        if int(payload.get('total', -1)) != len(products):
            raise ValueError('Каталог возвращён не полностью: ' + section + '. Нужна настройка пагинации.')
        for p in products:
            rows, notes = parse_tilda_product(p, section, source['kind'])
            items.extend(rows)
            warnings.extend(notes)
    return deduplicate(items), warnings


def parse_beeftime(html, source):
    soup = BeautifulSoup(html, 'html.parser')
    section = ''
    items, warnings = [], []
    found = set()
    for block in soup.select('.wb_text_element'):
        text = clean(block.get_text(' ', strip=True))
        if not text:
            continue
        heading = block.find('h5')
        if heading:
            section = clean(heading.get_text(' ', strip=True))
            continue
        is_beer = section in {'Пиво разливное', 'Пиво бутылочное'}
        if source['kind'] == 'beer' and not is_beer:
            continue
        if source['kind'] == 'food' and normalized(section) not in FOOD:
            continue
        if '₽' not in text:
            continue
        found.add(section)
        # ₽ terminates a price, unlike a <br> that can wrap a long item title.
        segments = re.findall(r'([^₽]+₽)', text)
        for segment in segments:
            raw = clean(segment).lstrip('* ')
            m = re.match(r'(?P<portion>за\s*100\s*г\.?|\d+(?:/\d+)*)\s+(?P<name>.+?)\s*[-–—]\s*(?P<prices>[\d\s/*]+)\s*₽$', raw, re.I)
            if not m:
                warnings.append('Не распознана строка: ' + raw)
                continue
            name = clean(m['name'])
            if is_beer and not_beer(name):
                continue
            prices = [money(x.replace('*','')) for x in m['prices'].split('/')]
            portion = clean(m['portion'])
            if is_beer:
                sizes = [float(x) for x in portion.split('/')]
                if len(sizes) != len(prices):
                    warnings.append('Объём не сопоставлен с ценой: ' + raw)
                    continue
                for ml,price in zip(sizes,prices):
                    serving = 'Разливное' if section == 'Пиво разливное' else 'Бутылочное/баночное'
                    items.append(make_item(name, section, 'beer', price, f'{ml:g} мл',
                                           ml=ml, serving=serving, evidence=raw))
            elif len(prices) == 1:
                weight = None if 'за' in portion else sum(float(x) for x in portion.split('/'))
                items.append(make_item(name, section, 'food', prices[0],
                                       portion if 'за' in portion else portion+' г',
                                       weight=weight, evidence=raw))
            else:
                warnings.append('Несколько цен для блюда: ' + raw)
    if source['kind'] == 'beer' and found != {'Пиво разливное', 'Пиво бутылочное'}:
        raise ValueError('Не найдены оба пивных раздела BeefTime')
    if source['kind'] == 'food' and not {'Стейки', 'Шашлык'}.issubset(found):
        raise ValueError('Не найдены основные разделы BeefTime')
    return deduplicate(items), warnings


def parse(html, source, fetcher):
    if source['parser'] == 'easypub':
        from .easypub import parse_easypub
        return parse_easypub(html, source)
    if source['parser'] == 'document':
        from .document_menus import parse_document
        return parse_document(html, source)
    if source['parser'] == 'structured_html':
        from .structured_menus import parse_structured_html
        return parse_structured_html(html, source)
    if source['parser'] == 'tweed':
        from .tweed import parse_tweed
        return parse_tweed(html, source)
    if source['parser'] == 'chelsea':
        from .chelsea import parse_chelsea
        return parse_chelsea(html, source)
    if source['parser'] == 'krombacher':
        from .krombacher import parse_krombacher
        return parse_krombacher(html, source)
    if source['parser'] == 'iggy':
        from .iggy import parse_iggy
        return parse_iggy(html, source)
    if source['parser'] == 'post_pdf':
        from .pdf_menus import parse_pdf
        return parse_pdf(html, source)
    if source['parser'] == 'dom':
        from .menus import parse_dom
        return parse_dom(html, source)
    if source['parser'] == 'pub22':
        from .pub22 import parse_pub22
        return parse_pub22(html, source)
    if source['parser'] == 'tilda':
        return parse_tilda(html, source, fetcher)
    if source['parser'] == 'dubliner':
        return parse_dubliner(html, source)
    if source['parser'] == 'beeftime':
        return parse_beeftime(html, source)
    raise ValueError('Неизвестный адаптер: ' + source['parser'])
