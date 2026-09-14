from langchain_core.tools import tool

from core.ai_client import ask_vlm


@tool
def analyze_screenshot(image_path: str, question: str = "") -> str:
    """Анализирует скриншот страницы через зрительную модель (VLM).

    Смотрит на картинку и отвечает: какой бренд имитируется (банк, почта,
    сервис), что на странице (форма логина, подозрительный дизайн, логотип),
    есть ли признаки обмана.

    Аргументы:
        image_path: путь к PNG-скриншоту (на общем томе /app/data).
        question: конкретный вопрос про картинку (по умолчанию — общий разбор).

    Возвращает: описание модели.
    """
    if not image_path:
        raise ValueError("image_path обязателен")

    prompt = question or (
        "Проанализируй скриншот подозрительной страницы. Какой бренд/сервис "
        "имитируется? Есть ли форма ввода логина/пароля и другие признаки "
        "фишинга? Ответь понятно на русском."
    )
    return ask_vlm(prompt=prompt, image_path=image_path)