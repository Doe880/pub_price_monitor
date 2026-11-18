"""Validated text-PDF recipes. Image PDFs are never treated as empty menus."""
import re
from io import BytesIO
from pypdf import PdfReader
from .models import clean, not_beer, deduplicate
from .parsers import make_item


def parse_pdf(data, source):
    reader = PdfReader(BytesIO(data))
    if len(reader.pages) != 1: raise ValueError('Изменилось число страниц меню Post Pub')
    content = reader.pages[0].extract_text(extraction_mode='layout')
    if len(content.strip()) < 100: raise ValueError('PDF без извлекаемого текста; требуется проверка изображения')
    items, notes = [], []
    if source['kind'] == 'beer':
        if 'СИДР' not in content: raise ValueError('Не найдена пивная карта')
        lines = content.splitlines()
        for i,line in enumerate(lines):
            m = re.fullmatch(r'\s*(.+?)\s{3,}(\d{2,5})\s+q\s*',line)
            if not m:continue
            name, price = clean(m[1]), float(m[2])
            desc = clean(lines[i+1]) if i+1<len(lines) else ''
            if not_beer(name+' '+desc):continue
            # PDF has no explicit unit beside 0,33; do not infer litres.
            size = re.search(r'(?:БАНКА|БУТЫЛКА)\s+(0[,.]\d+)',desc)
            portion = size[1]+' (единица не указана)' if size else 'не указан'
            item=make_item(name,'Пиво','beer',price,portion,
                serving='Бутылочное/баночное' if size else '', evidence=clean(line)+' | '+desc)
            items.append(item);notes.append('Объём не указан: '+name)
    else:
        lines=content.splitlines()
        header=next((line for line in lines if 'ГОРЯЧЕЕ' in line and re.search('ЗА ?КУСКИ',line)),None)
        if not header:raise ValueError('Изменились колонки PDF')
        boundary=re.search('ЗА ?КУСКИ',header).start()-2
        if boundary < 90:raise ValueError('Неоднозначная ширина колонок PDF')
        current=None;section='';seen=set()
        def finish():
            if current is None:return
            if len(current['prices'])!=1:raise ValueError('Неоднозначная цена PDF: '+current['name'])
            items.append(make_item(current['name'],section,'food',current['prices'][0],current['portion'],
                evidence=' | '.join(current['lines']),note='На сайте указано, что меню обновляется; наличие уточняется в пабе.'))
        for full in lines:
            line=full[:boundary].rstrip(); compact=re.sub(r'\s+','',line)
            if compact in {'ГОРЯЧЕЕ','САЛАТЫ','БУРГЕРЫ','СОУСЫ'}:
                finish();current=None;section=compact;seen.add(section);continue
            if section not in {'ГОРЯЧЕЕ','БУРГЕРЫ'}:continue
            m=re.match(r'\s*(.+?)\s+(\d+(?:\s*\+\s*\d+)*)\s*г\.',line)
            if m:
                finish();current={'name':clean(m[1]),'portion':clean(m[2])+' г','prices':[],'lines':[]}
            if current:
                current['lines'].append(clean(line))
                price=re.search(r'(?:^|\s{3,})(\d{2,5})\s*$',line)
                if price:current['prices'].append(float(price[1]))
        finish()
        if not {'ГОРЯЧЕЕ','БУРГЕРЫ','САЛАТЫ','СОУСЫ'}<=seen:raise ValueError('Не найдены границы разделов PDF')
        if 'меню' in content and ('обновля' in content or 'о бновля' in content):
            notes.append('Сайт предупреждает об обновлении меню и возможном отсутствии позиций; цены опубликованы, наличие не подтверждено.')
    if not items:raise ValueError('Не удалось извлечь цены из PDF')
    return deduplicate(items),notes
