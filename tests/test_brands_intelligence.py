import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from core import storage
from core.brand_detector import (
    get_target_brands,
    resolve_brand,
    build_brand_prompt,
    _parse_brand_response,
    brand_fingerprint
)
from core.pipeline import analyze_brand


def test_target_brands_loading():
    brands = get_target_brands()
    assert len(brands) == 175, f"Ожидалось 175 брендов, получено {len(brands)}"
    assert "Сбер" in brands
    assert "Т-Банк" in brands
    assert "PayPal" in brands
    print("✅ test_target_brands_loading passed")


def test_resolve_brand():
    # Прямые совпадения с целевым списком (без учета регистра)
    assert resolve_brand("Сбер") == ("Сбер", True)
    assert resolve_brand("сбер") == ("Сбер", True)
    assert resolve_brand("Т-Банк") == ("Т-Банк", True)
    assert resolve_brand("т-банк") == ("Т-Банк", True)
    assert resolve_brand("Apple ID") == ("Apple ID", True)
    assert resolve_brand("apple id") == ("Apple ID", True)
    assert resolve_brand("PayPal") == ("PayPal", True)
    assert resolve_brand("paypal") == ("PayPal", True)
    assert resolve_brand("госуслуги") == ("Госуслуги", True)
    assert resolve_brand("LINE") == ("LINE", True)

    # Совпадение по токену в названии компании (например, PayPal в PayPal Inc.)
    assert resolve_brand("PayPal Inc.") == ("PayPal", True)

    # Бренд с пояснением в скобках в справочнике
    canon, in_target = resolve_brand("AEON")
    assert in_target is True and "AEON" in canon

    # Open-set: бренд вне списка
    assert resolve_brand("Steam") == ("Steam", False)
    assert resolve_brand("Telegram") == ("Telegram", False)

    # Пустые / нейтральные значения
    assert resolve_brand(None) == (None, False)
    assert resolve_brand("null") == (None, False)
    assert resolve_brand("") == (None, False)
    print("✅ test_resolve_brand passed")


def test_parse_brand_response():
    resp_target = '{"brand": "Сбер", "confidence": 0.95, "evidence": "Логотип Сбербанка и форма онлайн-банка"}'
    parsed = _parse_brand_response(resp_target)
    assert parsed["brand"] == "Сбер"
    assert parsed["in_target"] is True
    assert parsed["confidence"] == 0.95

    resp_openset = '{"brand": "Steam", "confidence": 0.88, "evidence": "Логотип Steam Community"}'
    parsed_os = _parse_brand_response(resp_openset)
    assert parsed_os["brand"] == "Steam"
    assert parsed_os["in_target"] is False
    assert parsed_os["confidence"] == 0.88

    resp_null = '{"brand": null, "confidence": 0.0, "evidence": "Нейтральная страница паркинга"}'
    parsed_null = _parse_brand_response(resp_null)
    assert parsed_null["brand"] is None
    assert parsed_null["in_target"] is False
    print("✅ test_parse_brand_response passed")


def test_storage_and_migration():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # 1. Инициализация и проверка структуры
        storage.init_db(db_path)
        conn = storage.get_conn(db_path)
        cur = conn.execute("PRAGMA table_info(brands)")
        cols = {r["name"]: r["type"] for r in cur.fetchall()}
        assert "in_target" in cols, "Колонка in_target отсутствует в таблице brands"

        # 2. Добавление записи с in_target
        sample_id = storage.create_sample(conn, "url", "https://fake-sber.ru")
        storage.add_brand(conn, sample_id, "Сбер", 0.95, method="vlm", evidence="логотип", in_target=True)
        storage.add_brand(conn, sample_id, "Steam", 0.8, method="vlm", evidence="логотип", in_target=False)

        brands = storage.list_brands(conn, sample_id)
        assert len(brands) == 2
        assert brands[0]["brand"] == "Сбер" and brands[0]["in_target"] is True
        assert brands[1]["brand"] == "Steam" and brands[1]["in_target"] is False
        conn.close()

        # 3. Тест автомиграции со старой схемой
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f_old:
            old_db_path = f_old.name

        old_conn = sqlite3.connect(old_db_path)
        old_conn.execute("""
            CREATE TABLE brands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER,
                brand TEXT NOT NULL,
                confidence REAL,
                method TEXT,
                evidence TEXT,
                created_at TEXT
            )
        """)
        old_conn.execute("INSERT INTO brands (brand, confidence, created_at) VALUES ('PayPal', 0.9, '2026-01-01')")
        old_conn.commit()
        old_conn.close()

        # Запуск init_db на старой базе должен добавить in_target без потери данных
        storage.init_db(old_db_path)
        mig_conn = storage.get_conn(old_db_path)
        mig_cur = mig_conn.execute("PRAGMA table_info(brands)")
        mig_cols = [r["name"] for r in mig_cur.fetchall()]
        assert "in_target" in mig_cols, "Миграция не добавила in_target"
        rows = mig_conn.execute("SELECT * FROM brands").fetchall()
        assert len(rows) == 1
        assert rows[0]["brand"] == "PayPal"
        mig_conn.close()
        os.remove(old_db_path)

        print("✅ test_storage_and_migration passed")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_pipeline_analyze_brand_features():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        storage.init_db(db_path)
        conn = storage.get_conn(db_path)
        sample_id = storage.create_sample(conn, "url", "https://sber-verify-security.xyz")

        # Мокаем detect_brand, чтобы протестировать логику формирования признаков
        with patch("core.pipeline.detect_brand") as mock_detect:
            mock_detect.return_value = {
                "brand": "Сбер",
                "in_target": True,
                "confidence": 0.95,
                "evidence": "Логотип Сбера и форма логина"
            }
            analyze_brand(conn, sample_id, ["fake_screenshot.png"], ["sber-verify-security.xyz"])

        brands = storage.list_brands(conn, sample_id)
        assert len(brands) == 1
        assert brands[0]["brand"] == "Сбер"
        assert brands[0]["in_target"] is True

        findings = storage.list_findings(conn, sample_id)
        assert len(findings) == 1
        assert findings[0]["technique"] == "brand_impersonation"
        assert findings[0]["severity"] == "high"

        signatures = storage.list_signatures(conn, sample_id)
        kinds = [s["kind"] for s in signatures]
        assert "brand_feature" in kinds
        assert "reason_code" in kinds

        reason_code_sigs = [s for s in signatures if s["kind"] == "reason_code"]
        assert reason_code_sigs[0]["signature"] == "BRAND_IMPERSONATION_TARGET_СБЕР"

        conn.close()
        print("✅ test_pipeline_analyze_brand_features passed")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    test_target_brands_loading()
    test_resolve_brand()
    test_parse_brand_response()
    test_storage_and_migration()
    test_pipeline_analyze_brand_features()
    print("\n🎉 Все тесты модуля брендов успешно пройдены!")
