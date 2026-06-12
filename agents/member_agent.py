"""Natural-language FOM agent: answers "Can we serve a member at <address>?"
by letting Bedrock call the verify_membership tool, then explaining the
decision with its evidence chain. If Bedrock is down, a template answer is
built straight from the tool result — the question still gets answered.

  uv run python -m agents.member_agent "Can we serve a member at 301 W 2nd St, Austin?"
"""

import json
import sys

import config
from agents import fom

TOOL_SPEC = {
    "toolSpec": {
        "name": "verify_membership",
        "description": ("Verify whether an address is inside the credit union's "
                        "field of membership. Geocodes the address, checks the "
                        "county against chartered districts, and returns "
                        "ELIGIBLE / NOT_ELIGIBLE / UNVERIFIABLE with an evidence chain."),
        "inputSchema": {"json": {
            "type": "object",
            "properties": {"address": {"type": "string", "description": "postal address to verify"}},
            "required": ["address"],
        }},
    }
}

SYSTEM = (
    f"You are the membership-eligibility assistant for a {fom.FOM_REGION} "
    "credit union. When asked whether someone at an address can become a member, "
    "ALWAYS call verify_membership with the address, then answer in 2-3 plain "
    "sentences: the eligibility decision, which county/district drove it, and any "
    "caveat from the evidence (e.g. partial geocode match). Mention that the full "
    "evidence chain is logged for compliance. Eligibility is based on living, "
    "working, worshiping, or attending school in a chartered county, so phrase "
    "decisions accordingly."
)


def _template_answer(question: str, result: dict) -> str:
    county = result.get("county") or "an unknown county"
    status = result["status"]
    if status == "ELIGIBLE":
        return (f"Yes — the address resolves to {county}, which is inside our field of "
                f"membership, so we can serve a member there. Full evidence chain logged. "
                f"(LLM unavailable; template answer from verified tool result.)")
    if status == "NOT_ELIGIBLE":
        return (f"No — the address resolves to {county}, which is outside our chartered "
                f"districts. Full evidence chain logged. "
                f"(LLM unavailable; template answer from verified tool result.)")
    return ("Unable to verify — the address did not resolve to a real place with any "
            "geocoder, so eligibility cannot be determined. Evidence chain logged. "
            "(LLM unavailable; template answer from verified tool result.)")


def answer(question: str) -> dict:
    """Returns {'answer': str, 'tool_result': dict | None}."""
    tool_result = None
    try:
        from agents import llm
        messages = [{"role": "user", "content": [{"text": question}]}]
        for _ in range(4):  # question -> toolUse -> toolResult -> final text
            resp = llm.converse(
                messages=messages,
                system=SYSTEM,
                tool_config={"tools": [TOOL_SPEC]},
                max_tokens=500,
                name="member-agent",
            )
            msg = resp["output"]["message"]
            messages.append(msg)
            tool_uses = [c["toolUse"] for c in msg["content"] if "toolUse" in c]
            if not tool_uses:
                text = " ".join(c["text"] for c in msg["content"] if "text" in c).strip()
                return {"answer": text, "tool_result": tool_result}
            tool_contents = []
            for tu in tool_uses:
                tool_result = fom.verify_membership(tu["input"]["address"])
                tool_contents.append({"toolResult": {
                    "toolUseId": tu["toolUseId"],
                    "content": [{"json": tool_result}],
                }})
            messages.append({"role": "user", "content": tool_contents})
        raise RuntimeError("tool loop did not converge")
    except Exception as exc:
        print(f"    ! bedrock unavailable ({type(exc).__name__}), using template answer")
        if tool_result is None:
            # Best effort: treat everything after 'at ' as the address, else whole question.
            address = question.split(" at ", 1)[-1].rstrip("?").strip()
            tool_result = fom.verify_membership(address)
        return {"answer": _template_answer(question, tool_result), "tool_result": tool_result}


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Can we serve a member at 301 W 2nd Street, Austin, TX 78701?"
    out = answer(question)
    print(f"\nQ: {question}\nA: {out['answer']}")
    if out["tool_result"]:
        print("\nEvidence chain:")
        print(fom.format_evidence(out["tool_result"]))
