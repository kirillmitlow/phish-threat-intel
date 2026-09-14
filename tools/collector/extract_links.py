from langchain_core.tools import tool

from .http_proxy import sandbox_request


@tool
def extract_links(html: str | None = None, html_path: str | None = None) -> dict:
    """Вытаскивает ВСЕ ссылки из HTML/DOM-снимка в изолированной песочнице.

    Собирает все внешние/внутренние ресурсы страницы: ссылки (a/href),
    скрипты (script/src), формы (form/action), iframe, img, favicon и т.п.

    Аргументы (укажи одно):
        html: сырой HTML для разбора.
        html_path: путь к HTML-файлу на общем томе (/app/data).

    Возвращает список {tag, attr, url} и их количество.
    """
    if not html and not html_path:
        raise ValueError("Укажите либо html, либо html_path")
    return sandbox_request(
        "/extract_links",
        {"html": html, "html_path": html_path},
        timeout=20,
    )