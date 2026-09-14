from langchain_core.tools import tool

from .http_proxy import sandbox_request


@tool
def extract_qr(image_path: str) -> dict:
    """Декодирует QR-коды из изображения внутри изолированной песочницы.

    Аргументы:
        image_path: путь к изображению (на общем томе /app/data).

    Возвращает список расшифрованных QR-контентов (текст/URL).
    """
    if not image_path:
        raise ValueError("image_path обязателен")
    return sandbox_request(
        "/extract_qr",
        {"image_path": image_path},
        timeout=30,
    )