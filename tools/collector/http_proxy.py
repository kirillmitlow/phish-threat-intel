import os

import httpx

SANDBOX_URL = os.getenv("SANDBOX_URL", "http://sandbox_service:8400").rstrip("/")
_TIMEOUT = float(os.getenv("SANDBOX_TIMEOUT", "60"))


def _detail_from_response(r: httpx.Response) -> str:
    try:
        body = r.json()
        if isinstance(body, dict):
            return body.get("detail") or body.get("error") or str(body)[:500]
    except Exception:
        pass
    return f"HTTP {r.status_code}"


def sandbox_request(endpoint: str, payload: dict, timeout: float = _TIMEOUT) -> dict:
    url = f"{SANDBOX_URL}{endpoint}"
    try:
        r = httpx.post(url, json=payload, timeout=timeout)
    except httpx.TimeoutException:
        return {"ok": False, "error": f"таймаут песочницы ({timeout}с) на {endpoint}"}
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"песочница недоступна: {e.__class__.__name__}"}

    if r.status_code >= 400:
        return {"ok": False, "error": _detail_from_response(r),
                "http_status": r.status_code}
    try:
        return r.json()
    except Exception:
        return {"ok": False, "error": "песочница вернула не-JSON ответ"}


def sandbox_available() -> bool:
    try:
        r = httpx.get(f"{SANDBOX_URL}/ping", timeout=5)
        return r.status_code == 200
    except Exception:
        return False
