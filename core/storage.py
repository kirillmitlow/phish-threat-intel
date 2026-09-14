import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = os.getenv("THREAT_DB_PATH", "/app/data/analysis.db")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,          -- тип входа: url / file / email / folder
    source_ref  TEXT NOT NULL,          -- сам URL / путь / письмо
    created_at  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending / collecting / analyzed / failed
    campaign_id INTEGER                 -- привязка к спам-кампании
);

CREATE TABLE IF NOT EXISTS urls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   INTEGER,
    url         TEXT NOT NULL,
    kind        TEXT DEFAULT 'link',    -- link / script / form / iframe / attachment / qr / redirect
    final_url   TEXT,
    redirect_chain TEXT,                -- JSON-список
    source_artifact TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS artifacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   INTEGER,
    kind        TEXT NOT NULL,          -- screenshot / html / attachment / pdf_png / qr_image / document
    path        TEXT,                   -- путь в /app/data/artifacts
    md5         TEXT,
    sha256      TEXT,
    meta        TEXT,                   -- JSON (размер, mime, текст-сниппет)
    created_at  TEXT NOT NULL,
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS brands (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   INTEGER,
    brand       TEXT NOT NULL,
    in_target   BOOLEAN DEFAULT 0,      -- признак: бренд из отслеживаемого каталога
    confidence  REAL,
    method      TEXT DEFAULT 'vlm',     -- как определён: vlm / llm / domain
    evidence    TEXT,                   -- короткое объяснение
    created_at  TEXT NOT NULL,
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS findings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   INTEGER,
    technique   TEXT NOT NULL,          -- brand_impersonation / credential_form / qr_phish / redirect / obfuscated_js / html_attachment / ...
    evidence    TEXT,                   -- JSON-доказательства
    severity    TEXT DEFAULT 'info',    -- info / low / medium / high / critical
    created_at  TEXT NOT NULL,
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS signatures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   INTEGER,
    kind        TEXT NOT NULL,          -- signature / url_template / dom_template / rule / fingerprint / brand_feature / reason_code
    signature   TEXT NOT NULL,          -- само значение (компактный артефакт)
    meta        TEXT,                   -- JSON
    created_at  TEXT NOT NULL,
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE
);

-- Полная цепочка рассуждений агента: каждый шаг ReAct-цикла (thought/action/observation)
CREATE TABLE IF NOT EXISTS agent_traces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   INTEGER,
    agent_name  TEXT NOT NULL,          -- collector_agent / analyst_agent
    step        INTEGER NOT NULL,       -- номер шага в цикле
    kind        TEXT NOT NULL,          -- thought / action / observation / final
    content     TEXT,                   -- текст мысли / имя инструмента / результат
    args        TEXT,                   -- JSON аргументы (для action)
    created_at  TEXT NOT NULL,
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE
);
-- Кластеризованные фишинговые/спам кампании (Task.md: Campaign Tracking)
CREATE TABLE IF NOT EXISTS campaigns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,   -- CAMP_SBER_A1B2
    target_brand    TEXT,                   -- Сбер
    dom_hash        TEXT,                   -- структурный хэш DOM-остова
    kit_name        TEXT,                   -- определенный kit или 'custom'
    sample_count    INTEGER DEFAULT 1,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL
);
"""


def get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    target = db_path or os.getenv("THREAT_DB_PATH") or DEFAULT_DB_PATH
    p = Path(target)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    conn = get_conn(db_path)
    try:
        conn.executescript(SCHEMA)
        # Миграция: проверяем наличие колонки in_target в таблице brands
        cur = conn.execute("PRAGMA table_info(brands)")
        cols = [r["name"] for r in cur.fetchall()]
        if cols and "in_target" not in cols:
            conn.execute("ALTER TABLE brands ADD COLUMN in_target BOOLEAN DEFAULT 0")

        # Миграция: проверяем наличие колонки campaign_id в таблице samples
        cur_samples = conn.execute("PRAGMA table_info(samples)")
        cols_samples = [r["name"] for r in cur_samples.fetchall()]
        if cols_samples and "campaign_id" not in cols_samples:
            conn.execute("ALTER TABLE samples ADD COLUMN campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL")

        conn.commit()
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ---------- Samples ----------
def create_sample(conn: sqlite3.Connection, source: str, source_ref: str) -> int:
    cur = conn.execute(
        "INSERT INTO samples (source, source_ref, created_at) VALUES (?,?,?)",
        (source, source_ref, _now_iso()),
    )
    return cur.lastrowid


def set_sample_status(conn: sqlite3.Connection, sample_id: int, status: str) -> None:
    conn.execute("UPDATE samples SET status=? WHERE id=?", (status, sample_id))


# ---------- Urls ----------
def add_url(conn: sqlite3.Connection, sample_id: int, url: str,
            kind: str = "link", final_url: Optional[str] = None,
            redirect_chain: Optional[List[str]] = None,
            source_artifact: Optional[str] = None) -> int:
    cur = conn.execute(
        "INSERT INTO urls (sample_id, url, kind, final_url, redirect_chain, "
        "source_artifact, created_at) VALUES (?,?,?,?,?,?,?)",
        (sample_id, url, kind, final_url,
         json.dumps(redirect_chain) if redirect_chain else None,
         source_artifact, _now_iso()),
    )
    return cur.lastrowid


def list_urls(conn: sqlite3.Connection, sample_id: int) -> List[dict]:
    rows = conn.execute("SELECT * FROM urls WHERE sample_id=?", (sample_id,)).fetchall()
    out = [_row_to_dict(r) for r in rows]
    for o in out:
        if o.get("redirect_chain"):
            try:
                o["redirect_chain"] = json.loads(o["redirect_chain"])
            except Exception:
                pass
    return out


# ---------- Artifacts ----------
def add_artifact(conn: sqlite3.Connection, sample_id: int, kind: str, path: str,
                 md5: Optional[str] = None, sha256: Optional[str] = None,
                 meta: Optional[dict] = None) -> int:
    cur = conn.execute(
        "INSERT INTO artifacts (sample_id, kind, path, md5, sha256, meta, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (sample_id, kind, path, md5, sha256,
         json.dumps(meta, ensure_ascii=False) if meta else None, _now_iso()),
    )
    return cur.lastrowid


def list_artifacts(conn: sqlite3.Connection, sample_id: int) -> List[dict]:
    rows = conn.execute("SELECT * FROM artifacts WHERE sample_id=?", (sample_id,)).fetchall()
    out = [_row_to_dict(r) for r in rows]
    for o in out:
        if o.get("meta"):
            try:
                o["meta"] = json.loads(o["meta"])
            except Exception:
                pass
    return out


# ---------- Brands ----------
def add_brand(conn: sqlite3.Connection, sample_id: int, brand: str,
              confidence: float, method: str = "vlm", evidence: str = "",
              in_target: bool = False) -> int:
    cur = conn.execute(
        "INSERT INTO brands (sample_id, brand, in_target, confidence, method, evidence, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (sample_id, brand, 1 if in_target else 0, confidence, method, evidence, _now_iso()),
    )
    return cur.lastrowid


def list_brands(conn: sqlite3.Connection, sample_id: int) -> List[dict]:
    rows = conn.execute("SELECT * FROM brands WHERE sample_id=?", (sample_id,)).fetchall()
    out = []
    for r in rows:
        d = _row_to_dict(r)
        d["in_target"] = bool(d.get("in_target", 0))
        out.append(d)
    return out


# ---------- Findings ----------
def add_finding(conn: sqlite3.Connection, sample_id: int, technique: str,
                evidence: Optional[dict] = None, severity: str = "info") -> int:
    cur = conn.execute(
        "INSERT INTO findings (sample_id, technique, evidence, severity, created_at) "
        "VALUES (?,?,?,?,?)",
        (sample_id, technique,
         json.dumps(evidence, ensure_ascii=False) if evidence else None,
         severity, _now_iso()),
    )
    return cur.lastrowid


def list_findings(conn: sqlite3.Connection, sample_id: int) -> List[dict]:
    rows = conn.execute("SELECT * FROM findings WHERE sample_id=?", (sample_id,)).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------- Signatures ----------
def add_signature(conn: sqlite3.Connection, sample_id: int, kind: str,
                  signature: str, meta: Optional[dict] = None) -> int:
    cur = conn.execute(
        "INSERT INTO signatures (sample_id, kind, signature, meta, created_at) "
        "VALUES (?,?,?,?,?)",
        (sample_id, kind, signature,
         json.dumps(meta, ensure_ascii=False) if meta else None, _now_iso()),
    )
    return cur.lastrowid


def list_signatures(conn: sqlite3.Connection, sample_id: int) -> List[dict]:
    rows = conn.execute("SELECT * FROM signatures WHERE sample_id=?", (sample_id,)).fetchall()
    out = [_row_to_dict(r) for r in rows]
    for o in out:
        if o.get("meta"):
            try:
                o["meta"] = json.loads(o["meta"])
            except Exception:
                pass
    return out


# ---------- Agent traces (цепочка рассуждений) ----------
def add_trace(conn: sqlite3.Connection, sample_id: int, agent_name: str,
              step: int, kind: str, content: str, args: Optional[dict] = None) -> int:
    cur = conn.execute(
        "INSERT INTO agent_traces (sample_id, agent_name, step, kind, content, args, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (sample_id, agent_name, step, kind, content,
         json.dumps(args, ensure_ascii=False) if args else None, _now_iso()),
    )
    return cur.lastrowid


def list_traces(conn: sqlite3.Connection, sample_id: int) -> List[dict]:
    rows = conn.execute(
        "SELECT * FROM agent_traces WHERE sample_id=? ORDER BY step, id", (sample_id,)
    ).fetchall()
    out = [_row_to_dict(r) for r in rows]
    for o in out:
        if o.get("args"):
            try:
                o["args"] = json.loads(o["args"])
            except Exception:
                pass
    return out


# ---------- Campaigns ----------
def create_campaign(conn: sqlite3.Connection, name: str, target_brand: Optional[str] = None,
                    dom_hash: Optional[str] = None, kit_name: Optional[str] = None) -> int:
    now = _now_iso()
    cur = conn.execute(
        "INSERT INTO campaigns (name, target_brand, dom_hash, kit_name, sample_count, first_seen, last_seen) "
        "VALUES (?,?,?,?,1,?,?)",
        (name, target_brand, dom_hash, kit_name, now, now)
    )
    return cur.lastrowid


def get_campaign(conn: sqlite3.Connection, campaign_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    return _row_to_dict(row) if row else None


def find_matching_campaign(conn: sqlite3.Connection, target_brand: Optional[str] = None,
                           dom_hash: Optional[str] = None) -> Optional[dict]:
    if dom_hash and target_brand:
        row = conn.execute(
            "SELECT * FROM campaigns WHERE target_brand=? AND dom_hash=?",
            (target_brand, dom_hash)
        ).fetchone()
        if row:
            return _row_to_dict(row)

    if dom_hash:
        row = conn.execute("SELECT * FROM campaigns WHERE dom_hash=?", (dom_hash,)).fetchone()
        if row:
            return _row_to_dict(row)

    return None


def update_campaign_stats(conn: sqlite3.Connection, campaign_id: int) -> None:
    now = _now_iso()
    conn.execute(
        "UPDATE campaigns SET sample_count = sample_count + 1, last_seen=? WHERE id=?",
        (now, campaign_id)
    )


def link_sample_campaign(conn: sqlite3.Connection, sample_id: int, campaign_id: int) -> None:
    conn.execute("UPDATE samples SET campaign_id=? WHERE id=?", (campaign_id, sample_id))


def list_campaigns(conn: sqlite3.Connection) -> List[dict]:
    rows = conn.execute("SELECT * FROM campaigns ORDER BY last_seen DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------- Convenience ----------
def get_sample(conn: sqlite3.Connection, sample_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM samples WHERE id=?", (sample_id,)).fetchone()
    return _row_to_dict(row) if row else None


def full_report(conn: sqlite3.Connection, sample_id: int) -> dict:
    sample = get_sample(conn, sample_id)
    campaign = None
    if sample and sample.get("campaign_id"):
        campaign = get_campaign(conn, sample["campaign_id"])

    return {
        "sample": sample,
        "campaign": campaign,
        "urls": list_urls(conn, sample_id),
        "artifacts": list_artifacts(conn, sample_id),
        "brands": list_brands(conn, sample_id),
        "findings": list_findings(conn, sample_id),
        "signatures": list_signatures(conn, sample_id),
        "traces": list_traces(conn, sample_id),   # полная цепочка рассуждений агентов
    }