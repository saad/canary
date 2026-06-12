"""Notification drafting agent: given a classified item, draft the short
message the owning business unit(s) actually receive — what changed, what
they must prepare, and by when. One Bedrock call through agents.llm (so it
is Langfuse-traced like every other call); a template fallback keeps the
demo alive if Bedrock is unreachable."""

import config
from sources.base import Item

SYSTEM = """You draft internal notifications for a credit union's compliance unit.
Given a regulatory change (item + impact brief as JSON), write the message sent to
the owning business unit(s). Format:

TO: <unit names>
SUBJECT: <one imperative line>
<2-4 short sentences: what changed, what this team must prepare or verify,
and the effective date / deadline if stated. Concrete and calm — no filler,
no 'per my last email', no sign-off.>

Respond with ONLY the notification text."""


def _bedrock_draft(item: Item, brief: dict) -> str:
    import json

    from agents import llm

    resp = llm.converse(
        messages=[{"role": "user", "content": [{"text": json.dumps(
            {"item": item.to_dict(), "brief": {
                "impact_level": brief["impact_level"],
                "business_units": brief["business_units"],
                "effective_date": brief["effective_date"],
                "summary": brief["summary"],
            }})}]}],
        system=SYSTEM,
        max_tokens=400,
        name=f"draft:{item.id}",
    )
    text = resp["output"]["message"]["content"][0]["text"].strip()
    if not text:
        raise ValueError("empty draft")
    llm.enrich_last_trace(
        metadata={"item_id": item.id, "source": item.source,
                  "impact_level": brief["impact_level"],
                  "business_units": brief["business_units"]},
        tags=[item.source, f"impact:{brief['impact_level']}", "notification-draft"]
        + brief["business_units"],
    )
    return text


def _template_draft(item: Item, brief: dict) -> str:
    units = ", ".join(brief["business_units"]) or "Compliance"
    effective = f" Effective: {brief['effective_date']}." if brief["effective_date"] else ""
    return (f"TO: {units}\n"
            f"SUBJECT: Action needed — {item.title}\n"
            f"{brief['summary']}{effective} "
            f"Please assess operational impact and confirm readiness to Compliance. "
            f"(template draft; LLM unavailable)")


def draft(item: Item, brief: dict) -> str:
    try:
        return _bedrock_draft(item, brief)
    except Exception as exc:
        print(f"    ! bedrock draft unavailable ({type(exc).__name__}), using template")
        return _template_draft(item, brief)
