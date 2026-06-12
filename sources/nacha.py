"""NACHA adapter — live scrape of the upcoming ACH rule amendments page
(nacha.org/newrules). Each entry carries a body blurb that usually states
the effective date; we surface that as the item date since amendments have
no publication date on the index. Snapshot fallback mirrors ncua.py."""

import html as html_lib
import json
import re

import requests

import config
from sources.base import Item, USER_AGENT, TIMEOUT

name = "nacha"

BASE = "https://www.nacha.org"
INDEX = f"{BASE}/newrules"
SNAPSHOT = config.SNAPSHOT_DIR / "nacha.json"

NAV_SLUGS = {"archive", "new", "proposed"}

# <a href="/rules/<slug>"> ... <span class="field fieldName-title ...">Title</span> ... </a>
ENTRY_RE = re.compile(
    r'<a href="(/rules/[^"#]+)">\s*(?:<!--.*?-->\s*)*'
    r'<span class="field fieldName-title[^"]*">([^<]+)</span>',
    re.DOTALL,
)
BODY_RE = re.compile(
    r'<div class="formattedText field fieldName-body[^"]*">(.*?)</div>',
    re.DOTALL,
)
EFFECTIVE_RE = re.compile(r"effective date[^.]*?(\w+ \d{1,2}, \d{4})", re.IGNORECASE)

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


def _iso(date_text: str) -> str | None:
    m = re.match(r"(\w+) (\d{1,2}), (\d{4})", date_text.strip())
    if not m or m.group(1) not in MONTHS:
        return None
    return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"


def _strip_tags(fragment: str) -> str:
    fragment = re.sub(r"<!--.*?-->", "", fragment, flags=re.DOTALL)
    fragment = html_lib.unescape(re.sub(r"<[^>]+>", "", fragment))
    return re.sub(r"\s+", " ", fragment).strip()


def _parse(html: str) -> list[Item]:
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    items: list[Item] = []
    seen: set[str] = set()
    for m in ENTRY_RE.finditer(html):
        path, title = m.group(1), m.group(2).strip()
        slug = path.rsplit("/", 1)[-1]
        if slug in NAV_SLUGS or path in seen:
            continue
        seen.add(path)
        body = BODY_RE.search(html, m.end())
        excerpt = _strip_tags(body.group(1))[:500] if body else f"NACHA rule amendment: {title}"
        em = EFFECTIVE_RE.search(excerpt)
        date = _iso(em.group(1)) if em else None
        items.append(Item(
            id=f"nacha:{slug}",
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
