from langchain_core.tools import tool

from .http_proxy import sandbox_request


@tool
def extract_document(file_path: str) -> dict:
    """Извлекает текст и ссылки из документа (PDF, DOCX, XLSX, PPTX, EML).

    Аргументы:
        file_path: путь к документу на общем томе (/app/data/...).

    Возвращает: markdown-содержимое, найденные URL, метаданные.
    """
    if not file_path:
        raise ValueError("file_path обязателен")
    return sandbox_request("/extract_document", {"file_path": file_path}, timeout=45)