"""Detection loop: poll every source, diff against items_seen, route new
items through classify → gate, narrating to the console.

Unattended demo mode (Step 4):

  uv run python -m harness.poller --interval 15

First run on an empty DB baselines existing items, then watches. Trigger the
demo beat from another terminal:  uv run python -m sources.injector

Escalation handling: --ack console (default) pauses the loop until Enter —
the live-demo beat; --ack pending records the escalation as awaiting review
and keeps polling (the dashboard's acknowledge button closes it out)."""

import argparse
import sqlite3
import threading
import time
from datetime import datetime

import config

from agents import classifier, notifier
from harness import cases, db, gate, notify
from sources import federal_register, ncua, nacha, irs, injector
from sources.base import Item

PUBLISH = True  # backfill flips this off so resets don't blast the channel

ADAPTERS = [federal_register, ncua, nacha, irs, injector]


def _say(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


def baseline(conn: sqlite3.Connection, skip: set[str] = frozenset()) -> int:
    """Mark everything currently visible as seen (no classification), so the
    loop only reacts to genuinely new items. `skip` ids stay unseen."""
    count = 0
    for adapter in ADAPTERS:
        if adapter is injector:
            continue
        for item in adapter.fetch_latest():
            if item.id not in skip and db.mark_seen(conn, item.id, item.source):
                count += 1
    _say(f"BASELINE — {count} existing items marked seen")
    return count


def _draft_async(case_id: int, item: Item, brief: dict, advance: bool) -> None:
    """Draft the owner notification off the hot path — escalation must never
    wait on a Bedrock call. Attaches the draft when it returns; LOW/MED then
    advance to NOTIFIED (HIGH stays held for the human)."""
    def work():
        conn = db.connect()
        try:
            draft = notifier.draft(item, brief)
            cases.attach_draft(conn, case_id, draft)
            stamp = injector.injected_at(item.id)
            if stamp is not None:
                _say(f"  ⏱ keypress → draft attached: {time.time() - stamp:.1f}s")
            if advance:
                delivery = notify.publish(item.title, brief["impact_level"],
                                          brief["business_units"], draft, case_id) if PUBLISH else None
                if delivery:
                    state = "DELIVERED" if delivery["ok"] else "FAILED"
                    cases.record(conn, case_id, "agent", "published",
                                 f"notification {state.lower()} via {delivery['detail']}")
                    db.audit(conn, "publish", item.source, state, "autonomous",
                             f"case #{case_id} owner notification via {delivery['detail']}")
                    _say(f"  📤 {state.lower()} via {delivery['detail']}")
                try:
                    cases.transition(conn, case_id, "NOTIFIED", "agent",
                                     f"{brief['impact_level']} impact — owners notified "
                                     "autonomously (within autonomous authority)")
                    _say(f"  ✉ draft attached → case #{case_id} NOTIFIED (autonomous)")
                except ValueError:  # human already moved the case on
                    _say(f"  ✉ draft attached to case #{case_id} (already advanced)")
            else:
                _say(f"  ✉ draft attached to case #{case_id} — awaiting human Approve & Notify")
        finally:
            conn.close()
    threading.Thread(target=work, daemon=True).start()


def handle_new(conn: sqlite3.Connection, item: Item, acknowledge=gate._console_acknowledge) -> gate.GateDecision:
    _say(f"NEW ITEM ({item.source}) {item.title[:80]}")
    db.save_meta(conn, item)
    case_id = cases.open_case(conn, item.id)
    _say(f"  ⊕ case #{case_id} opened (NEW)")
    brief = classifier.classify(item)
    if brief["relevant"]:
        cases.transition(conn, case_id, "TRIAGED", "agent",
                         f"classified {brief['impact_level']} — owners: "
                         f"{', '.join(brief['business_units']) or 'unassigned'}",
                         owner_units=brief["business_units"])
        cases.record(conn, case_id, "agent", "draft_pending",
                     "drafting owner notification…")
    decision = gate.decide(conn, item, brief, acknowledge=acknowledge)
    stamp = injector.injected_at(item.id)
    if stamp is not None:
        visible = "escalation" if decision.action == "ESCALATE" else "triage"
        _say(f"  ⏱ keypress → {visible} visible: {time.time() - stamp:.1f}s")
    if not brief["relevant"]:
        cases.transition(conn, case_id, "CLOSED", "agent",
                         "classified not relevant to our charter — closed, no action")
    else:
        if decision.action == "ESCALATE":
            cases.record(conn, case_id, "agent", "escalated",
                         "HIGH impact — held at TRIAGED, awaiting human Approve & Notify")
            if acknowledge is not None:
                cases.transition(conn, case_id, "NOTIFIED", "human",
                                 "approved & notified via console acknowledge")
        _draft_async(case_id, item, brief, advance=decision.action == "STORE_BRIEF")
    units = ", ".join(brief["business_units"]) or "-"
    if decision.action == "ESCALATE":
        suffix = "→ ESCALATED to human" + (" (awaiting review)" if acknowledge is None else " (acknowledged)")
    elif decision.action == "STORE_BRIEF":
        suffix = "→ brief stored (autonomous)"
    else:
        suffix = "→ ignored (not relevant)"
    _say(f"  → classified {brief['impact_level']} | units: {units} {suffix}")
    return decision


POLL_STATUS_FILE = config.DATA_DIR / "poll_status.json"


def _write_poll_status(status: dict) -> None:
    try:
        import json
        POLL_STATUS_FILE.write_text(json.dumps(status))
    except Exception:
        pass  # liveness display only — never break the loop


def poll_once(conn: sqlite3.Connection, acknowledge=gate._console_acknowledge) -> int:
    new_count = 0
    status = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), "sources": {}}
    for adapter in ADAPTERS:
        try:
            items = adapter.fetch_latest()
        except Exception as exc:
            _say(f"POLLED {adapter.name} — fetch failed ({type(exc).__name__}), skipping")
            status["sources"][adapter.name] = {"ok": False, "items": 0}
            continue
        fresh = [i for i in items if db.is_new(conn, i.id)]
        status["sources"][adapter.name] = {"ok": True, "items": len(items)}
        _say(f"POLLED {adapter.name} — {len(items)} items, {len(fresh)} new")
        for item in fresh:
            # mark_seen is the dedup gate: a duplicate id within the same
            # batch (e.g. double-tapped injector) inserts nothing and is skipped
            if not db.mark_seen(conn, item.id, item.source):
                continue
            handle_new(conn, item, acknowledge=acknowledge)
            new_count += 1
    _write_poll_status(status)
    return new_count


def run(interval: int = config.POLL_SECONDS, ack_mode: str = "console") -> None:
    from harness import clickhouse
    clickhouse.warmup()
    acknowledge = gate._console_acknowledge if ack_mode == "console" else None
    conn = db.connect()
    migrated = cases.migrate_existing(conn)
    if migrated:
        _say(f"opened {migrated} case(s) for pre-existing briefs")
    # seeded demo items don't count — a reset that seeds first must still baseline
    seen_count = conn.execute(
        "SELECT COUNT(*) FROM items_seen WHERE id NOT LIKE '%:seed-%'").fetchone()[0]
    if seen_count == 0:
        _say("first run — baselining existing items so we only react to changes")
        baseline(conn)
    _say(f"canary watching {len(ADAPTERS)} sources every {interval}s — Ctrl-C to stop")
    _say("(trigger the demo item any time:  uv run python -m sources.injector)")
    try:
        while True:
            new = poll_once(conn, acknowledge=acknowledge)
            if new == 0:
                _say(f"quiet skies — next poll in {interval}s")
            time.sleep(interval)
    except KeyboardInterrupt:
        _say("canary stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Canary detection loop")
    parser.add_argument("--interval", type=int, default=config.POLL_SECONDS,
                        help="seconds between polls (default: $DEMO_POLL_SECONDS or 10)")
    parser.add_argument("--ack", choices=["console", "pending"], default="console",
                        help="console: pause for Enter on HIGH; pending: log and keep polling")
    args = parser.parse_args()
    run(interval=args.interval, ack_mode=args.ack)
