import re
from pathlib import Path
from typing import Optional
from html.parser import HTMLParser

ARTIFACTS_DIR = Path("/app/data/artifacts")

# Теги, где берём URL из конкретного атрибута
_TAG_ATTRS = {
    "a": "href",
    "area": "href",
    "link": "href",
    "script": "src",
    "img": "src",
    "iframe": "src",
    "frame": "src",
    "embed": "src",
    "source": "src",
    "form": "action",
    "meta": "content",
    "input": "src",
    "video": "src",
    "audio": "src",
}


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict] = []
        self._current_attrs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag not in _TAG_ATTRS:
            return
        attr = _TAG_ATTRS[tag]
        d = dict((k.lower(), v) for k, v in attrs)
        url = d.get(attr)
        if not url:
            return
        self.links.append({
            "tag": tag,
            "attr": attr,
            "url": url,
            "text": (d.get("title") or d.get("alt") or "").strip(),
        })


def _normalize_url(url: str) -> str:
    url = url.strip().strip("'\"")
    lowered = url.lower()
    if lowered.startswith(("javascript:", "vbscript:", "data:text/html",
                           "data:text/javascript", "file:", "mailto:", "tel:")):
        return ""
    # Обрезаем хэши и query-мусор? Нет — query может быть важна. Оставляем как есть.
    return url


def _extract_from_html(html: str) -> list[dict]:
    parser = _LinkExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return [l for l in parser.links if _normalize_url(l["url"])]


def extract_links(payload: dict) -> dict:
    html = payload.get("html")
    html_path = payload.get("html_path")

    if not html and not html_path:
        return {"ok": False, "error": "нужно указать html или html_path"}

    if html_path:
        p = Path(html_path)
        if not p.is_absolute():
            p = ARTIFACTS_DIR / p
        if not p.exists():
            return {"ok": False, "error": f"файл не найден: {p}"}
        try:
            html = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"ok": False, "error": f"не удалось прочитать: {e}"}

    links = _extract_from_html(html or "")
    # Убираем дубликаты, сохраняя порядок
    seen = set()
    unique = []
    for l in links:
        key = (l["tag"], l["attr"], l["url"])
        if key not in seen:
            seen.add(key)
            unique.append(l)

    return {"ok": True, "total": len(unique), "links": unique}