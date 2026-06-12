"""Shared source-adapter interface: every adapter exposes
fetch_latest() -> list[Item] and never raises out of it."""

from dataclasses import dataclass, asdict
from typing import Protocol

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
TIMEOUT = 10


@dataclass
class Item:
    id: str
    source: str          # "federal_register" | "ncua" | "irs"
    title: str
    date: str | None     # ISO yyyy-mm-dd when known
    url: str
    raw_excerpt: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(**{k: d.get(k) for k in ("id", "source", "title", "date", "url", "raw_excerpt")})


class SourceAdapter(Protocol):
    name: str

    def fetch_latest(self) -> list[Item]: ...
