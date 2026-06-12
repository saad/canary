"""The demo keypress, on REAL data: erase the agent's memory of one real
rule it has already seen. The next poll re-fetches the live source and the
agent detects, classifies, drafts, and escalates it — every byte real; only
the agent's memory of the item is reset.

  uv run python -m harness.redetect            (default: NACHA sanctions return-code rule)
  uv run python -m harness.redetect <item-id>
"""

import argparse
import json
import time

from harness import db
from sources.injector import INJECTED_AT_FILE

DEFAULT = "nacha:new-return-reason-code-sanctions-compliance-obligations"


def trigger(item_id: str = DEFAULT) -> None:
    conn = db.connect()
    conn.execute("DELETE FROM items_seen WHERE id = ?", (item_id,))
    # clear any prior run of this beat so rehearsals repeat cleanly
    conn.execute("DELETE FROM cases WHERE item_id = ?", (item_id,))
    conn.execute("DELETE FROM briefs WHERE item_id = ?", (item_id,))
    conn.execute("DELETE FROM items_meta WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    # stamp the keypress so the poller prints keypress→escalation seconds
    try:
        stamps = json.loads(INJECTED_AT_FILE.read_text()) if INJECTED_AT_FILE.exists() else {}
    except Exception:
        stamps = {}
    stamps[item_id] = time.time()
    INJECTED_AT_FILE.parent.mkdir(parents=True, exist_ok=True)
    INJECTED_AT_FILE.write_text(json.dumps(stamps))
    print(f"FORGOTTEN → {item_id}")
    print("the canary will re-detect it on the next poll, live from the source")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset the agent's memory of one real item")
    parser.add_argument("item_id", nargs="?", default=DEFAULT)
    trigger(parser.parse_args().item_id)
