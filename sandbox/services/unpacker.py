import shutil
import tarfile
import zipfile
from pathlib import Path

ARTIFACTS_DIR = Path("/app/data/artifacts")
MAX_TOTAL_BYTES = 200 * 1024 * 1024  # 200 MB суммарно
MAX_FILES = 2048


def _safe_join(root: Path, member_name: str) -> Path:
    target = (root / member_name).resolve()
    root_resolved = root.resolve()
    if not target.is_relative_to(root_resolved):
        raise RuntimeError(f"path traversal: {member_name!r}")
    return target


def _check_zip(zf: zipfile.ZipFile) -> None:
    total = 0
    n = 0
    for info in zf.infolist():
        total += info.file_size
        n += 1
        if total > MAX_TOTAL_BYTES:
            raise RuntimeError("архив превышает лимит размера (200 MB)")
        if n > MAX_FILES:
            raise RuntimeError("слишком много файлов в архиве")


def _unpack_zip(archive: Path, target: Path) -> dict:
    with zipfile.ZipFile(archive) as zf:
        _check_zip(zf)
        extracted = []
        for info in zf.infolist():
            # Пропускаем директории и пустые имена
            if info.is_dir() or not info.filename:
                continue
            dest = _safe_join(target, info.filename)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
            extracted.append(str(dest.relative_to(target)))
    return {"ok": True, "files": extracted, "count": len(extracted)}


def _unpack_tar(archive: Path, target: Path) -> dict:
    extracted = []
    with tarfile.open(archive) as tf:
        members = tf.getmembers()
        total = sum(m.size for m in members if m.isfile())
        if total > MAX_TOTAL_BYTES:
            raise RuntimeError("архив превышает лимит размера (200 MB)")
        if len(members) > MAX_FILES:
            raise RuntimeError("слишком много файлов в архиве")
        for member in members:
            if not member.isfile() or not member.name:
                continue
            dest = _safe_join(target, member.name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with open(dest, "wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
            extracted.append(str(dest.relative_to(target)))
    return {"ok": True, "files": extracted, "count": len(extracted)}


def unpack(payload: dict) -> dict:
    archive_path = payload.get("archive_path")
    task_id = payload.get("task_id")
    if not archive_path or not task_id:
        return {"ok": False, "error": "нужны archive_path и task_id"}

    archive = Path(archive_path)
    if not archive.is_absolute():
        archive = ARTIFACTS_DIR / archive
    if not archive.exists():
        return {"ok": False, "error": f"архив не найден: {archive}"}

    safe_task_id = "".join(c for c in task_id if c.isalnum() or c in "-_")
    target = (ARTIFACTS_DIR / safe_task_id).resolve()
    if not target.is_relative_to(ARTIFACTS_DIR.resolve()):
        return {"ok": False, "error": "некорректный task_id"}
    target.mkdir(parents=True, exist_ok=True)

    if str(archive).lower().endswith(".zip"):
        return _unpack_zip(archive, target)
    if archive.suffix in (".tar", ".tgz", ".gz", ".bz2", ".xz"):
        return _unpack_tar(archive, target)
    return {"ok": False, "error": f"неподдерживаемый формат: {archive.suffix}"}