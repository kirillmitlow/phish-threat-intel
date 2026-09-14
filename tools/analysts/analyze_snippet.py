from langchain_core.tools import tool

from core.ai_client import ask_llm


@tool
def analyze_snippet(snippet: str, question: str = "") -> str:
    """Разбирает фрагмент кода/текста вне контекста всей страницы через LLM.

    Полезно, когда из песочницы прилетел подозрительный фрагмент
    (обфусцированный JS, строка, кусок письма) и нужно понять,
    что он делает, отдельно от общего контекста.

    Аргументы:
        snippet: фрагмент текста или кода для разбора.
        question: конкретный вопрос про фрагмент (по умолчанию — общий разбор).

    Возвращает: объяснение модели.
    """
    if not snippet or not snippet.strip():
        raise ValueError("snippet обязателен")

    prompt = question or "Что это за фрагмент и что он делает? Объясни простыми словами."
    return ask_llm(prompt=f"{prompt}\n\nФрагмент:\n{snippet[:2000]}")