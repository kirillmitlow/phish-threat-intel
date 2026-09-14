import pytest
from sandbox.services.downloader import _safe_name, download, ALLOWED_SCHEMES


def test_allowed_schemes():
    assert "http" in ALLOWED_SCHEMES
    assert "https" in ALLOWED_SCHEMES
    assert "file" not in ALLOWED_SCHEMES
    assert "ftp" not in ALLOWED_SCHEMES


def test_safe_name():
    # Проверяем очистку опасных символов в имени файла
    name = _safe_name("https://example.com/files/malware..exe?token=123")
    assert not name.startswith("..")
    assert ".exe" in name or "_" in name
    # Имя не должно содержать недопустимых символов путей
    assert "/" not in name
    assert "\\" not in name

    # Пустой путь дает fallback на 'download'
    empty_name = _safe_name("https://example.com/")
    assert "download" in empty_name


def test_download_validation():
    # Пустой URL
    res = download({})
    assert res["ok"] is False
    assert "url обязателен" in res["error"]

    # Запрещенная схема file://
    res_file = download({"url": "file:///etc/passwd"})
    assert res_file["ok"] is False
    assert "запрещена" in res_file["error"]

    # Запрещенная схема ftp://
    res_ftp = download({"url": "ftp://files.example.com/test.zip"})
    assert res_ftp["ok"] is False
    assert "запрещена" in res_ftp["error"]
