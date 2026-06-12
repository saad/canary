"""ClickHouse sink (env-flagged). Mirrors audit events and briefs to
ClickHouse Cloud over HTTPS; SQLite stays the source of truth locally, so
any failure here just logs once and the demo carries on."""

import json
import time

import config

_tables_ready = False
_warned = False

DDL = [
    """CREATE TABLE IF NOT EXISTS canary_audit_events (
        ts String, action String, source String, decision String,
        autonomy_level String, reason String
    ) ENGINE = MergeTree ORDER BY ts""",
    """CREATE TABLE IF NOT EXISTS canary_briefs (
        ts String, item_id String, classification String, business_units String,
        impact_level String, effective_date String, summary String, escalated UInt8
    ) ENGINE = MergeTree ORDER BY ts""",
]


def enabled() -> bool:
    return bool(config.CLICKHOUSE_ENABLED and config.CLICKHOUSE_URL)


def _execute(query: str, body: str = "", timeout: int = 10) -> str:
    import requests
    resp = requests.post(
        config.CLICKHOUSE_URL,
        params={"query": query},
        data=body.encode(),
        auth=(config.CLICKHOUSE_USER, config.CLICKHOUSE_PASSWORD),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text


def _warn_once(exc: Exception) -> None:
    global _warned
    if not _warned:
        print(f"    ! clickhouse sink unavailable ({type(exc).__name__}) — continuing on SQLite only")
        _warned = True


def _ensure_tables() -> None:
    global _tables_ready
    if not _tables_ready:
        for ddl in DDL:
            _execute(ddl)
        _tables_ready = True


def warmup() -> None:
    """Create tables ahead of the first insert (call at process start) —
    avoids losing the first rows to Cloud DDL propagation delay."""
    if not enabled():
        return
    try:
        _ensure_tables()
    except Exception as exc:
        _warn_once(exc)


def insert(table: str, row: dict) -> None:
    if not enabled():
        return
    body = json.dumps(row, default=str)
    for attempt in (1, 2):
        try:
            _ensure_tables()
            _execute(f"INSERT INTO {table} FORMAT JSONEachRow", body, timeout=5)
            return
        except Exception as exc:
            if attempt == 2:
                _warn_once(exc)
            else:
                time.sleep(0.5)


def query_json(sql: str, timeout: int = 10) -> list[dict]:
    """Read back for the dashboard's audit view. Empty list on any failure
    (including a slow Cloud instance waking from idle — callers fall back)."""
    if not enabled():
        return []
    try:
        _ensure_tables()
        text = _execute(sql + " FORMAT JSONEachRow", timeout=timeout)
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except Exception as exc:
        _warn_once(exc)
        return []


def keep_warm(interval: int = 45) -> None:
    """Background pinger so the Cloud instance never idle-pauses mid-demo."""
    if not enabled():
        return
    import threading

    def loop():
        import time
        while True:
            try:
                _execute("SELECT 1", timeout=8)
            except Exception:
                pass
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()
