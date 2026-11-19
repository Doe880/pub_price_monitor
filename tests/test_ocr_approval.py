import pytest

from monitor import storage
from monitor.models import Item


def test_quarantined_ocr_requires_explicit_audited_approval(tmp_path):
    db = tmp_path / "prices.sqlite3"
    pubs = [dict(id="sample", name="Паб", district="ЦАО", area="Центр",
                 address="Москва", sources=[dict(id="sample_ocr",
                                                 url="https://official.example/menu.pdf",
                                                 kind="food", parser="document")])]
    storage.sync_sources(pubs, path=db)
    item = Item(name="Стейк", category="Горячие блюда", subcategory="ГОРЯЧИЕ БЛЮДА",
                price=650, portion="300 г", evidence="OCR: Стейк 300 г — 650 ₽")
    check_id = storage.save_check("sample_ocr", "review", [item],
                                  "OCR требует ручной сверки", "snapshots/fake", path=db)
    check, rows = storage.review_check(check_id, path=db)
    assert check["status"] == "review"
    assert rows[0]["price"] == 650
    assert storage.current_rows(path=db) == []
    with pytest.raises(ValueError, match="проверяющего"):
        storage.approve_ocr_check(check_id, "", path=db)
    assert storage.approve_ocr_check(check_id, "Проверяющий", path=db) == check_id
    with storage.connect(db) as c:
        check = c.execute("SELECT status FROM checks WHERE id=?", (check_id,)).fetchone()
        audit = c.execute("SELECT approved_by,original_status FROM approvals WHERE check_id=?",
                          (check_id,)).fetchone()
    assert check["status"] == "ok"
    assert audit["original_status"] == "review"
    assert audit["approved_by"] == "Проверяющий"
    assert len(storage.current_rows(path=db)) == 1
    with pytest.raises(ValueError, match="только"):
        storage.approve_ocr_check(check_id, "Проверяющий", path=db)


def test_non_ocr_review_cannot_be_approved(tmp_path):
    db=tmp_path/"bad.sqlite3"
    storage.sync_sources([dict(id="sample",name="Sample",district="ЦАО",
                               area="Центр",address="Москва",
                               sources=[dict(id="s",url="https://official.example",
                                             kind="food")])],path=db)
    check_id=storage.save_check("s","review",[],"Мало позиций","raw",path=db)
    with pytest.raises(ValueError,match="только"):
        storage.approve_ocr_check(check_id,"Проверяющий",path=db)
