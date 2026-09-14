"""
Пакет prompts: загрузка и управление шаблонами промптов в формате Markdown (.md).
"""
import os

PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def load_prompt(prompt_name: str) -> str:
    """
    Загружает текст промпта из .md файла.
    
    :param prompt_name: Имя файла (например, 'react_system' или 'react_system.md')
    :return: Текст промпта
    """
    if not prompt_name.endswith(".md"):
        prompt_name += ".md"
        
    filepath = os.path.join(PROMPTS_DIR, prompt_name)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Файл промпта не найден: {filepath}")
        
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


__all__ = ["load_prompt", "PROMPTS_DIR"]
