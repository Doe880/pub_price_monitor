"""Bounded extraction from text PDFs, scanned PDF pages and image menus.

OCR uses Tesseract as an optional, local dependency. No unreviewed inference:
a row must have an explicit currency price and belong to an allowed section.
"""
from io import BytesIO
import re

from .models import clean, normalized, not_beer, deduplicate, volume
from .parsers import make_item

SECTION = re.compile(r"^\s*(?:#{1,4}\s*)?(.{2,90})\s*$")
PRICE = re.compile(r"^\s*(?P<name>.+?)\s*(?:\.{2,}|\s[-–—|:]\s|\s{2,})\s*(?P<price>\d[\d\s]{1,5})\s*(?P<currency>₽|руб\.?|р\.)\s*$", re.I)
PORTION = re.compile(r"(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l|гр|г)\b", re.I)


class TextExtractionError(ValueError):
    pass


def _ocr_image(image, languages="rus+eng", min_confidence=65):
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise TextExtractionError("OCR недоступен: pip install -r requirements-ocr.txt") from exc
    try:
        raw = pytesseract.image_to_data(image, lang=languages, output_type=Output.DICT,
                                        config="--psm 6")
    except Exception as exc:
        raise TextExtractionError("Не удалось запустить Tesseract OCR или нет rus/eng языковых пакетов") from exc
    lines = {}
    for i, word in enumerate(raw["text"]):
        word = clean(word)
        if not word:
            continue
        try:
            conf = float(raw["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf < min_confidence:
            # A missing low-confidence token makes the row incomplete instead of
            # accidentally interpreting uncertain digits as a price.
            continue
        key = (raw["page_num"][i], raw["block_num"][i], raw["par_num"][i], raw["line_num"][i])
        lines.setdefault(key, []).append(word)
    return "\n".join(" ".join(words) for words in lines.values())


def extract_text(data, source):
    kind = source.get("format", "pdf")
    if kind not in {"pdf", "image"}:
        raise TextExtractionError("Текстовое извлечение поддерживает только PDF и изображения")
    if not isinstance(data, bytes) or len(data) > 12_000_000:
        raise TextExtractionError("Некорректный документ или превышен лимит 12 МБ")
    if kind == "pdf":
        if not data.startswith(b"%PDF"):
            raise TextExtractionError("Неверная сигнатура PDF")
        from pypdf import PdfReader
        try:
            pdf = PdfReader(BytesIO(data), strict=True)
            if not 1 <= len(pdf.pages) <= source.get("max_pages", 12):
                raise TextExtractionError("Число страниц PDF превышает допустимое")
            pages = [(p.extract_text(extraction_mode="layout") or "") if p.get("/Contents") else ""
                     for p in pdf.pages]
        except TextExtractionError:
            raise
        except Exception as exc:
            raise TextExtractionError("Не удалось прочитать PDF с текстовым слоем") from exc
        if all(len(t.strip()) >= source.get("min_page_text", 50) for t in pages):
            return "\n".join(pages), False
        if not source.get("allow_ocr", False):
            raise TextExtractionError("PDF содержит страницы без текстового слоя; требуется OCR")
        try:
            import fitz
            from PIL import Image
        except ImportError as exc:
            raise TextExtractionError("PDF OCR недоступен: pip install -r requirements-ocr.txt") from exc
        rendered = []
        doc = fitz.open(stream=data, filetype="pdf")
        try:
            for n, text in enumerate(pages):
                if len(text.strip()) >= source.get("min_page_text", 50):
                    rendered.append(text)
                    continue
                pix = doc[n].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                if pix.width * pix.height > 20_000_000:
                    raise TextExtractionError("PDF страница слишком велика для OCR")
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                rendered.append(_ocr_image(img, source.get("ocr_languages", "rus+eng"),
                                           source.get("min_ocr_confidence", 65)))
        finally:
            doc.close()
        return "\n".join(rendered), True
    if not data.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF")):
        raise TextExtractionError("Ожидается PNG или JPEG (либо WebP)")
    try:
        from PIL import Image, ImageOps
        image = Image.open(BytesIO(data))
        if image.format not in {"PNG", "JPEG", "WEBP"}:
            raise TextExtractionError("Недопустимый формат изображения")
        if image.width * image.height > 20_000_000:
            raise TextExtractionError("Изображение слишком велико")
        image = ImageOps.exif_transpose(image).convert("RGB")
    except TextExtractionError:
        raise
    except Exception as exc:
        raise TextExtractionError("Изображение повреждено") from exc
    return _ocr_image(image, source.get("ocr_languages", "rus+eng"),
                      source.get("min_ocr_confidence", 65)), True


def parse_extracted_text(text, source):
    """Parse only explicitly whitelisted section headings and unambiguous row prices.

    OCR rows remain 'review' (never 'ok') until a human validates them.
    """
    kind = source["kind"]
    requested = {normalized(x): x for x in source.get("sections", [])}
    if not requested:
        raise ValueError("Нужен фиксированный список проверенных разделов меню")
    section = None
    observed = set()
    items, warnings = [], []
    for raw in text.splitlines():
        line = clean(raw)
        if not line:
            continue
        heading = normalized(SECTION.fullmatch(line)[1]) if SECTION.fullmatch(line) else ""
        if heading in requested:
            section = requested[heading]
            observed.add(heading)
            continue
        if heading in {normalized(x) for x in source.get("stop_sections", [])}:
            section = None
            continue
        if section is None:
            continue
        match = PRICE.fullmatch(raw.strip())
        if not match:
            if "₽" in raw or "руб" in raw.lower():
                warnings.append("Неоднозначная строка: " + line[:100])
            continue
        name = clean(match["name"])
        if kind == "beer" and not_beer(name):
            continue
        price = float(match["price"].replace(" ", ""))
        m = PORTION.search(name)
        portion = m[0] if m else "не указан"
        ml = volume(portion) if kind == "beer" else None
        if kind == "beer" and ml is None:
            warnings.append("Объём не указан: " + name)
        serving = source.get("serving_type", "") if kind == "beer" else ""
        item = make_item(name, section, kind, price, portion,
                         ml=ml, serving=serving,
                         evidence=f"{section} | {line}")
        item.validate()
        items.append(item)
    missing = set(requested) - observed
    if missing:
        raise ValueError("Не найдены ожидаемые разделы: " + ", ".join(sorted(missing)))
    if len(items) < source.get("min_items", 1):
        raise ValueError("Недостаточно проверяемых позиций меню")
    return deduplicate(items), warnings


def parse_document(data, source):
    text, ocr = extract_text(data, source)
    rows, warnings = parse_extracted_text(text, source)
    if ocr:
        # Keep extracted evidence available for manual review, never commit as a
        # trusted complete menu via storage.current_rows.
        warnings.insert(0, "OCR требует ручной сверки с оригинальным меню")
    return rows, warnings
