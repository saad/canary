"""Step 2 done-criteria demo: one real item and the injected FIRE→IRIS item
flow end-to-end (detect → classify → gate → brief + audit trail).

  uv run python -m harness.run_step2 [--auto-ack] [--keep-db]

--auto-ack answers the HIGH escalation automatically (for unattended runs);
without it you press Enter at the escalation pause, exactly like the demo."""

import sys

import config
from harness import db, gate, poller
from sources import federal_register, injector


def main() -> None:
    auto_ack = "--auto-ack" in sys.argv
    if "--keep-db" not in sys.argv and config.DB_PATH.exists():
        config.DB_PATH.unlink()
    ack = (lambda item, brief: "auto-ack (demo script)") if auto_ack else gate._console_acknowledge

    conn = db.connect()

    # Baseline everything except the newest Federal Register item, so the
    # first poll detects exactly one real item.
    fedreg = federal_register.fetch_latest()
    newest = fedreg[0] if fedreg else None
    poller.baseline(conn, skip={newest.id} if newest else frozenset())

    print("\n--- poll 1: one real Federal Register item should be new ---")
    poller.poll_once(conn, acknowledge=ack)

    print("\n--- injecting FIRE→IRIS, poll 2 should escalate ---")
    injector.inject()
    poller.poll_once(conn, acknowledge=ack)

    print("\n--- briefs ---")
    for r in conn.execute("SELECT * FROM briefs"):
        print(f"  {r['item_id']}: {r['impact_level']} | units={r['business_units']} | "
              f"effective={r['effective_date']} | escalated={r['escalated']}")
        print(f"    {r['summary']}")

    print("\n--- audit trail ---")
    for r in conn.execute("SELECT * FROM audit_events ORDER BY ts"):
        print(f"  {r['ts']} {r['action']:<12} {r['source'] or '-':<18} "
              f"{r['decision']:<12} {r['autonomy_level']:<14} {r['reason']}")
    conn.close()


if __name__ == "__main__":
    main()
