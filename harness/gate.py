"""The autonomy gate — the single chokepoint every classified item passes
through. Graduated autonomy: LOW/MED proceed autonomously; HIGH pauses and
waits for a human acknowledge. Every decision writes an audit event.

This is the function the Guildai control plane wraps when GUILDAI_ENABLED
(SDK details TBD from booth): keep all decision logic inside decide() so the
wrapper sees one call with one structured result."""

import sqlite3
from dataclasses import dataclass
from typing import Callable

from harness import db
from sources.base import Item


@dataclass
class GateDecision:
    action: str           # "IGNORE" | "STORE_BRIEF" | "ESCALATE"
    autonomy_level: str   # "autonomous" | "human-in-loop"
    reason: str


def _console_notify(item: Item, brief: dict) -> None:
    units = ", ".join(brief["business_units"])
    print(f"\n  *** ESCALATION — HIGH impact ***")
    print(f"  [{item.source}] {item.title}")
    print(f"  units: {units} | effective: {brief['effective_date'] or 'unstated'}")
    print(f"  {brief['summary']}")


def _console_acknowledge(item: Item, brief: dict) -> str:
    input("  acknowledge to continue [enter] > ")
    return "console-enter"


def decide(
    conn: sqlite3.Connection,
    item: Item,
    brief: dict,
    notify: Callable[[Item, dict], None] = _console_notify,
    acknowledge: Callable[[Item, dict], str] | None = _console_acknowledge,
) -> GateDecision:
    """Route a classified item. Pass acknowledge=None to leave HIGH items
    pending (escalated, awaiting review) without blocking the loop."""
    if not brief["relevant"]:
        decision = GateDecision("IGNORE", "autonomous", "classified not relevant to our charter")
        db.audit(conn, "classify", item.source, "IGNORE", "autonomous", decision.reason)
        return decision

    escalate = brief["impact_level"] == "HIGH"
    db.save_brief(conn, item.id, brief["classification"], brief["business_units"],
                  brief["impact_level"], brief["effective_date"], brief["summary"],
                  escalated=escalate)

    if not escalate:
        decision = GateDecision(
            "STORE_BRIEF", "autonomous",
            f"{brief['impact_level']} impact — within autonomous authority",
        )
        db.audit(conn, "classify", item.source, "STORE_BRIEF", "autonomous", decision.reason)
        return decision

    decision = GateDecision(
        "ESCALATE", "human-in-loop",
        f"HIGH impact on {', '.join(brief['business_units'])} — human review required",
    )
    db.audit(conn, "escalate", item.source, "ESCALATE", "human-in-loop", decision.reason)
    notify(item, brief)
    from harness import guild_gate
    guild_gate.review_escalation(item, brief)
    if acknowledge is not None:
        ack_via = acknowledge(item, brief)
        db.mark_acknowledged(conn, item.id)
        db.audit(conn, "acknowledge", item.source, "ACKNOWLEDGED", "human-in-loop",
                 f"human acknowledged via {ack_via}")
    return decision
