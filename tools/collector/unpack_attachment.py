from langchain_core.tools import tool

from .http_proxy import sandbox_request


@tool
def unpack_attachment(archive_path: str, task_id: str | None = None) -> dict:
    """Распаковывает архив/вложение в изолированной песочнице.

    Аргументы:
        archive_path: путь к архиву (на общем томе /app/data).
        task_id: подпапка для распакованных файлов (по умолчанию auto).

    Возвращает список извлечённых файлов. Защита от path traversal включена.
    """
    if not archive_path:
        raise ValueError("archive_path обязателен")
    return sandbox_request(
        "/unpack",
        {"archive_path": archive_path, "task_id": task_id},
        timeout=60,
    )