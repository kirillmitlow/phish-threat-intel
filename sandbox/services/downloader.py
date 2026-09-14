import re
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

ARTIFACTS_DIR = Path("/app/data/artifacts")
MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB на файл
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
ALLOWED_SCHEMES = {"http", "https"}


def _safe_name(url: str) -> str:
    path = urlparse(url).path
    name = unquote(path.rsplit("/", 1)[-1]) if path else ""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:80].strip("._") or "download"
    return f"{uuid.uuid4().hex[:8]}_{name}"


def download(payload: dict) -> dict:
    url = (payload.get("url") or "").strip()
    task_id = payload.get("task_id") or uuid.uuid4().hex

    if not url:
        return {"ok": False, "error": "url обязателен"}

    scheme = urlparse(url).scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        return {"ok": False, "error": f"схема {scheme!r} запрещена (только http/https)"}

    safe_task_id = "".join(c for c in task_id if c.isalnum() or c in "-_")
    target_dir = (ARTIFACTS_DIR / safe_task_id).resolve()
    if not target_dir.is_relative_to(ARTIFACTS_DIR.resolve()):
        return {"ok": False, "error": "некорректный task_id"}
    target_dir.mkdir(parents=True, exist_ok=True)

    dest: Path | None = None
    size = 0
    final_url = url
    redirects: list[str] = []
    ctype = ""

    try:
        with httpx.Client(follow_redirects=True, timeout=30,
                          headers={"User-Agent": USER_AGENT}) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                final_url = str(resp.url)
                ctype = resp.headers.get("content-type", "")
                redirects = [str(h.url) for h in resp.history]

                dest = target_dir / _safe_name(final_url)
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=256 * 1024):
                        size += len(chunk)
                        if size > MAX_FILE_BYTES:
                            raise RuntimeError(
                                f"файл больше лимита {MAX_FILE_BYTES // (1024 * 1024)} MB")
                        f.write(chunk)
    except (httpx.HTTPError, RuntimeError) as e:
        if dest and dest.exists():
            dest.unlink(missing_ok=True)
        return {"ok": False, "error": f"download error: {e}"}

    return {
        "ok": True,
        "path": str(dest),
        "size": size,
        "final_url": final_url,
        "redirect_chain": redirects + [final_url],
        "content_type": ctype,
    }
