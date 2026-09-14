import hashlib
import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

# Семантические структурные теги для остова страницы
_STRUCTURAL_TAGS = {
    "html", "head", "body", "header", "nav", "main", "footer", "section",
    "article", "aside", "div", "form", "input", "button", "select",
    "textarea", "table", "thead", "tbody", "tr", "td", "th", "ul", "ol",
    "li", "a", "img", "iframe", "p", "h1", "h2", "h3", "h4", "h5", "h6"
}


class _DOMSkeletonParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skeleton_tokens: List[str] = []
        self._in_script_or_style = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        tag_lower = tag.lower()
        if tag_lower in ("script", "style", "noscript"):
            self._in_script_or_style = True
            return

        if self._in_script_or_style:
            return

        if tag_lower in _STRUCTURAL_TAGS:
            if tag_lower == "input":
                attr_dict = {k.lower(): (v or "").lower() for k, v in attrs}
                input_type = attr_dict.get("type", "text")
                self.skeleton_tokens.append(f"<input:{input_type}>")
            else:
                self.skeleton_tokens.append(f"<{tag_lower}>")

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in ("script", "style", "noscript"):
            self._in_script_or_style = False
            return

        if self._in_script_or_style:
            return

        if tag_lower in _STRUCTURAL_TAGS and tag_lower not in ("input", "img"):
            self.skeleton_tokens.append(f"</{tag_lower}>")

    def error(self, message):
        pass


def extract_dom_skeleton(html: str) -> str:
    if not html:
        return ""
    parser = _DOMSkeletonParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    return "".join(parser.skeleton_tokens)


def compute_dom_hash(skeleton: str) -> str:
    if not skeleton:
        return ""
    return hashlib.sha256(skeleton.encode("utf-8")).hexdigest()


def compute_simhash(skeleton: str, n: int = 3) -> int:
    if not skeleton:
        return 0

    tokens = re.findall(r"<[^>]+>", skeleton)
    if not tokens:
        return 0

    shingles = []
    if len(tokens) < n:
        shingles = ["".join(tokens)]
    else:
        for i in range(len(tokens) - n + 1):
            shingles.append("".join(tokens[i:i + n]))

    v = [0] * 64
    for shingle in shingles:
        h = int(hashlib.md5(shingle.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(64):
            bit = (h >> i) & 1
            if bit == 1:
                v[i] += 1
            else:
                v[i] -= 1

    simhash = 0
    for i in range(64):
        if v[i] > 0:
            simhash |= (1 << i)
    return simhash


def simhash_similarity(hash1: int, hash2: int) -> float:
    if hash1 == 0 or hash2 == 0:
        return 0.0
    xor = hash1 ^ hash2
    diff_bits = bin(xor).count("1")
    return 1.0 - (diff_bits / 64.0)


def _extract_domain(url: str) -> str:
    if not url:
        return ""
    if not url.startswith(("http://", "https://", "//")):
        url = "http://" + url
    parsed = urlparse(url)
    netloc = parsed.netloc.split(":")[0].lower()
    return netloc


def analyze_forms_deep(html: str, page_url_or_domain: str = "") -> Dict:
    page_domain = _extract_domain(page_url_or_domain)

    forms_data = []
    has_cross_domain_post = False
    has_credential_harvesting = False
    c2_webhook_detected = None

    # Поиск всех блоков <form>...</form>
    form_matches = list(re.finditer(r"<form\b([^>]*)>(.*?)</form>", html, re.IGNORECASE | re.DOTALL))

    # Если закрывающий тег отсутствует (часто в фишинге) — парсим сами теги form
    if not form_matches:
        for m in re.finditer(r"<form\b([^>]*)>", html, re.IGNORECASE):
            attrs_str = m.group(1)
            form_matches.append((attrs_str, html[m.end():m.end() + 2000]))
    else:
        form_matches = [(m.group(1), m.group(2)) for m in form_matches]

    for attrs_str, content in form_matches:
        action_m = re.search(r'action\s*=\s*["\']([^"\']*)["\']', attrs_str, re.IGNORECASE)
        method_m = re.search(r'method\s*=\s*["\'](\w+)["\']', attrs_str, re.IGNORECASE)
        style_m = re.search(r'style\s*=\s*["\']([^"\']*)["\']', attrs_str, re.IGNORECASE)

        action = (action_m.group(1).strip() if action_m else "").strip()
        method = (method_m.group(1).upper() if method_m else "GET").strip()
        style = (style_m.group(1).lower() if style_m else "")

        is_hidden_form = bool(
            "display:none" in style or
            "display: none" in style or
            "visibility:hidden" in style or
            "opacity:0" in style
        )

        # Анализ action
        is_cross_domain = False
        action_domain = ""
        is_data_uri = action.lower().startswith("data:")
        is_js_void = action.lower().startswith(("javascript:", "#")) or not action

        if action and not is_data_uri and not is_js_void and not action.startswith(("/", "?", "#")):
            action_domain = _extract_domain(action)
            if page_domain and action_domain and action_domain != page_domain:
                is_cross_domain = True
                has_cross_domain_post = True

        # Проверка известных C2 endpoints
        if "api.telegram.org/bot" in action.lower():
            c2_webhook_detected = "telegram_bot_api"
        elif "discord.com/api/webhooks" in action.lower():
            c2_webhook_detected = "discord_webhook"

        # Поля внутри формы
        passwords = len(re.findall(r'<input\b[^>]*type\s*=\s*["\']password["\']', content, re.IGNORECASE))
        emails = len(re.findall(r'<input\b[^>]*type\s*=\s*["\']email["\']', content, re.IGNORECASE))
        texts = len(re.findall(r'<input\b[^>]*type\s*=\s*["\']text["\']', content, re.IGNORECASE))
        hiddens = len(re.findall(r'<input\b[^>]*type\s*=\s*["\']hidden["\']', content, re.IGNORECASE))

        # Поиск ключевых слов в именах полей (card, cvv, pin, phone, ssn)
        card_fields = len(re.findall(r'<input\b[^>]*(?:card|cvv|cvc|pan|expir)[^>]*>', content, re.IGNORECASE))

        if passwords > 0 or card_fields > 0:
            has_credential_harvesting = True

        forms_data.append({
            "action": action,
            "method": method,
            "action_domain": action_domain,
            "is_cross_domain": is_cross_domain,
            "is_hidden_form": is_hidden_form,
            "is_data_uri": is_data_uri,
            "password_fields": passwords,
            "email_fields": emails,
            "text_fields": texts,
            "hidden_fields": hiddens,
            "card_fields": card_fields,
        })

    # Общий подсчет паролей по всему HTML на случай бестеговых форм (AJAX)
    total_passwords = len(re.findall(r'<input\b[^>]*type\s*=\s*["\']password["\']', html, re.IGNORECASE))
    if total_passwords > 0:
        has_credential_harvesting = True

    return {
        "forms": forms_data,
        "form_count": len(forms_data),
        "has_cross_domain_post": has_cross_domain_post,
        "has_credential_harvesting": has_credential_harvesting,
        "c2_webhook_detected": c2_webhook_detected,
        "total_password_fields": total_passwords,
    }
