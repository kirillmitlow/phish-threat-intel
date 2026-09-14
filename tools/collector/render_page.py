from langchain_core.tools import tool

from .http_proxy import sandbox_request


@tool
def render_page(
    url: str | None = None,
    html: str | None = None,
    screenshot: bool = True,
    task_id: str | None = None,
) -> dict:
    """Рендерит подозрительную страницу в изолированном headless-браузере (песочница).

    Аргументы:
        url: URL страницы для анализа (необязательно, если передан html).
        html: сырой HTML вместо URL (для анализа HTML-вложений).
        screenshot: делать ли скриншот (PNG) в артефактах.
        task_id: имя подпапки артефактов (удобно для группировки по письму).

    Возвращает: final_url, redirect_chain, путь скриншота,
    размер DOM-снимка и признаки фишинга (формы, iframe, скрипты, обфускация).
    """
    if not url and not html:
        raise ValueError("Укажите либо url, либо html")
    result = sandbox_request(
        "/render",
        {
            "url": url,
            "html": html,
            "screenshot": screenshot,
            "task_id": task_id,
        },
        timeout=45,
    )
    return result