import hashlib
import io
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def extract_favicon_urls(html: str, base_url: str) -> List[str]:
    urls: List[str] = []

    # Поиск <link ... rel="(shortcut )?icon" ... href="...">
    patterns = [
        r'<link\b[^>]*\brel\s*=\s*["\'](?:shortcut\s+)?icon["\'][^>]*\bhref\s*=\s*["\']([^"\']+)["\']',
        r'<link\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\'][^>]*\brel\s*=\s*["\'](?:shortcut\s+)?icon["\']',
        r'<link\b[^>]*\brel\s*=\s*["\']apple-touch-icon["\'][^>]*\bhref\s*=\s*["\']([^"\']+)["\']',
    ]

    for pat in patterns:
        for m in re.finditer(pat, html, re.IGNORECASE):
            raw_href = m.group(1).strip()
            if raw_href and not raw_href.startswith("data:"):
                full_url = urljoin(base_url, raw_href)
                if full_url not in urls:
                    urls.append(full_url)

    # Fallback на /favicon.ico в корне домена
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme and parsed.netloc:
            root_favicon = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
            if root_favicon not in urls:
                urls.append(root_favicon)

    return urls


def compute_dhash(image_bytes: bytes, hash_size: int = 8) -> Optional[str]:
    if not _HAS_PIL or not image_bytes:
        return None

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Преобразуем в градации серого и уменьшаем до (hash_size + 1, hash_size)
            img = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            pixels = list(img.get_flattened_data()) if hasattr(img, "get_flattened_data") else list(img.getdata())

            diff = []
            for row in range(hash_size):
                row_start = row * (hash_size + 1)
                for col in range(hash_size):
                    left = pixels[row_start + col]
                    right = pixels[row_start + col + 1]
                    diff.append(1 if left > right else 0)

            # Перевод битов в hex
            decimal_val = 0
            for index, bit in enumerate(diff):
                if bit:
                    decimal_val |= 1 << index
            return f"{decimal_val:016x}"
    except Exception:
        return None


def dhash_distance(hash1: str, hash2: str) -> int:
    if not hash1 or not hash2 or len(hash1) != 16 or len(hash2) != 16:
        return 64
    val1 = int(hash1, 16)
    val2 = int(hash2, 16)
    return bin(val1 ^ val2).count("1")


def analyze_favicon_data(image_bytes: bytes) -> dict:
    if not image_bytes:
        return {"md5": None, "sha256": None, "dhash": None}

    md5_hash = hashlib.md5(image_bytes).hexdigest()
    sha256_hash = hashlib.sha256(image_bytes).hexdigest()
    dhash = compute_dhash(image_bytes)

    return {
        "md5": md5_hash,
        "sha256": sha256_hash,
        "dhash": dhash,
        "size_bytes": len(image_bytes),
    }
