from typing import List, Dict, Any
from langchain_core.tools import BaseTool, tool

from tools.collector import (
    render_page,
    extract_qr,
    unpack_attachment,
    eval_js,
    extract_links,
    run_shell,
    extract_document,
    render_pdf_to_png,
    download_file,
)
from tools.analysts import analyze_snippet, analyze_screenshot, hash_artifacts

# Реестр инструментов агента (имя -> @tool-функция). Один общий пул для всех агентов.
AVAILABLE_TOOLS: Dict[str, Any] = {
    # Разведка / сбор (исполняется в песочнице)
    "render_page": render_page,
    "extract_links": extract_links,
    "download_file": download_file,
    "unpack_attachment": unpack_attachment,
    "extract_qr": extract_qr,
    "eval_js": eval_js,
    "run_shell": run_shell,
    # Работа с документами (исполняется в песочнице)
    "extract_document": extract_document,
    "render_pdf_to_png": render_pdf_to_png,
    # Анализ / артефакты (исполняется в агенте)
    "analyze_snippet": analyze_snippet,
    "analyze_screenshot": analyze_screenshot,
    "hash_artifacts": hash_artifacts,
}


def register_tool(name: str, tool_instance: Any):
    AVAILABLE_TOOLS[name] = tool_instance


def get_tool(tool_name: str) -> Any:
    if tool_name not in AVAILABLE_TOOLS:
        raise KeyError(
            f"Инструмент '{tool_name}' не найден в реестре AVAILABLE_TOOLS. "
            f"Доступны: {list(AVAILABLE_TOOLS.keys())}"
        )
    return AVAILABLE_TOOLS[tool_name]


def get_tools(tool_names: List[str]) -> List[Any]:
    return [get_tool(name) for name in tool_names]


__all__ = [
    "BaseTool",
    "tool",
    "AVAILABLE_TOOLS",
    "register_tool",
    "get_tool",
    "get_tools",
]