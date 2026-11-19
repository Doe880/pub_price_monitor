"""No network or OCR runtime needed: strict parser integration tests."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from pypdf import PdfWriter

from monitor.document_menus import parse_extracted_text, parse_document, extract_text, TextExtractionError
from monitor.structured_menus import parse_structured_html
from monitor.fetch import Fetcher
from monitor.parsers import parse


def source(kind="food", **kwargs):
    return dict(parser="document", format="pdf", kind=kind, sections=["ГОРЯЧИЕ БЛЮДА"],
                stop_sections=["ЗАКУСКИ", "ДЕСЕРТЫ"], min_items=1, **kwargs)


def test_pdf_text_sections_are_strict_and_prices_explicit():
    sample = """ЗАКУСКИ
Сыр ... 250 ₽
ГОРЯЧИЕ БЛЮДА
Пастуший пирог — 650 ₽
Рибай 300 г — 1450 руб
ДЕСЕРТЫ
Мороженое — 320 ₽
"""
    rows, notes = parse_extracted_text(sample, source())
    assert [(r.name, r.price) for r in rows] == [
        ("Пастуший пирог", 650), ("Рибай 300 г", 1450)
    ]
    assert rows[1].portion == "300 г"
    assert not notes


def test_pdf_parser_rejects_amounts_without_currency_and_unlisted_sections():
    with pytest.raises(ValueError, match="Недостаточно"):
        parse_extracted_text("ГОРЯЧИЕ БЛЮДА\nКотлета — 590\n", source())
    with pytest.raises(ValueError, match="ожидаемые разделы"):
        parse_extracted_text("ЗАКУСКИ\nСтейк — 590 ₽", source())


def test_beer_ocr_cannot_infer_volume_or_merge_cider():
    cfg = dict(parser="document", format="image", kind="beer",
               sections=["РАЗЛИВНОЕ ПИВО"], stop_sections=["СИДР"], min_items=1)
    rows, warnings = parse_extracted_text(
        "РАЗЛИВНОЕ ПИВО\nЛагер 0,5 л — 420 ₽\nСидр 0,5 л — 400 ₽\nСИДР\nЯблочный — 450 ₽", cfg)
    assert len(rows) == 1 and rows[0].volume_ml == 500
    assert not warnings


def test_scanned_pdf_is_not_silently_interpreted_as_blank_menu():
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    pdf = BytesIO()
    writer.write(pdf)
    with pytest.raises(TextExtractionError, match="требуется OCR"):
        extract_text(pdf.getvalue(), source())


def test_invalid_document_does_not_publish():
    with pytest.raises(TextExtractionError, match="Неверная сигнатура"):
        extract_text(b"hello world", source())
    with pytest.raises(TextExtractionError, match="Некорректный документ"):
        extract_text(b"%PDF" + b"X" * 24_000_001, source())


def test_ocr_flag_forces_partial_review(monkeypatch):
    from monitor import document_menus
    monkeypatch.setattr(document_menus, "extract_text",
                        lambda data, cfg: ("ГОРЯЧИЕ БЛЮДА\nСтейк — 650 ₽", True))
    rows, warnings = parse_document(b"mock", source())
    assert len(rows) == 1
    assert any("ручной сверки" in warning for warning in warnings)


def test_structured_html_enforces_sections_and_explicit_currency():
    cfg = dict(parser="structured_html", kind="food", min_items=1,
               sections=["Горячие блюда"],
               selectors=dict(card=".card", name=".name", price=".price",
                              section=".section", portion=".portion"))
    html = """<html><div class="card"><b class="section">Горячие блюда</b>
      <b class="name">Стейк</b><span class="portion">300 г</span>
      <span class="price">1 400 ₽</span></div>
      <div class="card"><b class="section">Закуски</b>
      <b class="name">Сыр</b><span class="price">250 ₽</span></div></html>"""
    rows, notes = parse(html, cfg, None)
    assert len(rows) == 1 and rows[0].price == 1400
    assert not notes
    with pytest.raises(ValueError, match="слишком мало|Слишком мало|разделы"):
        parse_structured_html(html.replace("1 400 ₽", "1400"), cfg)


def test_browser_host_whitelist_and_binary_response(tmp_path, monkeypatch):
    fetcher = Fetcher(tmp_path, {"pub.example"})
    try:
        with pytest.raises(ValueError, match="разрешённых"):
            fetcher._check_url("https://unexpected.example/a.pdf")
        with pytest.raises(ValueError, match="разрешённых"):
            fetcher._check_url("http://pub.example/menu")
        with pytest.raises(ValueError, match="разрешённых"):
            fetcher._check_url("https://pub.example:8080/menu")
        monkeypatch.setattr(fetcher, "check_robots", lambda url: None)
        monkeypatch.setattr(fetcher, "_get",
                            lambda url, **kwargs: (b"\x89PNG\r\n\x1a\nDATA", "image/png", url))
        img = fetcher.get("https://pub.example/menu.png", kind="image")
        assert img.startswith(b"\x89PNG")
        assert fetcher.files[0]["sha256"]
        assert Path(tmp_path / fetcher.files[0]["path"]).exists()
    finally:
        fetcher.close()
