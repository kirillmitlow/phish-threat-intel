import json
import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from core.ai_client import ask_vlm

logger = logging.getLogger(__name__)

# Путь к файлу целевых брендов
DEFAULT_BRANDS_PATH = Path(__file__).resolve().parent.parent / "configs" / "target_brands.json"

_TARGET_BRANDS_CACHE: Optional[List[str]] = None

#Возвращает список целевых брендов из конфигурационного файла
def get_target_brands(brands_path: Optional[Path] = None) -> List[str]:
    global _TARGET_BRANDS_CACHE
    if _TARGET_BRANDS_CACHE is not None:
        return _TARGET_BRANDS_CACHE

    path = brands_path or DEFAULT_BRANDS_PATH
    if not path.exists():
        alt_path = path.parent.parent / "target_brands.json"
        if alt_path.exists():
            path = alt_path

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    _TARGET_BRANDS_CACHE = data
                    return _TARGET_BRANDS_CACHE
        except Exception as e:
            logger.warning("Не удалось загрузить целевые бренды из %s: %s", path, e)

    _TARGET_BRANDS_CACHE = []
    return _TARGET_BRANDS_CACHE

#lowercase, удаление лишнего
def _normalize_name(name: str) -> str:
    cleaned = re.sub(r"\(.*?\)", "", name)
    cleaned = re.sub(r"[^\w\s-]", "", cleaned, flags=re.UNICODE)
    return cleaned.strip().lower()


def resolve_brand(raw_name: Optional[str], target_brands: Optional[List[str]] = None) -> Tuple[Optional[str], bool]:
    if not raw_name or str(raw_name).strip().lower() in ("null", "none", "", "no", "нет"):
        return None, False

    cleaned_raw = str(raw_name).strip()
    raw_lower = cleaned_raw.lower()

    targets = target_brands if target_brands is not None else get_target_brands()
    if not targets:
        return cleaned_raw, False

    norm_raw = _normalize_name(cleaned_raw)

    # 1. Прямое совпадение с целевыми брендами (без учёта регистра)
    for target in targets:
        if raw_lower == target.lower():
            return target, True

    # 2. Совпадение по нормализованному имени без скобок
    for target in targets:
        norm_target = _normalize_name(target)
        if norm_raw and norm_target and norm_raw == norm_target:
            return target, True

    # 3. Вхождение основного токена (например "PayPal" в "PayPal Inc.")
    for target in targets:
        norm_target = _normalize_name(target)
        if norm_target and len(norm_target) >= 3:
            pattern = r"\b" + re.escape(norm_target) + r"\b"
            if re.search(pattern, norm_raw):
                return target, True

    # 4. Если в списке не найден — это бренд вне списка (open-set)
    return cleaned_raw, False


def build_brand_prompt(target_brands: Optional[List[str]] = None) -> str:
    targets = target_brands if target_brands is not None else get_target_brands()
    sample_targets = ", ".join(targets[:60]) if targets else "Сбер, Т-Банк, ВТБ, Госуслуги, Apple ID, PayPal, Amazon, Microsoft Outlook"

    return f"""Ты — эксперт по анализу веб-страниц и извлечению признаков для Threat Intelligence.
Посмотри на скриншот веб-страницы и определи, какой бренд/сервис/организацию она имитирует (по логотипу, названиям, цветовой гамме, форме входа или заголовкам).

В приоритете проверь совпадение со списком отслеживаемых целевых брендов (фрагмент):
[{sample_targets}...]

Инструкция:
1. Если страница имитирует бренд из списка отслеживаемых — укажи его точное название.
2. Система работает в режиме OPEN-SET: если страница имитирует известный бренд, которого НЕТ в списке выше (например, Steam, Telegram, Booking и т.д.), укажи его фактическое общепринятое название.
3. Если страница нейтральная, не содержит признаков имитации конкретного бренда (доменный паркинг, пустая заглушка, generic-форма) — укажи "brand": null.
4. Не делай вывод, скам это или легитимный сайт — твоя задача ТОЛЬКО определить бренд и факты на скриншоте.

Ответь СТРОГО в формате JSON без markdown-разметки:
{{"brand": "название бренда или null",
 "confidence": 0.0-1.0,
 "evidence": "короткое перечисление фактов: логотип, элементы дизайна, текст"}}
"""


def _parse_brand_response(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            raw_brand = data.get("brand")
            canonical_brand, in_target = resolve_brand(raw_brand)
            return {
                "brand": canonical_brand,
                "in_target": in_target,
                "confidence": float(data.get("confidence", 0.0)),
                "evidence": data.get("evidence", ""),
            }
        except Exception as e:
            logger.debug("Ошибка разбора JSON ответа VLM: %s", e)

    canonical_brand, in_target = resolve_brand(text.strip()[:100])
    return {
        "brand": canonical_brand,
        "in_target": in_target,
        "confidence": 0.0,
        "evidence": text.strip()[:500]
    }


def detect_brand(image_path: str, question: Optional[str] = None) -> dict:
    prompt = question or build_brand_prompt()
    try:
        text = ask_vlm(prompt=prompt, image_path=image_path)
    except Exception as e:
        return {"brand": None, "in_target": False, "confidence": 0.0, "evidence": f"vlm error: {e}"}

    result = _parse_brand_response(text)
    if not result.get("brand"):
        result["brand"] = None
        result["in_target"] = False
    return result


def brand_fingerprint(brand: str, domain: Optional[str], confidence: float, in_target: bool = False) -> dict:
    fp = {
        "kind": "brand_feature",
        "brand": brand,
        "in_target": in_target,
        "domain_mismatch": bool(domain and brand),
        "confidence": confidence,
    }
    if domain:
        fp["domain"] = domain
    return fp