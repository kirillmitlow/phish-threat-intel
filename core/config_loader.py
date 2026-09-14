import os
import json
from typing import Any, Dict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIGS_DIR = os.path.join(BASE_DIR, "configs")
AGENTS_CONFIG_DIR = os.path.join(CONFIGS_DIR, "agents")


def load_json_config(file_path: str) -> Dict[str, Any]:
    if not os.path.isabs(file_path):
        file_path = os.path.join(BASE_DIR, file_path)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл конфигурации не найден: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_agent_config(agent_name_or_path: str) -> Dict[str, Any]:
    if agent_name_or_path.endswith(".json") and (os.path.isabs(agent_name_or_path) or "/" in agent_name_or_path or "\\" in agent_name_or_path):
        return load_json_config(agent_name_or_path)

    # Ищем в configs/agents/
    filename = agent_name_or_path if agent_name_or_path.endswith(".json") else f"{agent_name_or_path}.json"
    full_path = os.path.join(AGENTS_CONFIG_DIR, filename)

    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Конфигурация агента '{filename}' не найдена в {AGENTS_CONFIG_DIR}")

    return load_json_config(full_path)
