"""Step 1 done-criteria demo: fetch every source live, print to console,
exercise the injector, and confirm the SQLite schema exists."""

from sources import federal_register, ncua, nacha, irs, injector
from harness import db


def show(adapter) -> None:
    items = adapter.fetch_latest()
    print(f"\n=== {adapter.name} — {len(items)} items ===")
    for item in items[:6]:
        print(f"  [{item.source}] {item.date or '????-??-??'}  {item.title}")
        print(f"      {item.url}")


def main() -> None:
    for adapter in (federal_register, ncua, nacha, irs):
        show(adapter)

    print("\n=== injector ===")
    injected = injector.inject()
    print(f"  queued: {injected.title}")
    drained = injector.fetch_latest()
    print(f"  fetch_latest() drained {len(drained)} item(s): [{drained[0].source}] {drained[0].title}")

    conn = db.connect()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print(f"\n=== sqlite ===\n  tables: {', '.join(tables)}")
    conn.close()


if __name__ == "__main__":
    main()
