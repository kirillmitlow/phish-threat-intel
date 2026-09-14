import json
import uuid
from pathlib import Path

ARTIFACTS_DIR = Path("/app/data/artifacts")


def _text_from_file(path: Path) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as e:
        return f"[markitdown не установлен: {e}]"

    md = MarkItDown()
    result = md.convert(str(path))
    return result.text_content


def extract_document(payload: dict) -> dict:
    file_path = payload.get("file_path")
    if not file_path:
        return {"ok": False, "error": "file_path обязателен"}

    p = Path(file_path)
    if not p.is_absolute():
        p = ARTIFACTS_DIR / p
    if not p.exists():
        return {"ok": False, "error": f"файл не найден: {p}"}

    try:
        text = _text_from_file(p)
    except Exception as e:
        return {"ok": False, "error": f"не удалось разобрать документ: {e}"}

    # Вытаскиваем ссылки из Markdown
    import re
    urls = re.findall(r"https?://[^\s)\]}]+", text)
    # Убираем дубликаты
    seen = set()
    unique_urls = []
    for u in urls:
        u = u.rstrip(".,;:!?”")
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    return {
        "ok": True,
        "filename": p.name,
        "text_length": len(text),
        "markdown": text,
        "urls": unique_urls,
        "url_count": len(unique_urls),
    }


def render_pdf_to_png(payload: dict) -> dict:
    import pymupdf as fit  # PyMuPDF (fitz устарел)

    file_path = payload.get("file_path")
    task_id = payload.get("task_id") or uuid.uuid4().hex
    max_pages = int(payload.get("max_pages", 5))

    if not file_path:
        return {"ok": False, "error": "file_path обязателен"}

    p = Path(file_path)
    if not p.is_absolute():
        p = ARTIFACTS_DIR / p
    if not p.exists():
        return {"ok": False, "error": f"файл не найден: {p}"}

    task_dir = ARTIFACTS_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = fit.open(str(p))
        total_pages = doc.page_count
        pages = []
        limit = min(total_pages, max_pages)
        for i in range(limit):
            pix = doc[i].get_pixmap(dpi=120)
            out = task_dir / f"page_{i + 1:03d}.png"
            pix.save(str(out))
            pages.append(str(out))
        doc.close()
        return {"ok": True, "pages": pages, "count": len(pages),
                "total_pages": total_pages}
    except Exception as e:
        return {"ok": False, "error": f"не удалось отрендерить PDF: {e}"}