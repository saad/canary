"""Federal Register adapter — live, free JSON API.
Two queries (NCUA agency filter + credit-union/payments term search),
merged and deduped on document_number."""

import requests

from sources.base import Item, USER_AGENT, TIMEOUT

name = "federal_register"

API = "https://www.federalregister.gov/api/v1/documents.json"
FIELDS = ["document_number", "title", "publication_date", "html_url", "abstract"]
TERMS = '"credit union" OR NCUA OR "ACH payments" OR "share insurance"'


def _query(conditions: dict) -> list[dict]:
    params: list[tuple[str, str]] = [
        ("per_page", "10"),
        ("order", "newest"),
    ]
    params += [("fields[]", f) for f in FIELDS]
    params += [(k, v) for k, v in conditions.items()]
    resp = requests.get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("results", [])


def fetch_latest() -> list[Item]:
    results: dict[str, dict] = {}
    for conditions in (
        {"conditions[agencies][]": "national-credit-union-administration"},
        {"conditions[term]": TERMS},
    ):
        try:
            for doc in _query(conditions):
                results.setdefault(doc["document_number"], doc)
        except Exception:
            continue

    items = [
        Item(
            id=f"fedreg:{doc['document_number']}",
            source=name,
            title=doc.get("title", "").strip(),
            date=doc.get("publication_date"),
            url=doc.get("html_url", ""),
            raw_excerpt=(doc.get("abstract") or "")[:500],
        )
        for doc in results.values()
    ]
    items.sort(key=lambda i: i.date or "", reverse=True)
    return items
