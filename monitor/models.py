from dataclasses import dataclass, asdict
import hashlib
import re
import math


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('\xa0', ' ')).strip()


def normalized(value):
    return clean(value).casefold().replace('ё', 'е')


@dataclass
class Item:
    name: str
    category: str
    subcategory: str
    price: float
    portion: str = 'не указан'
    volume_ml: float | None = None
    weight_g: float | None = None
    price_basis: str = 'порция'
    serving_type: str = ''
    alcohol_free: bool = False
    evidence: str = ''
    note: str = ''

    @property
    def key(self):
        # Never merge pubs, draft/bottle, portion sizes or food sold per 100 g.
        identity = '|'.join(normalized(v) for v in
                            [self.name, self.category, self.portion, self.price_basis,
                             self.serving_type, str(self.alcohol_free)])
        return hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]

    def validate(self):
        if not self.name or len(self.name) > 350:
            raise ValueError('Неверное название')
        if not math.isfinite(self.price) or not 30 <= self.price <= 100000:
            raise ValueError('Цена вне допустимого диапазона')
        if self.category not in {'Пиво', 'Горячие блюда'}:
            raise ValueError('Недопустимая категория')
        if self.volume_ml is not None and not 50 <= self.volume_ml <= 5000:
            raise ValueError('Неверный объём')
        if not self.evidence:
            raise ValueError('Нет текста-основания')
        return self

    def record(self):
        return dict(asdict(self), item_key=self.key)


def deduplicate(items):
    result = {}
    for item in items:
        item.validate()
        if item.key in result and result[item.key].price != item.price:
            raise ValueError('Конфликт цен одной позиции: ' + item.name)
        result[item.key] = item
    return list(result.values())


def volume(text):
    """Only explicit units: don't interpret alcohol percentage as serving volume."""
    m = re.search(r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l)\b', clean(text), re.I)
    if not m:
        return None
    n = float(m[1].replace(',', '.'))
    return n * (1000 if m[2].lower() in {'л', 'l'} else 1)


def not_beer(name):
    # Known cider names mixed into beer sections on the monitored websites.
    return bool(re.search(r'сидр|cider|cidre|cidr|galipette|тэтчерс|thatchers|магнерс|magners|dickiy\s*crest|дикий\s*крест|stowford|сто[уы]форд', name, re.I))
