"""Classification agent: given a detected regulatory item, decide whether it
matters to OUR credit union, which business units it hits, how hard, and when.

Primary path is Bedrock (Claude). If Bedrock is unreachable or returns
garbage, a keyword heuristic produces a usable (clearly labeled) brief —
the demo never dies on a credential."""

import json
import re

import config
from sources.base import Item

PROFILE = (
    "Our institution: a state-chartered, federally insured credit union "
    "(~$2B assets) serving community districts in Central Texas. Business "
    "lines: consumer/auto/real-estate lending, share and checking accounts, ACH and "
    "wire payments, debit/credit card programs. We file information returns "
    "(1099-INT, 1099-MISC, 1098) with the IRS each year and are subject to NCUA "
    "regulation, NACHA Operating Rules, and BSA/AML requirements."
)

AREAS = ["lending", "payments", "BSA", "FOM", "ops", "tax-filing"]
BUSINESS_UNITS = ["Lending", "Payments", "BSA/Compliance", "Ops", "Accounting/Tax", "Membership"]

SYSTEM = f"""You are the regulatory-impact classifier for a credit union's risk/compliance unit.

{PROFILE}

Given one newly detected regulatory item, respond with ONLY a JSON object (no
markdown, no prose) with exactly these keys:
  "relevant": boolean — does this plausibly affect our credit union's obligations or operations?
  "areas": array drawn from {json.dumps(AREAS)}
  "business_units": array drawn from {json.dumps(BUSINESS_UNITS)} — the units that must act or be informed
  "impact_level": "LOW" | "MED" | "HIGH" — HIGH means mandatory change to our processes/systems with deadline or penalty exposure; MED means likely action needed; LOW means monitor only
  "effective_date": "YYYY-MM-DD" if the item states one, else null
  "summary": exactly 3 sentences: what changed, why it matters to us, what to do next"""


def _bedrock_classify(item: Item) -> dict:
    from agents import llm

    resp = llm.converse(
        messages=[{"role": "user", "content": [{"text": json.dumps(item.to_dict())}]}],
        system=SYSTEM,
        max_tokens=600,
        name=f"classify:{item.id}",
    )
    text = resp["output"]["message"]["content"][0]["text"]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON in model output: {text[:200]}")
    raw = json.loads(match.group(0))
    brief = _validate(raw, classification="bedrock:" + config.BEDROCK_MODEL_ID)
    llm.enrich_last_trace(
        metadata={"item_id": item.id, "source": item.source,
                  "impact_level": brief["impact_level"],
                  "business_units": brief["business_units"],
                  "effective_date": brief["effective_date"],
                  "relevant": brief["relevant"]},
        tags=[item.source, f"impact:{brief['impact_level']}"] + brief["business_units"],
    )
    return brief


def _validate(raw: dict, classification: str) -> dict:
    impact = str(raw.get("impact_level", "LOW")).upper()
    if impact not in ("LOW", "MED", "HIGH"):
        impact = "LOW"
    return {
        "relevant": bool(raw.get("relevant")),
        "areas": [a for a in raw.get("areas", []) if a in AREAS],
        "business_units": [u for u in raw.get("business_units", []) if u in BUSINESS_UNITS],
        "impact_level": impact,
        "effective_date": raw.get("effective_date") or None,
        "summary": str(raw.get("summary", "")).strip(),
        "classification": classification,
    }


HEURISTIC_UNITS = [
    (("information return", "1099", "1098", "fire", "iris", "e-file", "w-2", "tax"),
     ["Accounting/Tax", "Ops", "BSA/Compliance"], "tax-filing"),
    (("ach", "same day", "payment", "wire", "settlement", "return reason"),
     ["Payments", "Ops"], "payments"),
    (("lend", "loan", "interest rate", "mortgage", "credit card"),
     ["Lending"], "lending"),
    (("bsa", "aml", "sanction", "suspicious", "fraud", "laundering"),
     ["BSA/Compliance"], "BSA"),
    (("field of membership", "membership", "charter"),
     ["Membership"], "FOM"),
]
HEURISTIC_HIGH = ("must", "required", "retired", "penalt", "deadline", "mandatory", "no longer")


def _heuristic_classify(item: Item) -> dict:
    text = f"{item.title} {item.raw_excerpt}".lower()
    units: list[str] = []
    areas: list[str] = []
    for keywords, hit_units, area in HEURISTIC_UNITS:
        if any(k in text for k in keywords):
            units += [u for u in hit_units if u not in units]
            areas.append(area)
    relevant = bool(units) or "credit union" in text or "ncua" in text
    impact = "LOW"
    if units:
        impact = "HIGH" if sum(k in text for k in HEURISTIC_HIGH) >= 2 else "MED"
    em = re.search(r"effective[^.]*?(\d{4}-\d{2}-\d{2})", text)
    return _validate({
        "relevant": relevant,
        "areas": areas,
        "business_units": units or (["Ops"] if relevant else []),
        "impact_level": impact,
        "effective_date": em.group(1) if em else item.date,
        "summary": (f"{item.title} was detected from {item.source} (keyword heuristic; "
                    f"LLM unavailable). It appears to touch: {', '.join(areas) or 'general'}. "
                    f"A human should review the source for specifics."),
    }, classification="fallback-heuristic")


def classify(item: Item) -> dict:
    try:
        return _bedrock_classify(item)
    except Exception as exc:
        print(f"    ! bedrock unavailable ({type(exc).__name__}), using heuristic fallback")
        return _heuristic_classify(item)
