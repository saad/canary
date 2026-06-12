"""Single Bedrock entry point. Every converse() call in the codebase goes
through here, so Langfuse tracing (env-flagged, REST ingestion — no SDK
dependency) wraps all LLM usage in one place. The trace POST is synchronous
(~0.2s next to a multi-second LLM call) so short-lived scripts can't drop
traces; failures are swallowed — observability must never break the demo."""

import json
import uuid
from datetime import datetime, timezone

import config

_client = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _post_langfuse(batch: list[dict]) -> None:
    try:
        import requests
        requests.post(
            f"{config.LANGFUSE_HOST}/api/public/ingestion",
            json={"batch": batch},
            auth=(config.LANGFUSE_PUBLIC_KEY, config.LANGFUSE_SECRET_KEY),
            timeout=10,
        )
    except Exception:
        pass


_last_trace_id: str | None = None


def enrich_last_trace(metadata: dict, tags: list[str] | None = None) -> None:
    """Attach post-hoc metadata (impact level, business units…) to the most
    recent trace — Langfuse upserts trace bodies by id."""
    if not (config.LANGFUSE_ENABLED and config.LANGFUSE_PUBLIC_KEY and _last_trace_id):
        return
    now = _now_iso()
    _post_langfuse([{
        "id": str(uuid.uuid4()), "type": "trace-create", "timestamp": now,
        "body": {"id": _last_trace_id, "metadata": metadata,
                 "tags": ["canary", "bedrock"] + (tags or [])},
    }])


def _trace(name: str, input_payload, output_payload, usage: dict,
           start: str, end: str) -> None:
    global _last_trace_id
    if not (config.LANGFUSE_ENABLED and config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_HOST):
        return
    trace_id = str(uuid.uuid4())
    _last_trace_id = trace_id
    batch = [
        {"id": str(uuid.uuid4()), "type": "trace-create", "timestamp": start,
         "body": {"id": trace_id, "name": name, "timestamp": start,
                  "input": input_payload, "output": output_payload,
                  "tags": ["canary", "bedrock"]}},
        {"id": str(uuid.uuid4()), "type": "generation-create", "timestamp": end,
         "body": {"id": str(uuid.uuid4()), "traceId": trace_id, "name": name,
                  "model": config.BEDROCK_MODEL_ID,
                  "input": input_payload, "output": output_payload,
                  "usage": {"input": usage.get("inputTokens", 0),
                            "output": usage.get("outputTokens", 0)},
                  "startTime": start, "endTime": end}},
    ]
    _post_langfuse(batch)


def converse(messages: list[dict], system: str | None = None,
             tool_config: dict | None = None, max_tokens: int = 600,
             temperature: float = 0.1, name: str = "bedrock-call") -> dict:
    global _client
    if _client is None:
        import boto3
        _client = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)

    kwargs = {
        "modelId": config.BEDROCK_MODEL_ID,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    if tool_config:
        kwargs["toolConfig"] = tool_config

    start = _now_iso()
    resp = _client.converse(**kwargs)
    end = _now_iso()

    try:
        input_payload = {"system": (system or "")[:2000],
                         "messages": json.loads(json.dumps(messages, default=str))}
        _trace(name, input_payload, resp["output"]["message"], resp.get("usage", {}), start, end)
    except Exception:
        pass
    return resp
