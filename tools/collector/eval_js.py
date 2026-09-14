from langchain_core.tools import tool

from .http_proxy import sandbox_request


@tool
def eval_js(code: str, extract_urls: bool = True) -> dict:
    """Выполняет JS-сниппет в изолированном браузере песочницы (headless Chromium).

    Нужен, чтобы прогнать обусцированный JS и увидеть результат — например,
    мошенники прячут ссылки в коде, который срабатывает только при выполнении.

    Аргументы:
        code: JS-сниппет для исполнения (без обёртки в функцию — она добавится).
        extract_urls: искать ли URL в результате (True по умолчанию).

    Возвращает: результат и список найденных в выводе ссылок.
    """
    if not code or not code.strip():
        raise ValueError("code обязателен")
    return sandbox_request(
        "/eval_js",
        {"code": code, "extract_urls": extract_urls},
        timeout=20,
    )