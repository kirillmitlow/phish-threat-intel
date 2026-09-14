import shlex
import subprocess
import time

# Разрешённые команды для разбора артефактов (безопасная работа с файлами)
ALLOWED_COMMANDS = {
    "strings": True,
    "file": True,
    "grep": True,
    "xxd": True,
    "hexdump": True,
    "base64": True,
    "head": True,
    "tail": True,
    "cat": True,
    "wc": True,
    "ls": True,
    "tesseract": True,  # OCR (если установлен)
    "exiftool": True,   # метаданные (если установлен)
}

# Максимальный размер возвращаемого вывода
MAX_OUTPUT_CHARS = 50_000
DEFAULT_TIMEOUT = 15


def _is_allowed(cmd: str) -> tuple[bool, str]:
    try:
        parts = shlex.split(cmd)
    except ValueError as e:
        return False, f"некорректная команда: {e}"

    if not parts:
        return False, "пустая команда"
    base = parts[0]
    if base not in ALLOWED_COMMANDS:
        return False, f"команда '{base}' не разрешена. Доступны: {', '.join(sorted(ALLOWED_COMMANDS))}"

    # Запрещаем разделители и операторы, чтобы нельзя было выполнить вторую команду
    banned = [";", "&&", "||", "`", "${", "|"]
    for b in banned:
        if b in cmd:
            return False, f"запрещён символ/оператор '{b}'"
    return True, ""


def run_command(payload: dict) -> dict:
    command = payload.get("command", "")
    timeout = min(int(payload.get("timeout", DEFAULT_TIMEOUT)), 60)

    if not command or not command.strip():
        return {"ok": False, "error": "command обязателен"}

    allowed, reason = _is_allowed(command)
    if not allowed:
        return {"ok": False, "error": reason}

    try:
        start = time.monotonic()
        proc = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = round(time.monotonic() - start, 2)
        stdout = proc.stdout[:MAX_OUTPUT_CHARS]
        stderr = proc.stderr[:MAX_OUTPUT_CHARS]
        return {
            "ok": True,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "elapsed_s": elapsed,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"TIMEOUT после {timeout}s"}
    except FileNotFoundError as e:
        return {"ok": False, "error": f"команда не найдена: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"ошибка выполнения: {e}"}