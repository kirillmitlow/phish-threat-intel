from langchain_core.tools import tool

from .http_proxy import sandbox_request


@tool
def run_shell(command: str, timeout: int = 15) -> dict:
    """Выполняет консольную команду в изолированной песочнице (грязная зона).

    Позволяет разбирать файлы: cat, strings, file, grep, xxd, hexdump, head, tail, base64, wc, ls.
    Только одиночные команды! Операторы '&&', '||', '|', ';', '>', '<', '$' и утилита 'curl' запрещены.

    Аргументы:
        command: одиночная команда для выполнения (например 'strings file.bin').
        timeout: макс. время выполнения, сек (по умолчанию 15).

    Возвращает: stdout, stderr, exit_code.
    """
    if not command or not command.strip():
        raise ValueError("command обязателен")
    return sandbox_request(
        "/run_shell",
        {"command": command, "timeout": timeout},
        timeout=timeout + 5,
    )