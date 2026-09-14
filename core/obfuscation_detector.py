import math
import re
from typing import Dict, List


def calculate_shannon_entropy(text: str) -> float:
    if not text:
        return 0.0

    entropy = 0.0
    length = len(text)
    freq = {}
    for char in text:
        freq[char] = freq.get(char, 0) + 1

    for count in freq.values():
        p = count / length
        entropy -= p * math.log2(p)

    return round(entropy, 3)


def analyze_obfuscation(html: str) -> Dict:
    findings = []
    flags = {}

    # Извлечение содержимого всех тегов <script>
    scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.IGNORECASE | re.DOTALL)

    max_entropy = 0.0
    high_entropy_blocks = 0
    for s in scripts:
        clean_s = s.strip()
        if len(clean_s) > 100:
            ent = calculate_shannon_entropy(clean_s)
            if ent > max_entropy:
                max_entropy = ent
            if ent >= 5.2:
                high_entropy_blocks += 1

    flags["max_entropy"] = max_entropy
    flags["high_entropy_scripts"] = high_entropy_blocks
    if high_entropy_blocks > 0:
        findings.append("high_entropy_script_payload")

    # Паттерны упаковщиков и обфускаторов
    # 1. Dean Edwards Packer: eval(function(p,a,c,k,e,d)...
    if re.search(r'eval\s*\(\s*function\s*\(\s*p\s*,\s*a\s*,\s*c\s*,\s*k', html, re.IGNORECASE):
        flags["has_dean_edwards_packer"] = True
        findings.append("packer_dean_edwards")

    # 2. JSFuck: последовательности [][(![]+[])
    if len(re.findall(r'\[\]\[\(!\[\]\+\[\]\)', html)) > 0 or len(re.findall(r'\[\+!\[\]\]', html)) > 5:
        flags["has_jsfuck"] = True
        findings.append("jsfuck_obfuscation")

    # 3. String.fromCharCode цепочки
    charcodes = len(re.findall(r'String\.fromCharCode\s*\(', html, re.IGNORECASE))
    flags["charcode_count"] = charcodes
    if charcodes > 0:
        findings.append("charcode_obfuscation")

    # 4. eval + atob / unescape
    if re.search(r'eval\s*\(\s*(?:window\.)?atob\s*\(', html, re.IGNORECASE):
        flags["eval_atob"] = True
        findings.append("eval_atob_execution")

    if re.search(r'eval\s*\(\s*(?:window\.)?unescape\s*\(', html, re.IGNORECASE):
        flags["eval_unescape"] = True
        findings.append("eval_unescape_execution")

    # 5. Base64 блобы данных в скриптах/HTML
    base64_blobs = re.findall(r'data:text/javascript;base64,[A-Za-z0-9+/=]{40,}', html)
    if base64_blobs:
        flags["base64_js_blob"] = True
        findings.append("base64_script_blob")

    # 6. document.write обфускация
    if "document.write(unescape(" in html or "document.write(decodeURIComponent(" in html:
        flags["docwrite_decode"] = True
        findings.append("document_write_decode")

    is_obfuscated = len(findings) > 0

    return {
        "is_obfuscated": is_obfuscated,
        "techniques": findings,
        "max_entropy": max_entropy,
        "flags": flags,
    }


def detect_phishing_kit_markers(html: str) -> Dict:
    markers = []
    details = {}

    # 1. Telegram Bot Exfiltration
    tg_bots = re.findall(r'(?:api\.telegram\.org/bot)(\d+:[A-Za-z0-9_-]{30,})', html)
    if tg_bots:
        markers.append("telegram_bot_exfiltration")
        details["telegram_bot_token"] = tg_bots[0][:10] + "..."

    # 2. Discord Webhook Exfiltration
    discord_hooks = re.findall(r'discord(?:app)?\.com/api/webhooks/(\d+/[A-Za-z0-9_-]+)', html)
    if discord_hooks:
        markers.append("discord_webhook_exfiltration")
        details["discord_webhook"] = True

    # 3. Маркеры антибот-защиты в фишинг-китах (antibot.php, antibot.js, blackbox)
    antibot_patterns = [
        r'antibot\.php',
        r'antibot\.js',
        r'killbot',
        r'fucking_bot',
        r'blocker\.php',
        r'bot_detect',
    ]
    for pat in antibot_patterns:
        if re.search(pat, html, re.IGNORECASE):
            markers.append("phishing_kit_antibot")
            details["antibot_pattern"] = pat
            break

    # 4. Маркеры известных админок фишинг-китов в коде/ссылках
    kit_paths = [
        r'/panel/login\.php',
        r'/admin/login\.php',
        r'/logs\.txt',
        r'/victim\.txt',
        r'/result\.php',
        r'/action\.php\?action=login',
        r'/send\.php',
        r'/gate\.php',
    ]
    for pat in kit_paths:
        if re.search(pat, html, re.IGNORECASE):
            markers.append("phishing_kit_gate_path")
            details["gate_path"] = pat
            break

    return {
        "has_kit_markers": len(markers) > 0,
        "markers": markers,
        "details": details,
    }
