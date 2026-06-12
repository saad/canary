"""SQLite state: items seen, impact briefs, and the audit trail."""

import sqlite3
from datetime import datetime, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS items_seen (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    first_seen  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS briefs (
    item_id        TEXT NOT NULL,
    classification TEXT,
    business_units TEXT,
    impact_level   TEXT,
    effective_date TEXT,
    summary        TEXT,
    escalated      INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit_events (
    ts             TEXT NOT NULL,
    action         TEXT NOT NULL,
    source         TEXT,
    decision       TEXT,
    autonomy_level TEXT,
    reason         TEXT
);
CREATE TABLE IF NOT EXISTS items_meta (
    id     TEXT PRIMARY KEY,
    source TEXT,
    title  TEXT,
    date   TEXT,
    url    TEXT
);
"""


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mark_seen(conn: sqlite3.Connection, item_id: str, source: str) -> bool:
    """Record an item; returns True if it was new."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO items_seen (id, source, first_seen) VALUES (?, ?, ?)",
        (item_id, source, _now()),
    )
    conn.commit()
    return cur.rowcount > 0


def is_new(conn: sqlite3.Connection, item_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM items_seen WHERE id = ?", (item_id,)).fetchone()
    return row is None


def save_meta(conn: sqlite3.Connection, item) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO items_meta (id, source, title, date, url) VALUES (?, ?, ?, ?, ?)",
        (item.id, item.source, item.title, item.date, item.url),
    )
    conn.commit()


def mark_acknowledged(conn: sqlite3.Connection, item_id: str) -> None:
    """briefs.escalated: 0 = not escalated, 1 = awaiting review, 2 = acknowledged."""
    conn.execute("UPDATE briefs SET escalated = 2 WHERE item_id = ? AND escalated = 1", (item_id,))
    conn.commit()


def feed(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT b.rowid AS rid, b.*, m.title, m.date, m.url, s.first_seen
        FROM briefs b
        LEFT JOIN items_meta m ON m.id = b.item_id
        LEFT JOIN items_seen s ON s.id = b.item_id
        ORDER BY s.first_seen DESC, b.rowid DESC
    """).fetchall()
    return [dict(r) for r in rows]


def save_brief(conn: sqlite3.Connection, item_id: str, classification: str,
               business_units: list[str], impact_level: str,
               effective_date: str | None, summary: str, escalated: bool) -> None:
    conn.execute(
        "INSERT INTO briefs VALUES (?, ?, ?, ?, ?, ?, ?)",
        (item_id, classification, ",".join(business_units), impact_level,
         effective_date, summary, int(escalated)),
    )
    conn.commit()
    from harness import clickhouse
    clickhouse.insert("canary_briefs", {
        "ts": _now(), "item_id": item_id, "classification": classification,
        "business_units": ",".join(business_units), "impact_level": impact_level,
        "effective_date": effective_date or "", "summary": summary,
        "escalated": int(escalated),
    })


def audit(conn: sqlite3.Connection, action: str, source: str, decision: str,
          autonomy_level: str, reason: str) -> None:
    ts = _now()
    conn.execute(
        "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?)",
        (ts, action, source, decision, autonomy_level, reason),
    )
    conn.commit()
    from harness import clickhouse
    clickhouse.insert("canary_audit_events", {
        "ts": ts, "action": action, "source": source or "", "decision": decision,
        "autonomy_level": autonomy_level, "reason": reason,
    })
