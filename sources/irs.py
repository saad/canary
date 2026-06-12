"""IRS newsroom adapter — live scrape of the current-month news releases,
keyword-filtered to information-return / filing-system / e-file topics.
If the filter matches nothing, the newest few items pass through (marked)
so the feed is never empty. Snapshot fallback mirrors ncua.py."""

import json
import re

import requests

import config
from sources.base import Item, USER_AGENT, TIMEOUT

name = "irs"

BASE = "https://www.irs.gov"
INDEX = f"{BASE}/newsroom/news-releases-for-current-month"
SNAPSHOT = config.SNAPSHOT_DIR / "irs.json"

KEYWORDS = (
    "information return", "e-file", "efile", "electronic filing", "filing system",
    "fire", "iris", "1099", "w-2", "form 945", "backup withholding", "tin matching",
)

# "IR-2026-76, June 8, 2026 — <summary>"
TEXT_RE = re.compile(
    r"(IR-\d{4}-\d+),\s+(\w+ \d{1,2}, \d{4})\s*(?:—|&mdash;)?\s*([^<]*)"
)

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


def _iso(date_text: str) -> str | None:
    m = re.match(r"(\w+) (\d{1,2}), (\d{4})", date_text.strip())
    if not m or m.group(1) not in MONTHS:
        return None
    return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"


ANCHOR_RE = re.compile(r'<a href="(/newsroom/[^"#]+)"[^>]*>(.*?)</a>', re.DOTALL)


def _strip_tags(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", fragment)).strip()


def _parse(html: str) -> list[Item]:
    # Pair each "IR-NNNN-NN, <date> — <summary>" text block with the nearest
    # preceding teaser anchor, which holds the title (in a nested span) + link.
    items: list[Item] = []
    seen: set[str] = set()
    for m in TEXT_RE.finditer(html):
        rid, date_text, summary = m.group(1), m.group(2), m.group(3).strip()
        if rid in seen or not summary:
            continue
        seen.add(rid)
        before = html[max(0, m.start() - 1200):m.start()]
        am = None
        for am in ANCHOR_RE.finditer(before):
            pass
        url = f"{BASE}{am.group(1)}" if am else INDEX
        title = _strip_tags(am.group(2)) if am else summary[:120]
        items.append(Item(
            id=f"irs:{rid}",
            source=name,
            title=title,
            date=_iso(date_text),
            url=url,
            raw_excerpt=summary[:500],
        ))
    return items


def _filtered(items: list[Item]) -> list[Item]:
    hits = [
        i for i in items
        if any(k in f"{i.title} {i.raw_excerpt}".lower() for k in KEYWORDS)
    ]
    if hits:
        return hits[:10]
    latest = items[:3]
    for i in latest:
        i.raw_excerpt = "[no filing-keyword match; latest release] " + i.raw_excerpt
    return latest


def _load_snapshot() -> list[Item]:
    try:
        return [Item.from_dict(d) for d in json.loads(SNAPSHOT.read_text())]
    except Exception:
        return []


def _save_snapshot(items: list[Item]) -> None:
    try:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps([i.to_dict() for i in items], indent=2))
    except Exception:
        pass


def fetch_latest() -> list[Item]:
    try:
        resp = requests.get(INDEX, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
        items = _parse(resp.text)
        if items:
            _save_snapshot(items)
            return _filtered(items)
    except Exception:
        pass
    return _filtered(_load_snapshot())
