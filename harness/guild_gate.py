"""Guild control-plane wrapper for the autonomy gate (env-flagged).

When GUILDAI_ENABLED, every HIGH escalation is also sent to the published
saad~canary Guild agent for an independent second-opinion review. The review
runs in a background thread (the escalation beat must render instantly); its
disposition lands in the audit trail as a guild_review event, and the session
is visible in app.guild.ai — the governance surface.

Requires `guild auth login` to have been run once on this machine. Any
failure (CLI missing, not authed, timeout) is swallowed and audited as
unavailable — the demo never depends on it."""

import json
import re
import subprocess
import threading

import config
from harness import db
from sources.base import Item

AGENT = "saad~canary"
TIMEOUT_S = 120


def _invoke(payload: dict) -> tuple[str | None, dict | None]:
    """Returns (session_id, review dict) — Nones on failure."""
    proc = subprocess.run(
        ["guild", "chat", "--agent", AGENT, "--once", "--no-splash", json.dumps(payload)],
        capture_output=True, text=True, timeout=TIMEOUT_S,
    )
    out = proc.stdout + proc.stderr
    sm = re.search(r"Session:\s*([0-9a-f-]+)", out)
    session_id = sm.group(1) if sm else None
    review = None
    for match in re.finditer(r"\{[^{}]*\}", out):
        try:
            candidate = json.loads(match.group(0))
            if "disposition" in candidate:
                review = candidate
        except json.JSONDecodeError:
            continue
    return session_id, review


def _review_worker(item: Item, brief: dict) -> None:
    payload = {
        "item_id": item.id, "source": item.source, "title": item.title,
        "url": item.url, "impact_level": brief["impact_level"],
        "business_units": brief["business_units"],
        "effective_date": brief["effective_date"], "summary": brief["summary"],
    }
    conn = db.connect()  # own connection: sqlite objects are not thread-shareable
    try:
        session_id, review = _invoke(payload)
        if review:
            db.audit(conn, "guild_review", item.source,
                     review.get("disposition", "concur").upper(), "control-plane",
                     f"guild session {session_id or '?'}: {review.get('review_summary', '')[:200]} "
                     f"(owner: {review.get('recommended_owner', '?')})")
            print(f"    guild control plane: {review.get('disposition')} — "
                  f"session {session_id or '?'} (app.guild.ai)")
        else:
            db.audit(conn, "guild_review", item.source, "UNAVAILABLE", "control-plane",
                     "guild review returned no disposition")
    except Exception as exc:
        try:
            db.audit(conn, "guild_review", item.source, "UNAVAILABLE", "control-plane",
                     f"guild control plane unreachable: {type(exc).__name__}")
        except Exception:
            pass
    finally:
        conn.close()


def review_escalation(item: Item, brief: dict) -> None:
    """Fire-and-forget. No-op unless GUILDAI_ENABLED."""
    if not config.GUILDAI_ENABLED:
        return
    threading.Thread(target=_review_worker, args=(item, brief), daemon=False).start()
