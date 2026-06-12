"""NCUA Letters to Credit Unions adapter — live scrape of the index page
(titles/links, best-effort dates), falling back to a committed snapshot.
A successful live fetch refreshes the snapshot so the fallback stays real."""

import json
import re

import requests

import config
from sources.base import Item, USER_AGENT, TIMEOUT

name = "ncua"

BASE = "https://ncua.gov"
INDEX = f"{BASE}/regulation-supervision/letters-credit-unions-other-guidance"
SNAPSHOT = config.SNAPSHOT_DIR / "ncua.json"

LINK_RE = re.compile(
    r'<a href="(/regulation-supervision/letters-credit-unions-other-guidance/[^"#]+)"[^>]*>([^<]+)</a>'
)
# The listing is a table: each title link is followed by <td> cells for
# topic, letter type, and year.
CELL_RE = re.compile(r"<td>([^<]*?)\s*</td>")


def _parse(html: str) -> list[Item]:
    items: list[Item] = []
    seen: set[str] = set()
    for match in LINK_RE.finditer(html):
        path, title = match.group(1), match.group(2)
        title = re.sub(r"&rsquo;", "'", title)
        title = re.sub(r"&amp;", "&", title).strip()
        if path in seen or "menu" in title.lower():
            continue
        seen.add(path)
        window = html[match.end():match.end() + 600]
        cells = [c.strip() for c in CELL_RE.findall(window)]
        topic = cells[0] if cells else ""
        date = next((c for c in cells if re.fullmatch(r"\d{4}", c)), None)
        slug = path.rsplit("/", 1)[-1]
        excerpt = f"NCUA guidance — {topic}: {title}" if topic else f"NCUA guidance: {title}"
        items.append(Item(
            id=f"ncua:{slug}",
            source=name,
            title=title,
            date=date,
            url=f"{BASE}{path}",
            raw_excerpt=excerpt,
        ))
    return items[:15]


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
            return items
    except Exception:
        pass
    return _load_snapshot()
