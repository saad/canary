"""Demo seeding: two backdated cases showing the full lifecycle, so the
queue tells the whole story the moment FIRE→IRIS lands as NEW on top.

  uv run python -m harness.seed     (idempotent — skips if already present)

Seeds briefs/meta/cases directly with historical timestamps; deliberately
writes NO audit events — the audit trail stays an honest record of live runs.
"""

import json
from datetime import datetime, timedelta, timezone

from harness import db, cases


def _ts(days_ago: float, minutes: int = 0) -> str:
    t = datetime.now(timezone.utc) - timedelta(days=days_ago) + timedelta(minutes=minutes)
    return t.isoformat(timespec="seconds")


def _entry(actor, action, note, ts):
    return {"ts": ts, "actor": actor, "action": action, "note": note}


SEEDS = [
    {
        "item": {
            "id": "ncua:seed-cyber-incident-reporting",
            "source": "ncua",
            "title": "NCUA guidance: cyber incident reporting — 72-hour notification procedures",
            "date": _ts(3)[:10],
            "url": "https://ncua.gov/regulation-supervision/letters-credit-unions-other-guidance",
        },
        "brief": {
            "classification": "bedrock:us.anthropic.claude-sonnet-4-6",
            "business_units": "Ops,BSA/Compliance",
            "impact_level": "MED",
            "effective_date": _ts(3)[:10],
            "summary": ("NCUA issued follow-up guidance on the 72-hour cyber incident "
                        "notification rule, clarifying what counts as a reportable incident "
                        "and the expected documentation. We are subject to the rule and our "
                        "incident-response playbook must reflect the clarified thresholds. "
                        "Ops should update the playbook and BSA/Compliance should verify the "
                        "reporting workflow is documented for examiners."),
            "escalated": 0,
        },
        "case": {
            "status": "CLOSED",
            "opened_days_ago": 3,
            "closed_days_ago": 0.9,
            "timeline": [
                ("agent", "detected", "new item from source watch: ncua:seed-cyber-incident-reporting", _ts(3)),
                ("agent", "triaged", "classified MED — owners: Ops, BSA/Compliance", _ts(3, 1)),
                ("agent", "drafted",
                 "TO: Ops, BSA/Compliance\nSUBJECT: Update incident-response playbook for "
                 "clarified 72-hour cyber reporting thresholds\nNCUA clarified which cyber "
                 "incidents trigger the 72-hour NCUA notification and the documentation "
                 "examiners expect. Ops must update the incident-response playbook to the "
                 "clarified thresholds and re-run the tabletop exercise. BSA/Compliance must "
                 "verify the reporting workflow and evidence trail are documented.", _ts(3, 2)),
                ("agent", "notified", "MED impact — owners notified autonomously (within autonomous authority)", _ts(3, 2)),
                ("human", "in_progress", "Playbook updated to clarified thresholds; tabletop exercise scheduled with core vendor", _ts(2)),
                ("human", "closed", "Tabletop complete; 72-hour reporting procedure documented and examiner-ready", _ts(0.9)),
            ],
        },
    },
    {
        "item": {
            "id": "nacha:seed-rdfi-credit-monitoring",
            "source": "nacha",
            "title": "NACHA Operating Rules: ACH credit-push fraud monitoring obligations (phase 1)",
            "date": _ts(1.2)[:10],
            "url": "https://www.nacha.org/rules/fraud-monitoring",
        },
        "brief": {
            "classification": "bedrock:us.anthropic.claude-sonnet-4-6",
            "business_units": "Payments,Ops,BSA/Compliance",
            "impact_level": "MED",
            "effective_date": "2026-06-19",
            "summary": ("NACHA's phase-1 fraud-monitoring amendments require RDFIs to "
                        "monitor inbound ACH credits for fraud indicators starting June 19, "
                        "2026. As an RDFI we must stand up velocity and anomaly rules on "
                        "inbound credits and document the monitoring procedure. Payments owns "
                        "the rule configuration; Ops and BSA/Compliance own procedure and "
                        "documentation."),
            "escalated": 0,
        },
        "case": {
            "status": "IN_PROGRESS",
            "opened_days_ago": 1.2,
            "closed_days_ago": None,
            "timeline": [
                ("agent", "detected", "new item from source watch: nacha:seed-rdfi-credit-monitoring", _ts(1.2)),
                ("agent", "triaged", "classified MED — owners: Payments, Ops, BSA/Compliance", _ts(1.2, 1)),
                ("agent", "drafted",
                 "TO: Payments, Ops, BSA/Compliance\nSUBJECT: Configure inbound ACH credit "
                 "fraud monitoring before June 19 effective date\nNACHA phase-1 amendments "
                 "require RDFIs to monitor inbound ACH credits for fraud indicators from "
                 "June 19, 2026. Payments must configure velocity and anomaly rules in the "
                 "fraud engine; Ops must fold alert handling into daily procedures; "
                 "BSA/Compliance must document the monitoring approach for the next exam.", _ts(1.2, 2)),
                ("agent", "notified", "MED impact — owners notified autonomously (within autonomous authority)", _ts(1.2, 2)),
                ("human", "in_progress", "Velocity rules drafted in the fraud engine; vendor ticket open for anomaly model", _ts(0.8)),
                ("human", "update", "Core processor confirms monitoring rules deploy Friday; procedure doc in review", _ts(0.2)),
            ],
        },
    },
]


def seed() -> int:
    conn = db.connect()
    cases.ensure(conn)
    added = 0
    for s in SEEDS:
        item, brief, case = s["item"], s["brief"], s["case"]
        if conn.execute("SELECT 1 FROM cases WHERE item_id = ?", (item["id"],)).fetchone():
            continue
        opened = _ts(case["opened_days_ago"])
        conn.execute("INSERT OR IGNORE INTO items_seen (id, source, first_seen) VALUES (?, ?, ?)",
                     (item["id"], item["source"], opened))
        conn.execute("INSERT OR REPLACE INTO items_meta (id, source, title, date, url) VALUES (?, ?, ?, ?, ?)",
                     (item["id"], item["source"], item["title"], item["date"], item["url"]))
        conn.execute("INSERT INTO briefs VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (item["id"], brief["classification"], brief["business_units"],
                      brief["impact_level"], brief["effective_date"], brief["summary"],
                      brief["escalated"]))
        timeline = [_entry(a, act, note, ts) for a, act, note, ts in case["timeline"]]
        conn.execute(
            "INSERT INTO cases (item_id, status, owner_units, opened_ts, closed_ts, timeline_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (item["id"], case["status"], brief["business_units"], opened,
             _ts(case["closed_days_ago"]) if case["closed_days_ago"] is not None else None,
             json.dumps(timeline)),
        )
        added += 1
    conn.commit()
    conn.close()
    return added


if __name__ == "__main__":
    n = seed()
    print(f"seeded {n} demo case(s)" if n else "demo cases already present — nothing to do")
