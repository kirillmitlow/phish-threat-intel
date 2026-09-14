import asyncio
import re

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


async def _run_js(payload: dict) -> dict:
    if async_playwright is None:
        return {"ok": False, "error": "playwright не установлен"}

    code = payload.get("code", "")
    timeout = int(payload.get("timeout", 10))
    extract_urls = payload.get("extract_urls", True)

    if not code or not code.strip():
        return {"ok": False, "error": "code обязателен"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            await page.set_content("<html><body></body></html>")
            try:
                result = await asyncio.wait_for(
                    page.evaluate(f"(() => {{ {code} }})()"),
                    timeout=timeout
                )
            except Exception as e:
                return {"ok": False, "error": f"js_error: {e.__class__.__name__}: {e}"}
        finally:
            await browser.close()

    found_urls: list = []
    if extract_urls and isinstance(result, (str, bytes)):
        text = result if isinstance(result, str) else result.decode("utf-8", "replace")
        found_urls = re.findall(r'https?://[^\s"\'<>]+', text)

    return {"ok": True, "result": str(result), "found_urls": found_urls}


def run_js(payload: dict) -> dict:
    return asyncio.run(_run_js(payload))