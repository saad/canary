"""Demo injector — drops a realistic fake item into the feed on demand.
inject() queues a payload in data/inject_queue.json; fetch_latest() drains
the queue, so the polling loop picks injected items up like any source.

CLI (the demo keypress):  uv run python -m sources.injector
"""

import json
import time
from datetime import date

import config
from sources.base import Item

INJECTED_AT_FILE = config.DATA_DIR / "injected_at.json"

name = "injector"

DEFAULT_PAYLOAD = {
    "id": "irs:fire-to-iris-transition",
    "source": "irs",
    "title": "Transition of Information Returns Filing from FIRE to IRIS",
    "url": "https://www.irs.gov/filing/e-file-forms-1099-with-iris",
    "raw_excerpt": (
        "The IRS announced that the Filing Information Returns Electronically "
        "(FIRE) system will be retired and all information returns — including "
        "Forms 1099-INT, 1099-MISC, and 1098 — must be filed through the new "
        "Information Returns Intake System (IRIS). Filers must obtain an IRIS "
        "Transmitter Control Code; existing FIRE TCCs will not carry over. "
        "Organizations filing ten or more information returns are required to "
        "file electronically and should begin migration immediately to avoid "
        "penalties under IRC 6721 for failure to file correct information "
        "returns by the deadline. Compliance officers should verify that "
        "TIN-matching, backup-withholding, and recordkeeping procedures remain "
        "compliant through the transition and document the migration for "
        "examiners."
    ),
}


def inject(payload: dict | None = None) -> Item:
    data = dict(DEFAULT_PAYLOAD if payload is None else payload)
    data.setdefault("date", date.today().isoformat())
    item = Item.from_dict(data)
    queue = _read_queue()
    queue.append(item.to_dict())
    config.INJECT_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    config.INJECT_QUEUE.write_text(json.dumps(queue, indent=2))
    # Stamp the keypress so the poller can print keypress→escalation seconds.
    try:
        stamps = json.loads(INJECTED_AT_FILE.read_text()) if INJECTED_AT_FILE.exists() else {}
    except Exception:
        stamps = {}
    stamps[item.id] = time.time()
    INJECTED_AT_FILE.write_text(json.dumps(stamps))
    return item


def injected_at(item_id: str) -> float | None:
    try:
        return json.loads(INJECTED_AT_FILE.read_text()).get(item_id)
    except Exception:
        return None


def _read_queue() -> list[dict]:
    try:
        return json.loads(config.INJECT_QUEUE.read_text())
    except Exception:
        return []


def fetch_latest() -> list[Item]:
    queue = _read_queue()
    if not queue:
        return []
    try:
        config.INJECT_QUEUE.unlink()
    except OSError:
        pass
    return [Item.from_dict(d) for d in queue]


if __name__ == "__main__":
    item = inject()
    print(f"INJECTED → [{item.source}] {item.title}")
