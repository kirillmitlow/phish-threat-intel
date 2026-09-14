import hashlib
import os
import re
from pathlib import Path
from typing import List, Optional

from core.brand_detector import detect_brand
from core import storage
from core import dom_analyzer
from core import obfuscation_detector
from core import favicon_analyzer
from core import campaign_cluster
from tools.collector.http_proxy import sandbox_request

ARTIFACTS_DIR = Path("/app/data/artifacts")


# ---------------------------------------------------------------- helpers
def _hash_file(path: Path) -> tuple:
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            md5.update(chunk)
            sha.update(chunk)
    return md5.hexdigest(), sha.hexdigest()


def _domain_of(url: str) -> str:
    m = re.search(r"https?://([^/]+)", url)
    return m.group(1) if m else url


def _extract_domains(urls: List[str]) -> List[str]:
    seen = set()
    out = []
    for u in urls:
        d = _domain_of(u)
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def read_sample_html(task_id: str, input_type: str, input_ref: str) -> str:
    dom_file = ARTIFACTS_DIR / task_id / "dom.html"
    input_file = ARTIFACTS_DIR / task_id / "input.html"
    if dom_file.exists():
        return dom_file.read_text(encoding="utf-8", errors="replace")
    if input_file.exists():
        return input_file.read_text(encoding="utf-8", errors="replace")
    if input_type == "html":
        return input_ref
    if input_type == "file" and input_ref.lower().endswith(".html"):
        p_file = Path(input_ref)
        if p_file.exists():
            return p_file.read_text(encoding="utf-8", errors="replace")
    return ""


# ---------------------------------------------------------------- step 1: collect
# Функции публичные: их переиспользует оркестратор агентов (core/orchestrator.py)
# как детерминированную подготовку стартовой точки.
def collect_url(conn, sample_id: int, url: str, task_id: str) -> dict:
    render = sandbox_request("/render", {"url": url, "screenshot": True, "task_id": task_id},
                             timeout=60)

    if not render.get("ok"):
        storage.add_url(conn, sample_id, url, kind="link", final_url=None)
        return {"ok": False, "error": render.get("error")}

    final = render.get("final_url") or url
    chain = render.get("redirect_chain") or []
    storage.add_url(conn, sample_id, url, kind="link", final_url=final,
                    redirect_chain=chain)

    # Скриншот
    shot = render.get("screenshot")
    if shot:
        md5, sha = _hash_file(Path(shot))
        storage.add_artifact(conn, sample_id, "screenshot", shot, md5, sha,
                             {"source": url})

    # Признаки фишинга из DOM
    suspicious = render.get("suspicious") or {}
    forms = suspicious.get("forms") or []
    if forms:
        storage.add_finding(conn, sample_id, "credential_form",
                            {"forms": forms, "url": url}, "high")
    if suspicious.get("password_fields", 0) > 0:
        storage.add_finding(conn, sample_id, "credential_form",
                            {"password_fields": suspicious["password_fields"], "url": url},
                            "high")
    if suspicious.get("iframes", 0) > 0:
        storage.add_finding(conn, sample_id, "hidden_iframe",
                            {"iframes": suspicious["iframes"], "url": final}, "medium")
    obf = suspicious.get("obfuscation_flags") or {}
    if any(obf.values()):
        storage.add_finding(conn, sample_id, "obfuscated_code",
                            {"flags": obf, "url": final}, "medium")

    # Ссылки из DOM (renderer сохранил dom.html в артефакты task_id)
    try:
        dom_path = f"{ARTIFACTS_DIR}/{task_id}/dom.html"
        if Path(dom_path).exists():
            links_res = sandbox_request(
                "/extract_links", {"html": None, "html_path": dom_path}, timeout=20)
            if links_res.get("ok"):
                for l in links_res.get("links", []):
                    storage.add_url(conn, sample_id, l["url"],
                                    kind=l.get("tag", "link"),
                                    source_artifact="dom.html")
    except Exception:
        pass

    return {"ok": True, "final_url": final, "redirect_chain": chain,
            "screenshot": shot, "suspicious": suspicious}


def collect_html(conn, sample_id: int, html: str, task_id: str) -> dict:
    render = sandbox_request("/render", {"html": html, "screenshot": True,
                                         "task_id": task_id}, timeout=60)
    if not render.get("ok"):
        return {"ok": False, "error": render.get("error")}

    suspicious = render.get("suspicious") or {}
    forms = suspicious.get("forms") or []
    if forms:
        storage.add_finding(conn, sample_id, "credential_form", {"forms": forms}, "high")
    if suspicious.get("password_fields", 0) > 0:
        storage.add_finding(conn, sample_id, "credential_form",
                            {"password_fields": suspicious["password_fields"]}, "high")
    obf = suspicious.get("obfuscation_flags") or {}
    if any(obf.values()):
        storage.add_finding(conn, sample_id, "obfuscated_code", {"flags": obf}, "medium")

    # Сохраняем HTML как артефакт
    html_path = ARTIFACTS_DIR / task_id / "input.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    md5, sha = _hash_file(html_path)
    storage.add_artifact(conn, sample_id, "html", str(html_path), md5, sha,
                         {"source": "input_html"})

    # Ссылки из HTML напрямую
    try:
        links_res = sandbox_request("/extract_links", {"html": html, "html_path": None},
                                    timeout=20)
        if links_res.get("ok"):
            for l in links_res.get("links", []):
                storage.add_url(conn, sample_id, l["url"], kind=l.get("tag", "link"),
                                source_artifact="input.html")
    except Exception:
        pass

    shot = render.get("screenshot")
    if shot:
        md5, sha = _hash_file(Path(shot))
        storage.add_artifact(conn, sample_id, "screenshot", shot, md5, sha,
                             {"source": "html"})

    return {"ok": True, "screenshot": shot, "suspicious": suspicious}


def collect_file(conn, sample_id: int, file_path: str, task_id: str) -> dict:
    p = Path(file_path)
    if not p.exists():
        return {"ok": False, "error": f"файл не найден: {p}"}

    md5, sha = _hash_file(p)
    storage.add_artifact(conn, sample_id, "attachment", str(p), md5, sha,
                         {"size": p.stat().st_size})

    suffix = p.suffix.lower()
    results = {"ok": True}

    # HTML-файл — рендерим как страницу (вложения-страницы из фишинга)
    if suffix == ".html":
        html = p.read_text(encoding="utf-8", errors="replace")
        html_render = sandbox_request(
            "/render", {"html": html, "screenshot": True, "task_id": task_id},
            timeout=60)
        if html_render.get("ok"):
            suspicious = html_render.get("suspicious") or {}
            if suspicious.get("forms"):
                storage.add_finding(conn, sample_id, "credential_form",
                                    {"forms": suspicious["forms"]}, "high")
            if suspicious.get("password_fields", 0) > 0:
                storage.add_finding(conn, sample_id, "credential_form",
                                    {"password_fields": suspicious["password_fields"]},
                                    "high")
            shot = html_render.get("screenshot")
            if shot:
                smd5, ssha = _hash_file(Path(shot))
                storage.add_artifact(conn, sample_id, "screenshot", shot, smd5, ssha,
                                     {"source": str(p)})
            # Ссылки из HTML
            links_res = sandbox_request(
                "/extract_links", {"html": html, "html_path": None}, timeout=20)
            if links_res.get("ok"):
                for l in links_res.get("links", []):
                    storage.add_url(conn, sample_id, l["url"],
                                    kind=l.get("tag", "link"), source_artifact=str(p))
            results["html_rendered"] = True
        else:
            results["html_render_error"] = html_render.get("error")
        return results

    # Документ (PDF/Office/письмо)
    if suffix in (".pdf", ".docx", ".xlsx", ".pptx", ".eml", ".txt"):
        try:
            doc = sandbox_request("/extract_document", {"file_path": str(p)}, timeout=60)
            if doc.get("ok"):
                md_text = doc.get("markdown", "")
                for u in doc.get("urls", []):
                    storage.add_url(conn, sample_id, u, kind="document_link",
                                    source_artifact=str(p))
                html_path = ARTIFACTS_DIR / task_id / "doc_text.md"
                html_path.parent.mkdir(parents=True, exist_ok=True)
                html_path.write_text(md_text, encoding="utf-8")
                dmd5, dsha = _hash_file(html_path)
                storage.add_artifact(conn, sample_id, "document", str(html_path),
                                     dmd5, dsha, {"source": str(p), "urls": doc["urls"]})
                results["markdown"] = md_text[:500]
            # PDF → PNG для VLM
            if suffix == ".pdf":
                pdf_png = sandbox_request("/render_pdf", {"file_path": str(p),
                                                          "task_id": task_id}, timeout=60)
                if pdf_png.get("ok"):
                    for page in pdf_png.get("pages", []):
                        storage.add_artifact(conn, sample_id, "pdf_png", page,
                                             None, None, {"source": str(p)})
                    results["pdf_pages"] = pdf_png.get("pages", [])
        except Exception as e:
            results["doc_error"] = str(e)

    # Картинка → QR
    if suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        try:
            qr = sandbox_request("/extract_qr", {"image_path": str(p)}, timeout=30)
            if qr.get("ok"):
                qr_count = qr.get("qr_count", 0)
                if qr_count > 0:
                    for r in qr.get("results", []):
                        storage.add_url(conn, sample_id, r.get("content", ""), kind="qr",
                                        source_artifact=str(p))
                        if r.get("normalized"):
                            stage = r.get("normalization_stage", "filter")
                            storage.add_finding(conn, sample_id, "qr_obfuscation",
                                                {"technique": "noise_filtering", "stage": stage},
                                                severity="high")
                            storage.add_signature(conn, sample_id, "reason_code", f"QR_OBFUSCATION_{stage.upper()}")

                    storage.add_finding(conn, sample_id, "qr_phish",
                                        {"qr_count": qr_count, "results": qr.get("results")},
                                        severity="high")
                    storage.add_signature(conn, sample_id, "reason_code", "QR_PHISHING")
                results["qr_count"] = qr_count
        except Exception as e:
            results["qr_error"] = str(e)

    # Архив → распаковка
    if suffix in (".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz"):
        try:
            unpack = sandbox_request("/unpack", {"archive_path": str(p), "task_id": task_id},
                                     timeout=60)
            if unpack.get("ok"):
                results["unpacked"] = unpack.get("files", [])
                for f in unpack.get("files", []):
                    fp = ARTIFACTS_DIR / task_id / f
                    if fp.exists():
                        fmd5, fsha = _hash_file(fp)
                        storage.add_artifact(conn, sample_id, "unpacked", str(fp),
                                             fmd5, fsha, {"source": str(p)})
        except Exception as e:
            results["unpack_error"] = str(e)

    return results


def analyze_brand(conn, sample_id: int, screenshots: List[str], domains: List[str]) -> None:
    if not screenshots:
        return
    shot = screenshots[0]
    det = detect_brand(shot)
    brand_name = det.get("brand")
    if brand_name:
        in_target = det.get("in_target", False)
        confidence = det.get("confidence", 0.5)
        evidence = det.get("evidence", "")

        storage.add_brand(conn, sample_id, brand_name, confidence,
                          method="vlm", evidence=evidence, in_target=in_target)

        # Brand fingerprint: связка бренд + домен-несоответствие
        domain = domains[0] if domains else None
        # Простая эвристика несовпадения: если домен не содержит бренд
        clean_brand_slug = re.sub(r"[^\w]", "", brand_name.lower())
        mismatch = bool(domain) and bool(clean_brand_slug) and clean_brand_slug not in domain.lower()

        storage.add_signature(conn, sample_id, "brand_feature",
                              f"{brand_name}|{domain or ''}",
                              {"domain_mismatch": mismatch,
                               "in_target": in_target,
                               "confidence": confidence})

        if mismatch:
            storage.add_finding(conn, sample_id, "brand_impersonation",
                                evidence={"brand": brand_name,
                                          "domain": domain,
                                          "in_target": in_target,
                                          "evidence": evidence},
                                severity="high" if in_target else "medium")
            # Генерируем reason code признака для антиспама
            target_prefix = "TARGET_" if in_target else ""
            clean_code = re.sub(r"[^\w]", "_", brand_name.upper()).strip("_")
            storage.add_signature(conn, sample_id, "reason_code",
                                  f"BRAND_IMPERSONATION_{target_prefix}{clean_code}",
                                  {"brand": brand_name, "in_target": in_target, "confidence": confidence})



def analyze_advanced_indicators(conn, sample_id: int, html: str, final_url: str = "") -> dict:
    if not html:
        return {}

    # 1. Структурный остов DOM и DOM Hash (Task.md: Повторяющиеся DOM-шаблоны)
    skeleton = dom_analyzer.extract_dom_skeleton(html)
    dom_hash = dom_analyzer.compute_dom_hash(skeleton)
    simhash = dom_analyzer.compute_simhash(skeleton)

    if dom_hash:
        storage.add_signature(conn, sample_id, "dom_template", dom_hash,
                              {"simhash": hex(simhash), "skeleton_len": len(skeleton)})

    # 2. Глубокий аудит форм (Task.md: form action, кросс-доменность, credential harvesting)
    forms_audit = dom_analyzer.analyze_forms_deep(html, final_url)
    if forms_audit.get("has_cross_domain_post"):
        storage.add_finding(conn, sample_id, "cross_domain_form_action",
                            {"forms": forms_audit["forms"]}, severity="critical")
        storage.add_signature(conn, sample_id, "reason_code", "CROSS_DOMAIN_CREDENTIAL_THEFT")

    if forms_audit.get("c2_webhook_detected"):
        c2 = forms_audit["c2_webhook_detected"]
        storage.add_finding(conn, sample_id, "c2_webhook_exfiltration",
                            {"c2_type": c2}, severity="critical")
        storage.add_signature(conn, sample_id, "reason_code", f"C2_EXFILTRATION_{c2.upper()}")

    if forms_audit.get("has_credential_harvesting"):
        storage.add_finding(conn, sample_id, "credential_form",
                            {"total_passwords": forms_audit["total_password_fields"]}, severity="high")
        storage.add_signature(conn, sample_id, "reason_code", "CREDENTIAL_HARVESTING_FORM")

    # 3. Детерминированный анализ обфускации (Task.md: Признаки обфускации)
    obf = obfuscation_detector.analyze_obfuscation(html)
    if obf.get("is_obfuscated"):
        storage.add_finding(conn, sample_id, "obfuscated_code",
                            {"techniques": obf["techniques"], "max_entropy": obf["max_entropy"]},
                            severity="high")
        for tech in obf["techniques"]:
            storage.add_signature(conn, sample_id, "reason_code", f"OBFUSCATION_{tech.upper()}")

    # 4. Маркеры phishing kits (Task.md: Сходство с phishing kits)
    kit = obfuscation_detector.detect_phishing_kit_markers(html)
    if kit.get("has_kit_markers"):
        storage.add_finding(conn, sample_id, "phishing_kit_marker",
                            {"markers": kit["markers"], "details": kit["details"]},
                            severity="high")
        for marker in kit["markers"]:
            storage.add_signature(conn, sample_id, "reason_code", f"PHISHING_KIT_{marker.upper()}")

    # 5. Извлечение ссылок Favicon (Task.md: Favicon)
    if final_url:
        fav_urls = favicon_analyzer.extract_favicon_urls(html, final_url)
        for fu in fav_urls[:3]:
            storage.add_url(conn, sample_id, fu, kind="favicon", source_artifact="dom.html")

    return {
        "dom_hash": dom_hash,
        "simhash": simhash,
        "forms_audit": forms_audit,
        "obfuscation": obf,
        "kit_markers": kit,
    }


# ---------------------------------------------------------------- step 3: signatures
def generate_signatures(conn, sample_id: int, urls: List[dict], artifacts: List[dict]) -> None:
    # URL/DOM-шаблоны: берём структуру пути как шаблон
    for u in urls[:10]:
        url = u.get("url", "")
        m = re.match(r"https?://([^/]+)(/.*)?", url)
        if m:
            domain = m.group(1)
            path = m.group(2) or "/"
            # Паттерн пути с заменой динамических сегментов
            path_parts = [p for p in path.split("/") if p]
            if path_parts:
                template = "/{}/".format("/".join("{}" if re.fullmatch(r"[0-9a-f]{8,}", p) or len(p) > 24 else p for p in path_parts))
                storage.add_signature(conn, sample_id, "url_template",
                                      f"{domain}{template}", {"url": url})

    # Fingerprints по хэшам артефактов
    for a in artifacts[:20]:
        if a.get("sha256"):
            storage.add_signature(conn, sample_id, "fingerprint", a["sha256"],
                                  {"path": a.get("path"), "kind": a.get("kind")})

    # Reason codes: если есть findings — строим компактный код
    findings = storage.list_findings(conn, sample_id)
    techniques = [f["technique"] for f in findings]
    if techniques:
        storage.add_signature(conn, sample_id, "reason_code",
                              "+".join(sorted(set(techniques))),
                              {"count": len(techniques)})

