"""Canary demo server: serves the dashboard, the JSON API, and runs the
detection loop in a background thread — one command is the whole demo:

  uv run python -m harness.server [--port 8400] [--interval 15]

Escalations land as 'awaiting review' (the dashboard acknowledge button
closes them out and writes the audit event)."""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config
from harness import cases, db, poller, clickhouse
from sources import injector

DASHBOARD = Path(__file__).parent / "dashboard.html"
UI_DIST = Path(__file__).parent.parent / "ui" / "dist"
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript",
        ".css": "text/css", ".svg": "image/svg+xml", ".ico": "image/x-icon",
        ".png": "image/png", ".woff2": "font/woff2", ".map": "application/json"}


def _feed() -> list[dict]:
    conn = db.connect()
    try:
        return db.feed(conn)
    finally:
        conn.close()


def _audit(backend: str) -> dict:
    if backend == "clickhouse" and clickhouse.enabled():
        rows = clickhouse.query_json(
            "SELECT ts, action, source, decision, autonomy_level, reason "
            "FROM canary_audit_events ORDER BY ts DESC LIMIT 200", timeout=4)
        if rows:
            return {"backend": "clickhouse", "rows": rows}
    conn = db.connect()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT ts, action, source, decision, autonomy_level, reason "
            "FROM audit_events ORDER BY ts DESC LIMIT 200")]
        return {"backend": "sqlite", "rows": rows}
    finally:
        conn.close()


def _status() -> dict:
    conn = db.connect()
    try:
        seen = conn.execute("SELECT COUNT(*) FROM items_seen").fetchone()[0]
        briefs = conn.execute("SELECT COUNT(*) FROM briefs").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM briefs WHERE escalated = 1").fetchone()[0]
    finally:
        conn.close()
    conn2 = db.connect()
    try:
        cases.ensure(conn2)
        open_cases = conn2.execute(
            "SELECT COUNT(*) FROM cases WHERE status != 'CLOSED'").fetchone()[0]
    finally:
        conn2.close()
    poll = {}
    try:
        poll = json.loads(poller.POLL_STATUS_FILE.read_text())
    except Exception:
        pass
    return {
        "items_seen": seen, "briefs": briefs, "pending_escalations": pending,
        "open_cases": open_cases, "poll": poll,
        "clickhouse": clickhouse.enabled(), "langfuse": config.LANGFUSE_ENABLED,
        "guild": config.GUILDAI_ENABLED, "thesys": bool(config.THESYS_API_KEY),
        "model": config.BEDROCK_MODEL_ID,
    }


def _case_payload(case: dict) -> dict:
    """Case data shaped for the UI and for C1 prop-filling: the draft memo is
    pre-parsed so rendering never depends on the model splitting text."""
    drafted = [e for e in case["timeline"] if e["action"] == "drafted"]
    # pending until a draft exists — covers the just-detected case the officer
    # clicks before triage finishes (shimmer, never an empty memo)
    draft = {"pending": not drafted, "to": [], "subject": "", "body": ""}
    if drafted:
        lines = drafted[-1]["note"].splitlines()
        body: list[str] = []
        for line in lines:
            if line.upper().startswith("TO:"):
                draft["to"] = [u.strip() for u in line[3:].split(",") if u.strip()]
            elif line.upper().startswith("SUBJECT:"):
                draft["subject"] = line[8:].strip()
            elif line.strip():
                body.append(line.strip())
        draft["body"] = "\n\n".join(body)
    case = dict(case)
    case["draft"] = draft
    case["owner_units"] = [u for u in (case.get("owner_units") or "").split(",") if u]
    return case


def _cases_list() -> list[dict]:
    conn = db.connect()
    try:
        return [_case_payload(c) for c in cases.queue(conn)]
    finally:
        conn.close()


def _case_get(case_id: int) -> dict | None:
    conn = db.connect()
    try:
        case = cases.get(conn, case_id)
        return _case_payload(case) if case else None
    finally:
        conn.close()


def _case_approve(case_id: int) -> dict:
    conn = db.connect()
    try:
        case = cases.get(conn, case_id)
        if case is None:
            return {"error": f"no case {case_id}"}
        if case["status"] != "TRIAGED" or case["impact_level"] != "HIGH":
            return {"error": f"approve requires HIGH at TRIAGED (is {case['impact_level']} {case['status']})"}
        payload = _case_payload(case)
        draft_text = ""
        if not payload["draft"]["pending"]:
            d = payload["draft"]
            draft_text = f"TO: {', '.join(d['to'])}\nSUBJECT: {d['subject']}\n{d['body']}"
        from harness import notify
        delivery = notify.publish(case.get("title") or case["item_id"], "HIGH",
                                  payload["owner_units"], draft_text, case_id)
        if delivery:
            state = "DELIVERED" if delivery["ok"] else "FAILED"
            cases.record(conn, case_id, "agent", "published",
                         f"notification {state.lower()} via {delivery['detail']}")
            db.audit(conn, "publish", case.get("source") or "?", state, "human-in-loop",
                     f"case #{case_id} owner notification via {delivery['detail']} (human-approved)")
        cases.transition(conn, case_id, "NOTIFIED", "human",
                         "Approve & Notify — compliance officer approved the draft; owners notified")
        db.mark_acknowledged(conn, case["item_id"])
        db.audit(conn, "acknowledge", case.get("source") or "?", "ACKNOWLEDGED",
                 "human-in-loop",
                 f"compliance officer approved case #{case_id} ({case['item_id']}) via dashboard")
        return {"ok": True, "case": _case_payload(cases.get(conn, case_id))}
    finally:
        conn.close()


def _case_update(case_id: int, note: str) -> dict:
    conn = db.connect()
    try:
        case = cases.add_update(conn, case_id, "human", note or "update noted")
        return {"ok": True, "case": _case_payload(case)}
    finally:
        conn.close()


def _case_close(case_id: int, note: str) -> dict:
    conn = db.connect()
    try:
        case = cases.transition(conn, case_id, "CLOSED", "human",
                                note or "closed by compliance officer")
        return {"ok": True, "case": _case_payload(case)}
    finally:
        conn.close()


C1_COMPONENT_SCHEMAS = {
    "ImpactBrief": {
        "type": "object",
        "description": "The impact assessment header for a regulatory case: what "
                       "changed and why it matters to this credit union.",
        "properties": {
            "title": {"type": "string"},
            "source": {"type": "string", "description": "item source key, e.g. irs, ncua, nacha, federal_register"},
            "impactLevel": {"type": "string", "enum": ["LOW", "MED", "HIGH"]},
            "effectiveDate": {"type": ["string", "null"]},
            "summary": {"type": "string"},
            "url": {"type": ["string", "null"]},
        },
        "required": ["title", "source", "impactLevel", "summary"],
    },
    "DraftMemo": {
        "type": "object",
        "description": "The agent-drafted owner notification, shown as an internal "
                       "memo. If pending is true the draft is still being written.",
        "properties": {
            "pending": {"type": "boolean"},
            "to": {"type": "array", "items": {"type": "string"}},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["pending"],
    },
    "CaseTimeline": {
        "type": "object",
        "description": "Vertical case timeline. Every entry is labeled with its "
                       "actor: 'agent' or 'human'.",
        "properties": {
            "entries": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "ts": {"type": "string"},
                    "actor": {"type": "string", "enum": ["agent", "human"]},
                    "action": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["ts", "actor", "action"],
            }},
        },
        "required": ["entries"],
    },
    "RecommendedActions": {
        "type": "object",
        "description": "The case CLOSE-OUT CHECKLIST you derive: 3-5 short, "
                       "verifiable conditions that must be TRUE before a compliance "
                       "officer may close this case — the acceptance criteria an "
                       "NCUA examiner would check. Do NOT restate the notification's "
                       "to-dos; state the verifiable end-state (e.g. 'IRIS TCC "
                       "received and recorded', not 'apply for a TCC'). Each tied "
                       "to the owner unit accountable for evidencing it.",
        "properties": {
            "items": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "one verifiable end-state condition, ≤14 words"},
                    "owner": {"type": "string", "description": "one of the case's owner units"},
                    "deadline": {"type": "string", "description": "if the case states one, e.g. '2026-06-19'; omit otherwise"},
                },
                "required": ["action", "owner"],
            }},
        },
        "required": ["items"],
    },
    "CaseActions": {
        "type": "object",
        "description": "The pinned action bar for the case: Approve & Notify "
                       "(HIGH at TRIAGED only), Add Update, Close Case.",
        "properties": {
            "caseId": {"type": "integer"},
            "status": {"type": "string"},
            "impactLevel": {"type": "string"},
        },
        "required": ["caseId", "status", "impactLevel"],
    },
}

C1_CASE_SYSTEM = """You compose the case workspace panel for Canary, a credit
union compliance case manager. You are given one case as JSON. Build the
workspace using ONLY the provided custom components, in this order:
ImpactBrief, DraftMemo, RecommendedActions, CaseTimeline, CaseActions.
Fill ImpactBrief, DraftMemo, CaseTimeline and CaseActions props verbatim
from the case JSON (the pre-parsed `draft` object maps to DraftMemo;
`timeline` maps to CaseTimeline entries; use the case `id` for caseId).
RecommendedActions is the one component where you generate content: the
close-out checklist — 3-5 verifiable end-state conditions (per its schema
description) that must hold before the case may be closed, each owned by one
of the case's owner units, deadlines anchored to the effective date when
stated. Never restate the notification's instructions. If the case has no
impact classification yet, use an empty items array. Do not add other
components, no follow-up questions."""


def _trace_c1(name: str, case: dict, content: str, usage: dict,
              start: str, end: str) -> None:
    """Langfuse trace for a Thesys C1 generation — same trace stream as the
    Bedrock calls so the whole pipeline is observable in one place."""
    if not (config.LANGFUSE_ENABLED and config.LANGFUSE_PUBLIC_KEY):
        return
    import uuid
    from agents import llm
    trace_id = str(uuid.uuid4())
    llm._post_langfuse([
        {"id": str(uuid.uuid4()), "type": "trace-create", "timestamp": start,
         "body": {"id": trace_id, "name": name, "timestamp": start,
                  "input": {"case_id": case.get("id"), "item_id": case.get("item_id"),
                            "status": case.get("status"), "impact": case.get("impact_level")},
                  "output": content[:2000],
                  "metadata": {"component_library": list(C1_COMPONENT_SCHEMAS)},
                  "tags": ["canary", "thesys-c1", f"impact:{case.get('impact_level')}"]}},
        {"id": str(uuid.uuid4()), "type": "generation-create", "timestamp": end,
         "body": {"id": str(uuid.uuid4()), "traceId": trace_id, "name": name,
                  "model": "c1/anthropic/claude-sonnet-4.6/v-20260331",
                  "input": {"case_id": case.get("id")}, "output": content[:2000],
                  "usage": {"input": usage.get("prompt_tokens", 0),
                            "output": usage.get("completion_tokens", 0)},
                  "startTime": start, "endTime": end}},
    ])


_C1_CACHE_FILE = config.DATA_DIR / "c1_cache.json"


def _c1_cache_load() -> dict:
    try:
        return json.loads(_C1_CACHE_FILE.read_text())
    except Exception:
        return {}


_c1_cache: dict = _c1_cache_load()  # "item_id|status|timeline_len" → {"c1": spec}


def _c1_cache_put(key: str, val: dict) -> None:
    _c1_cache[key] = val
    try:
        _C1_CACHE_FILE.write_text(json.dumps(_c1_cache))
    except Exception:
        pass  # cache is an optimization, never a failure


def _c1_case(case_id: int) -> dict:
    case = _case_get(case_id)
    if case is None:
        return {"error": f"no case {case_id}"}
    if not config.THESYS_API_KEY or config.C1_DISABLED:
        return {"error": "C1 disabled or no key", "fallback": case}
    # We cache the COMPOSITION, not the facts — components render live DB
    # data. Keyed by item_id (not case id) so the cache survives resets;
    # invalidates whenever the case advances.
    key = f"{case['item_id']}|{case['status']}|{len(case['timeline'])}"
    if key in _c1_cache:
        return {**_c1_cache[key], "case": case}
    import time as _time
    t0 = _time.time()
    try:
        import requests
        from agents.llm import _now_iso
        start_iso = _now_iso()
        resp = requests.post(
            "https://api.thesys.dev/v1/embed/chat/completions",
            headers={"Authorization": f"Bearer {config.THESYS_API_KEY}"},
            json={
                "model": "c1/anthropic/claude-sonnet-4.6/v-20260331",
                "messages": [
                    {"role": "system", "content": C1_CASE_SYSTEM},
                    {"role": "user", "content": json.dumps(case, default=str)},
                ],
                "metadata": {"thesys": json.dumps(
                    {"c1_custom_components": C1_COMPONENT_SCHEMAS})},
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        try:
            _trace_c1(f"c1-workspace:case-{case_id}", case, content,
                      data.get("usage", {}), start_iso, _now_iso())
        except Exception:
            pass
        print(f"    ✨ C1 workspace case #{case_id} generated in {_time.time() - t0:.1f}s (cached)")
        _c1_cache_put(key, {"c1": content})
        return {"c1": content, "case": case}
    except Exception as exc:
        detail = ""
        if hasattr(exc, "response") and getattr(exc.response, "text", None):
            detail = exc.response.text[:200]
        return {"error": f"{type(exc).__name__}: {detail or exc}", "fallback": case}


def _ack(item_id: str) -> dict:
    conn = db.connect()
    try:
        db.mark_acknowledged(conn, item_id)
        row = conn.execute("SELECT source FROM items_meta WHERE id = ?", (item_id,)).fetchone()
        db.audit(conn, "acknowledge", row["source"] if row else "?", "ACKNOWLEDGED",
                 "human-in-loop", f"compliance officer acknowledged {item_id} via dashboard")
        return {"ok": True}
    finally:
        conn.close()


def _fom(question: str) -> dict:
    from agents import member_agent
    return member_agent.answer(question)


def _c1_brief() -> dict:
    """Thesys C1 generative-UI morning brief from the live feed. Returns
    {"c1": <spec>} or {"error", "fallback": rows} — the dashboard renders a
    plain-HTML brief from `fallback` when C1 is unavailable."""
    rows = _feed()[:12]
    data = [{
        "title": r.get("title") or r["item_id"], "impact": r["impact_level"],
        "units": (r.get("business_units") or "").split(","),
        "effective": r.get("effective_date"), "summary": r.get("summary"),
        "source": (r.get("item_id") or "").split(":")[0],
        "escalation": {0: "none", 1: "AWAITING REVIEW", 2: "acknowledged"}.get(int(r.get("escalated") or 0)),
    } for r in rows]
    if not config.THESYS_API_KEY:
        return {"error": "THESYS_API_KEY not set", "fallback": data}
    try:
        import requests
        resp = requests.post(
            "https://api.thesys.dev/v1/embed/chat/completions",
            headers={"Authorization": f"Bearer {config.THESYS_API_KEY}"},
            json={
                "model": "c1/anthropic/claude-sonnet-4.6/v-20260331",
                "messages": [
                    {"role": "system", "content":
                        "You generate the morning regulatory brief UI for a credit union "
                        "compliance team. Given today's detected items as JSON, produce a "
                        "compact dashboard: a headline stat row (total items, HIGH count, "
                        "pending escalations), a prioritized list grouped by impact with "
                        "business-unit tags and effective dates, and a callout card for any "
                        "item awaiting review. Dark-theme friendly. No follow-up questions."},
                    {"role": "user", "content": json.dumps(data)},
                ],
            },
            timeout=45,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return {"c1": content}
    except Exception as exc:
        detail = ""
        if hasattr(exc, "response") and getattr(exc.response, "text", None):
            detail = exc.response.text[:160]
        return {"error": f"{type(exc).__name__}: {detail or exc}", "fallback": data}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console clean for the poller narration
        pass

    def _json(self, payload, code=200):
        body = json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, fp: Path) -> None:
        body = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(fp.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            index = UI_DIST / "index.html"
            self._file(index if index.exists() else DASHBOARD)
        elif path == "/legacy":
            self._file(DASHBOARD)
        elif (path.startswith("/assets/") or path.endswith((".svg", ".ico", ".png"))) and ".." not in path:
            fp = UI_DIST / path.lstrip("/")
            if fp.is_file():
                self._file(fp)
            else:
                self._json({"error": "not found"}, 404)
        elif path == "/api/cases":
            self._json(_cases_list())
        elif path.startswith("/api/case/"):
            case = _case_get(int(path.rsplit("/", 1)[1]))
            self._json(case if case else {"error": "not found"}, 200 if case else 404)
        elif path == "/api/feed":
            self._json(_feed())
        elif path == "/api/audit":
            backend = "clickhouse" if "backend=clickhouse" in self.path else \
                      ("clickhouse" if clickhouse.enabled() else "sqlite")
            if "backend=sqlite" in self.path:
                backend = "sqlite"
            self._json(_audit(backend))
        elif path == "/api/status":
            self._json(_status())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            payload = {}
        try:
            if self.path == "/api/ack":
                self._json(_ack(payload.get("item_id", "")))
            elif self.path == "/api/case/approve":
                self._json(_case_approve(int(payload["id"])))
            elif self.path == "/api/case/update":
                self._json(_case_update(int(payload["id"]), str(payload.get("note", ""))))
            elif self.path == "/api/case/close":
                self._json(_case_close(int(payload["id"]), str(payload.get("note", ""))))
            elif self.path == "/api/c1case":
                self._json(_c1_case(int(payload["id"])))
            elif self.path == "/api/inject":
                item = injector.inject(payload.get("payload"))
                self._json({"ok": True, "title": item.title})
            elif self.path == "/api/fom":
                self._json(_fom(payload.get("question", "")))
            elif self.path == "/api/c1brief":
                self._json(_c1_brief())
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8400)
    parser.add_argument("--interval", type=int, default=config.POLL_SECONDS)
    args = parser.parse_args()

    threading.Thread(target=poller.run, kwargs={"interval": args.interval, "ack_mode": "pending"},
                     daemon=True).start()
    clickhouse.keep_warm()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"🐤 Canary dashboard → http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
