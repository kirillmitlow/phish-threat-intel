from langchain_core.tools import tool

from .http_proxy import sandbox_request


@tool
def render_pdf_to_png(file_path: str, max_pages: int = 5, task_id: str | None = None) -> dict:
    """Рендерит страницы PDF в PNG-картинки внутри песочницы.

    Аргументы:
        file_path: путь к PDF (на общем томе /app/data).
        max_pages: макс. число страниц (по умолчанию 5).
        task_id: подпапка для PNG-файлов.

    Возвращает: список путей к PNG — их можно скормить analyze_screenshot для VLM.
    """
    if not file_path:
        raise ValueError("file_path обязателен")
    return sandbox_request(
        "/render_pdf",
        {"file_path": file_path, "max_pages": max_pages, "task_id": task_id},
        timeout=60,
    )