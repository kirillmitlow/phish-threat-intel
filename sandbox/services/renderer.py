import asyncio
import re
import uuid
from pathlib import Path
from typing import List

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

ARTIFACTS_DIR = Path("/app/data/artifacts")


def _extract_forms_and_suspicious(html: str) -> dict:
    result: dict = {
        "forms": [],
        "iframes": 0,
        "external_scripts": [],
        "obfuscation_flags": {},
        "password_fields": 0,
        "hidden_inputs": 0,
    }

    # Формы: <form ...> с атрибутами action/method
    for tag in re.finditer(r"<form\b[^>]*>", html, re.IGNORECASE):
        t = tag.group(0)
        action_m = re.search(r'action\s*=\s*["\']([^"\']*)["\']', t, re.IGNORECASE)
        method_m = re.search(r'method\s*=\s*["\'](\w+)["\']', t, re.IGNORECASE)
        result["forms"].append({
            "action": action_m.group(1) if action_m else None,
            "method": method_m.group(1) if method_m else "get",
        })

    result["password_fields"] = len(re.findall(
        r'<input\b[^>]*type\s*=\s*["\']password["\']', html, re.IGNORECASE))
    result["hidden_inputs"] = len(re.findall(
        r'<input\b[^>]*type\s*=\s*["\']hidden["\']', html, re.IGNORECASE))
    result["external_scripts"] = re.findall(
        r'<script\b[^>]*src\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
    result["iframes"] = len(re.findall(r"<iframe\b", html, re.IGNORECASE))

    # Признаки обфускации
    result["obfuscation_flags"] = {
        "has_base64_blob": bool(re.search(r"base64,\s*[A-Za-z0-9+/=]{50,}", html)),
        "has_atob": "atob(" in html,
        "has_eval": bool(re.search(r"\beval\s*\(", html, re.IGNORECASE)),
        "has_document_write": "document.write" in html,
        "has_charcode": "charcode" in html.lower(),
    }
    return result


async def _abort_heavy(route) -> None:
    url = route.request.url.lower()
    heavy_suffixes = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
                      ".mp4", ".webm", ".mp3", ".wav", ".woff", ".woff2", ".ttf")
    if url.split("?")[0].endswith(heavy_suffixes):
        try:
            await route.abort()
        except Exception:
            pass
    else:
        try:
            await route.continue_()
        except Exception:
            pass


async def _render_async(payload: dict) -> dict:
    if async_playwright is None:
        return {"ok": False, "error": "playwright не установлен"}

    url = payload.get("url")
    html = payload.get("html")
    want_shot = payload.get("screenshot", True)
    max_bytes = payload.get("max_bytes", 2_000_000)

    # Санитизация подпапки артефактов (от ../ и мусора), как в распаковщике
    raw_task = payload.get("task_id") or ""
    safe_task = "".join(c for c in raw_task if c.isalnum() or c in "-_")
    task_id = safe_task or uuid.uuid4().hex

    task_dir = ARTIFACTS_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    if not url:
        tmp_html = task_dir / "input.html"
        try:
            tmp_html.write_text(html or "", encoding="utf-8")
        except Exception:
            pass

    redirects: List[str] = []
    final_url = url or "local_html"
    shot_path = ""
    dom_snippet = ""
    suspicious: dict = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            await page.route("**/*", _abort_heavy)

            # Собираем редирект-цепочку через события (в playwright нет response.history)
            seen_responses: List[str] = []

            def _on_response(resp):
                seen_responses.append(resp.url)

            page.on("response", _on_response)

            if html and not url:
                try:
                    await page.set_content(html, wait_until="domcontentloaded", timeout=5000)
                except Exception:
                    try:
                        await page.set_content(html, wait_until="commit", timeout=3000)
                    except Exception:
                        pass
                redirects = ["local_html"]
                final_url = "local_html"
            else:
                try:
                    response = await page.goto(
                        url, timeout=10000, wait_until="domcontentloaded")
                except Exception:
                    try:
                        response = await page.goto(
                            url, timeout=5000, wait_until="commit")
                    except Exception:
                        response = None

                if response is not None:
                    final_url = response.url
                    redirects = []
                    for u in seen_responses:
                        if u not in redirects:
                            redirects.append(u)
                    if final_url not in redirects:
                        redirects.append(final_url)
                else:
                    redirects = [url]

            if want_shot:
                try:
                    fname = task_dir / f"{uuid.uuid4().hex}.png"
                    await page.screenshot(path=str(fname), full_page=True, timeout=5000)
                    shot_path = str(fname)
                except Exception:
                    pass

            try:
                dom_html = await page.content()
            except Exception:
                dom_html = html or ""
            dom_snippet = dom_html[:max_bytes]
            suspicious = _extract_forms_and_suspicious(dom_html)
            dom_file = task_dir / "dom.html"
            try:
                dom_file.write_text(dom_snippet, encoding="utf-8")
            except Exception:
                pass
        finally:
            await browser.close()

    return {
        "ok": True,
        "final_url": final_url,
        "redirect_chain": redirects,
        "screenshot": shot_path,
        "dom_snippet_len": len(dom_snippet),
        "suspicious": suspicious,
    }


def render(payload: dict) -> dict:
    return asyncio.run(_render_async(payload))