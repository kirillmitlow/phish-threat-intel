import json
import sqlite3
import tempfile
from pathlib import Path

from core import storage
from core import campaign_cluster
from core import rule_exporter


def test_campaign_clustering():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_campaigns.db")
        storage.init_db(db_path)
        conn = storage.get_conn(db_path)

        try:
            # 1. Создаем первый образец (Сбер, шаблон A)
            s1 = storage.create_sample(conn, "url", "https://sber-fake-1.com/login")
            c1_res = campaign_cluster.cluster_sample_into_campaign(
                conn, s1, target_brand="Сбер", dom_hash="a1b2c3d4e5f67890" * 4
            )
            conn.commit()

            assert c1_res["is_new"] is True, "Первый образец должен открыть новую кампанию"
            assert c1_res["sample_count"] == 1
            assert "СБЕР" in c1_res["name"] or "SBER" in c1_res["name"]

            # 2. Создаем второй образец (Сбер, ТОТ ЖЕ шаблон A, но другой домен)
            s2 = storage.create_sample(conn, "url", "https://sber-pay-online.ru/auth")
            c2_res = campaign_cluster.cluster_sample_into_campaign(
                conn, s2, target_brand="Сбер", dom_hash="a1b2c3d4e5f67890" * 4
            )
            conn.commit()

            assert c2_res["is_new"] is False, "Второй образец должен связаться с существующей кампанией"
            assert c2_res["campaign_id"] == c1_res["campaign_id"]
            assert c2_res["sample_count"] == 2

            # 3. Создаем третий образец (Т-Банк, другой шаблон B)
            s3 = storage.create_sample(conn, "url", "https://t-bank-stealer.com")
            c3_res = campaign_cluster.cluster_sample_into_campaign(
                conn, s3, target_brand="Т-Банк", dom_hash="9988776655443322" * 4
            )
            conn.commit()

            assert c3_res["is_new"] is True, "Другой бренд и шаблон должны открыть вторую кампанию"
            assert c3_res["campaign_id"] != c1_res["campaign_id"]

            # Проверяем отчет в БД
            camps = storage.list_campaigns(conn)
            assert len(camps) == 2, f"Должно быть ровно 2 кампании, получено: {len(camps)}"
        finally:
            conn.close()

    print("✅ test_campaign_clustering passed")


def test_rule_exporter():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_export.db")
        storage.init_db(db_path)
        conn = storage.get_conn(db_path)

        s_id = storage.create_sample(conn, "url", "https://fake-login.xyz")
        storage.add_brand(conn, s_id, "Сбер", in_target=True, confidence=0.95)
        storage.add_signature(conn, s_id, "brand_feature", "sberbank.fake-login.xyz", {"in_target": True})
        storage.add_signature(conn, s_id, "dom_template", "dom_hash_1234567890abcdef", {})
        storage.add_signature(conn, s_id, "url_template", "fake-login.xyz/{}/login", {})
        storage.add_signature(conn, s_id, "reason_code", "BRAND_IMPERSONATION_TARGET_SBER", {})
        storage.add_artifact(conn, s_id, "html", "/app/data/x.html", "md5_val", "sha256_fake_hash_12345", {})
        conn.commit()

        # 1. JSON Rulepack
        pack = rule_exporter.export_json_rulepack(conn)
        assert "manifest" in pack
        assert pack["manifest"]["total_rules"] >= 3
        assert len(pack["brand_rules"]) == 1
        assert len(pack["dom_template_rules"]) == 1
        assert len(pack["url_template_rules"]) == 1
        assert len(pack["attachment_fingerprints"]) == 1

        # 2. Rspamd config
        rspamd_cfg = rule_exporter.export_rspamd_rules(conn)
        assert "rspamd_config" in rspamd_cfg
        assert "RULE_BRAND_" in rspamd_cfg
        assert "RULE_DOM_" in rspamd_cfg

        # 3. YARA rules
        yara_rules = rule_exporter.export_yara_rules(conn)
        assert "rule Phish_Artifact_html_1" in yara_rules
        assert "sha256_fake_hash_12345" in yara_rules

        conn.close()

    print("✅ test_rule_exporter passed")


if __name__ == "__main__":
    test_campaign_clustering()
    test_rule_exporter()
    print("\n🎉 Все тесты кампаний и экспорта успешно пройдены!")
