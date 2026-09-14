import tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from sandbox.services import qr_reader


def test_qr_validation():
    # Пустой путь
    res = qr_reader.extract({})
    assert res["ok"] is False
    assert "image_path обязателен" in res["error"]

    # Несуществующий файл
    res_missing = qr_reader.extract({"image_path": "/non/existent/qr.png"})
    assert res_missing["ok"] is False
    assert "не найден" in res_missing["error"]


def test_otsu_threshold():
    # Проверка работы алгоритма бинаризации Оцу
    img = Image.new("L", (100, 100), color=50)
    for x in range(50, 100):
        for y in range(50, 100):
            img.putpixel((x, y), 200)

    th = qr_reader._otsu_threshold(img)
    # Порог отсекает темные пиксели (50) от светлых (200)
    assert 50 <= th < 200


def test_qr_extract_with_mock():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_img = f.name
        img = Image.new("RGB", (64, 64), color="white")
        img.save(f, format="PNG")

    try:
        mock_result = [{
            "content": "https://secure-bank.example/auth",
            "box": [10, 10, 40, 40],
            "decoder": "pyzbar_original",
            "normalized": False,
            "normalization_stage": "original",
        }]
        with patch.object(qr_reader, "_decode_with_pyzbar", return_value=mock_result):
            res = qr_reader.extract({"image_path": tmp_img})
            assert res["ok"] is True
            assert res["qr_count"] == 1
            assert res["results"][0]["content"] == "https://secure-bank.example/auth"
    finally:
        Path(tmp_img).unlink(missing_ok=True)
