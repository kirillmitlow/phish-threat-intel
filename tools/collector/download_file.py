from langchain_core.tools import tool

from .http_proxy import sandbox_request


@tool
def download_file(url: str, task_id: str | None = None) -> dict:
    """Скачивает файл по ссылке в изолированную песочницу (на общий том /app/data).

    Используй, когда нашёл ссылку на файл (архив, документ, картинку) и хочешь
    получить его для дальнейшего разбора. Только скачивает — НЕ исполняет.

    Аргументы:
        url: ссылка на файл (только http/https).
        task_id: подпапка артефактов (удобно та же, что у текущего образца).

    Возвращает: путь к сохранённому файлу, размер, финальный URL,
    цепочку редиректов и content-type. Путь можно передать в другие тулзы:
    unpack_attachment, extract_document, render_pdf_to_png, extract_qr, hash_artifacts.
    """
    if not url or not url.strip():
        raise ValueError("url обязателен")
    return sandbox_request(
        "/download",
        {"url": url.strip(), "task_id": task_id},
        timeout=45,
    )
