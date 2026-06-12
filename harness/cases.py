"""Case management layer — every detected item becomes a tracked case.

Lifecycle: NEW → TRIAGED → NOTIFIED → IN_PROGRESS → CLOSED. The timeline
records who did what (actor "agent" or "human"), so the division of labor is
visible at a glance. Purely additive on top of db.py: cases reference
items/briefs by item_id and own their schema here.

Run the migration + a queue printout:  uv run python -m harness.cases
"""

import json
import sqlite3
from datetime import datetime, timezone

from harness import db

STATUSES = ["NEW", "TRIAGED", "NOTIFIED", "IN_PROGRESS", "CLOSED"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id       TEXT NOT NULL UNIQUE,
    status        TEXT NOT NULL DEFAULT 'NEW',
    owner_units   TEXT DEFAULT '',
    opened_ts     TEXT NOT NULL,
    closed_ts     TEXT,
    timeline_json TEXT NOT NULL DEFAULT '[]'
);
"""


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _entry(actor: str, action: str, note: str = "", ts: str | None = None) -> dict:
    return {"ts": ts or _now(), "actor": actor, "action": action, "note": note}


def open_case(conn: sqlite3.Connection, item_id: str, ts: str | None = None) -> int:
    """Auto-open a case for a detected item (idempotent on item_id)."""
    ensure(conn)
    ts = ts or _now()
    timeline = [_entry("agent", "detected", f"new item from source watch: {item_id}", ts)]
    cur = conn.execute(
        "INSERT OR IGNORE INTO cases (item_id, status, opened_ts, timeline_json) "
        "VALUES (?, 'NEW', ?, ?)",
        (item_id, ts, json.dumps(timeline)),
    )
    conn.commit()
    if cur.rowcount:
        db.audit(conn, "case_open", item_id.split(":")[0], "NEW", "autonomous",
                 f"case auto-opened for {item_id}")
    row = conn.execute("SELECT id FROM cases WHERE item_id = ?", (item_id,)).fetchone()
    return row["id"]


def get(conn: sqlite3.Connection, case_id: int) -> dict | None:
    ensure(conn)
    row = conn.execute("""
        SELECT c.*, b.impact_level, b.classification, b.summary, b.effective_date,
               b.escalated, m.title, m.url, m.source
        FROM cases c
        LEFT JOIN briefs b ON b.item_id = c.item_id
        LEFT JOIN items_meta m ON m.id = c.item_id
        WHERE c.id = ?
    """, (case_id,)).fetchone()
    if row is None:
        return None
    case = dict(row)
    case["timeline"] = json.loads(case.pop("timeline_json") or "[]")
    return case


def queue(conn: sqlite3.Connection) -> list[dict]:
    """All cases for the queue view, sorted by status order then impact."""
    ensure(conn)
    rows = conn.execute("""
        SELECT c.id, c.item_id, c.status, c.owner_units, c.opened_ts, c.closed_ts,
               c.timeline_json, b.impact_level, b.summary, b.effective_date,
               m.title, m.url, m.source
        FROM cases c
        LEFT JOIN briefs b ON b.item_id = c.item_id
        LEFT JOIN items_meta m ON m.id = c.item_id
    """).fetchall()
    status_rank = {s: i for i, s in enumerate(STATUSES)}
    impact_rank = {"HIGH": 0, "MED": 1, "LOW": 2}
    cases = []
    for r in rows:
        case = dict(r)
        case["timeline"] = json.loads(case.pop("timeline_json") or "[]")
        cases.append(case)
    cases.sort(key=lambda c: (status_rank.get(c["status"], 9),
                              impact_rank.get(c["impact_level"], 9),
                              c["opened_ts"]))
    return cases


def _append(conn: sqlite3.Connection, case_id: int, entry: dict) -> None:
    row = conn.execute("SELECT timeline_json FROM cases WHERE id = ?", (case_id,)).fetchone()
    timeline = json.loads(row["timeline_json"] or "[]")
    timeline.append(entry)
    conn.execute("UPDATE cases SET timeline_json = ? WHERE id = ?",
                 (json.dumps(timeline), case_id))
    conn.commit()


def transition(conn: sqlite3.Connection, case_id: int, new_status: str,
               actor: str, note: str = "", owner_units: list[str] | None = None) -> dict:
    """Advance a case along the lifecycle. Forward-only; every transition is
    a timeline entry AND an audit event (which also lands in ClickHouse)."""
    ensure(conn)
    case = get(conn, case_id)
    if case is None:
        raise ValueError(f"no case {case_id}")
    cur_rank, new_rank = STATUSES.index(case["status"]), STATUSES.index(new_status)
    if new_rank <= cur_rank:
        raise ValueError(f"case {case_id}: cannot move {case['status']} → {new_status}")
    sets, args = ["status = ?"], [new_status]
    if owner_units is not None:
        sets.append("owner_units = ?")
        args.append(",".join(owner_units))
    if new_status == "CLOSED":
        sets.append("closed_ts = ?")
        args.append(_now())
    args.append(case_id)
    conn.execute(f"UPDATE cases SET {', '.join(sets)} WHERE id = ?", args)
    conn.commit()
    _append(conn, case_id, _entry(actor, new_status.lower(), note))
    autonomy = "autonomous" if actor == "agent" else "human-in-loop"
    db.audit(conn, "case_transition", (case["item_id"] or "").split(":")[0],
             f"{case['status']}→{new_status}", autonomy,
             note or f"case {case_id} by {actor}")
    return get(conn, case_id)


def add_update(conn: sqlite3.Connection, case_id: int, actor: str, note: str) -> dict:
    """Append a timeline note. A human update on a NOTIFIED case advances it
    to IN_PROGRESS — the owning team has picked it up."""
    ensure(conn)
    case = get(conn, case_id)
    if case is None:
        raise ValueError(f"no case {case_id}")
    if case["status"] == "NOTIFIED" and actor == "human":
        return transition(conn, case_id, "IN_PROGRESS", actor, note)
    _append(conn, case_id, _entry(actor, "update", note))
    db.audit(conn, "case_update", (case["item_id"] or "").split(":")[0],
             case["status"], "autonomous" if actor == "agent" else "human-in-loop",
             note)
    return get(conn, case_id)


def attach_draft(conn: sqlite3.Connection, case_id: int, draft: str) -> None:
    """Attach the agent-drafted owner notification to the timeline."""
    _append(conn, case_id, _entry("agent", "drafted", draft))


def record(conn: sqlite3.Connection, case_id: int, actor: str, action: str,
           note: str = "") -> None:
    """Timeline-only entry, no status change, no audit row — for moments the
    gate already audits (e.g. the escalation hold)."""
    _append(conn, case_id, _entry(actor, action, note))


def migrate_existing(conn: sqlite3.Connection) -> int:
    """Open cases for briefs that predate the case layer, reconstructing a
    minimal credible timeline from what the pipeline recorded. Idempotent."""
    ensure(conn)
    rows = conn.execute("""
        SELECT b.item_id, b.impact_level, b.business_units, b.escalated,
               s.first_seen
        FROM briefs b
        LEFT JOIN items_seen s ON s.id = b.item_id
        WHERE b.item_id NOT IN (SELECT item_id FROM cases)
    """).fetchall()
    for r in rows:
        ts = r["first_seen"] or _now()
        units = r["business_units"] or ""
        timeline = [
            _entry("agent", "detected", "migrated from pre-case feed", ts),
            _entry("agent", "triaged",
                   f"classified {r['impact_level']} — owners: {units or 'unassigned'}", ts),
        ]
        if r["escalated"] == 1:                      # HIGH, awaiting human review
            status = "TRIAGED"
            timeline.append(_entry("agent", "escalated",
                                   "HIGH impact — awaiting human review", ts))
        elif r["escalated"] == 2:                    # HIGH, human acknowledged
            status = "NOTIFIED"
            timeline.append(_entry("agent", "escalated",
                                   "HIGH impact — awaiting human review", ts))
            timeline.append(_entry("human", "notified", "approved & notified owners", ts))
        else:                                        # LOW/MED, autonomous
            status = "NOTIFIED"
            timeline.append(_entry("agent", "notified",
                                   "owner notification sent autonomously", ts))
        conn.execute(
            "INSERT INTO cases (item_id, status, owner_units, opened_ts, timeline_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (r["item_id"], status, units, ts, json.dumps(timeline)),
        )
    conn.commit()
    if rows:
        db.audit(conn, "case_migrate", "system", "MIGRATED", "autonomous",
                 f"opened {len(rows)} cases for pre-existing briefs")
    return len(rows)


if __name__ == "__main__":
    conn = db.connect()
    n = migrate_existing(conn)
    print(f"migrated {n} existing brief(s) into cases\n")
    print(f"{'#':>3}  {'STATUS':<12} {'IMPACT':<6} {'OWNERS':<28} TITLE")
    for c in queue(conn):
        print(f"{c['id']:>3}  {c['status']:<12} {c['impact_level'] or '-':<6} "
              f"{(c['owner_units'] or '-')[:28]:<28} {(c['title'] or c['item_id'])[:60]}")
        for e in c["timeline"]:
            print(f"     · {e['ts']}  [{e['actor']}] {e['action']}"
                  f"{' — ' + e['note'][:70] if e['note'] else ''}")
