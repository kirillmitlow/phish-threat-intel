import hashlib
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool


def _hash_file(path: Path) -> dict:
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            md5.update(chunk)
            sha.update(chunk)
            size += len(chunk)
    return {
        "path": str(path),
        "size_bytes": size,
        "md5": md5.hexdigest(),
        "sha256": sha.hexdigest(),
    }


@tool
def hash_artifacts(paths: list[str], base_dir: Optional[str] = None) -> dict:
    """Считает md5/sha256 для артефактов (файлов), собранных по задаче.

    Это «отпечатки» файлов, по которым антиспам сможет узнавать похожие
    вложения/образцы.

    Аргументы:
        paths: список файлов (абсолютные пути или пути на томе /app/data).
        base_dir: опциональный базовый каталог, к которому относить пути.

    Возвращает для каждого файла: путь, размер, md5, sha256.
    """
    results = []
    errors = []

    for p in paths:
        path = Path(p)
        if base_dir:
            base = Path(base_dir)
            candidate = base / p if not path.is_absolute() else path
        else:
            candidate = path
        if not candidate.exists():
            errors.append({"path": p, "error": "файл не найден"})
            continue
        try:
            results.append(_hash_file(candidate))
        except Exception as e:
            errors.append({"path": p, "error": f"ошибка чтения: {e}"})

    return {
        "ok": True if results else False,
        "files": results,
        "count": len(results),
        "errors": errors,
    }