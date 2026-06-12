"""Backfill: run the freshest REAL items from the live sources through the
actual pipeline (classify → case → draft → gate) so every queue row is a
real document with a real URL. Replaces synthetic seeding.

  uv run python -m harness.backfill

The hero item (the live re-detection demo beat — see harness/redetect.py)
is only marked seen, never cased, so the demo can detect it live."""

import time

from harness import db, cases, poller
from sources import federal_register, ncua, nacha, irs

HERO_ID = "nacha:new-return-reason-code-sanctions-compliance-obligations"
PER_SOURCE = {"federal_register": 2, "ncua": 2, "nacha": 2, "irs": 1}


def run() -> None:
    poller.PUBLISH = False  # backfill never blasts the delivery channel
    conn = db.connect()
    picked = []
    for adapter in (federal_register, ncua, nacha, irs):
        items = [i for i in adapter.fetch_latest() if i.id != HERO_ID]
        picked += items[: PER_SOURCE[adapter.name]]
    print(f"backfilling {len(picked)} real items through the live pipeline…")
    for item in picked:
        if not db.mark_seen(conn, item.id, item.source):
            continue  # already cased on a previous run
        poller.handle_new(conn, item, acknowledge=None)
    poller.baseline(conn)  # everything else (incl. the hero) just becomes 'seen'

    # async drafts finish out of band — wait so the reset ends in a calm state
    deadline = time.time() + 90
    while time.time() < deadline:
        pending = [c["id"] for c in cases.queue(conn)
                   if c["status"] != "CLOSED"
                   and not any(e["action"] == "drafted" for e in c["timeline"])]
        if not pending:
            break
        time.sleep(2)

    # warm pass: pre-compose every workspace so demo clicks are instant
    # (the disk-backed cache is shared with the server process)
    from concurrent.futures import ThreadPoolExecutor
    from harness import server as srv
    ids = [c["id"] for c in cases.queue(conn)]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(srv._c1_case, ids))
    warmed = sum(1 for r in results if "c1" in r)
    print(f"warm pass: {warmed}/{len(ids)} workspaces composed in {time.time() - t0:.0f}s")

    print(f"\n{'IMPACT':<6} {'STATUS':<12} TITLE")
    for c in cases.queue(conn):
        print(f"{c['impact_level'] or '-':<6} {c['status']:<12} {(c['title'] or c['item_id'])[:64]}")
    conn.close()


if __name__ == "__main__":
    run()
