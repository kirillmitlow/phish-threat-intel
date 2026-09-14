import io
from PIL import Image, ImageDraw
from core import favicon_analyzer


def _generate_test_icon(color=(0, 120, 215), circle_color=(255, 255, 255)) -> bytes:
    img = Image.new("RGBA", (32, 32), color)
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 24, 24], fill=circle_color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_extract_favicon_urls():
    html = """
    <html>
      <head>
        <link rel="stylesheet" href="/style.css">
        <link rel="shortcut icon" href="/static/img/favicon.ico">
        <link rel="apple-touch-icon" href="/static/img/apple-icon.png">
      </head>
      <body>Hello</body>
    </html>
    """
    urls = favicon_analyzer.extract_favicon_urls(html, base_url="https://secure-bank.example/auth/login")

    assert "https://secure-bank.example/static/img/favicon.ico" in urls
    assert "https://secure-bank.example/static/img/apple-icon.png" in urls
    assert "https://secure-bank.example/favicon.ico" in urls  # fallback в корень
    print("✅ test_extract_favicon_urls passed")


def test_favicon_dhash_and_distance():
    # 1. Эталонная иконка
    icon1 = _generate_test_icon(color=(10, 50, 200))
    # 2. Та же иконка, но чуть светлее и сохраненная в ICO (мутация фишеров)
    img2 = Image.open(io.BytesIO(icon1)).convert("RGB")
    buf = io.BytesIO()
    img2.save(buf, format="ICO")
    icon2 = buf.getvalue()

    # 3. Совершенно другая иконка (красный квадрат)
    icon_diff = _generate_test_icon(color=(220, 10, 10), circle_color=(0, 0, 0))

    res1 = favicon_analyzer.analyze_favicon_data(icon1)
    res2 = favicon_analyzer.analyze_favicon_data(icon2)
    res_diff = favicon_analyzer.analyze_favicon_data(icon_diff)

    assert res1["dhash"] is not None
    assert res2["dhash"] is not None

    dist_same = favicon_analyzer.dhash_distance(res1["dhash"], res2["dhash"])
    dist_diff = favicon_analyzer.dhash_distance(res1["dhash"], res_diff["dhash"])

    # Расстояние Хэмминга для одной и той же иконки в разных форматах должно быть минимальным (0..4)
    assert dist_same <= 4, f"Расстояние для похожих иконок должно быть <= 4, получено: {dist_same}"
    # Для принципиально разных иконок расстояние должно быть большим (> 10)
    assert dist_diff > 10, f"Расстояние для разных иконок должно быть большим, получено: {dist_diff}"

    print(f"✅ test_favicon_dhash_and_distance passed (dist_same={dist_same}, dist_diff={dist_diff})")


if __name__ == "__main__":
    test_extract_favicon_urls()
    test_favicon_dhash_and_distance()
    print("\n🎉 Все тесты Favicon успешно пройдены!")
