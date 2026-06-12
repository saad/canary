"""Real outbound delivery of owner notifications — the agent's publish
action, via SMTP email (env-configured). No credentials configured →
returns None and the pipeline records the draft only (demo never breaks
on a missing credential)."""

import config


def channel() -> str | None:
    if config.SMTP_HOST and config.SMTP_USER and config.NOTIFY_EMAIL_TO:
        return "email"
    return None


def _email(title: str, impact: str, units: list[str], draft: str, case_id: int) -> str:
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = f"[Canary {impact}] {title}"
    msg["From"] = config.SMTP_USER
    msg["To"] = config.NOTIFY_EMAIL_TO
    msg.set_content(f"Owners: {', '.join(units) or '-'}\nCanary case #{case_id}\n\n{draft}")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
        s.starttls()
        s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        s.send_message(msg)
    return f"email to {config.NOTIFY_EMAIL_TO}"


def publish(title: str, impact: str, units: list[str], draft: str, case_id: int) -> dict | None:
    """Deliver for real. Returns {channel, ok, detail} or None if unconfigured."""
    if channel() is None:
        return None
    try:
        return {"channel": "email", "ok": True,
                "detail": _email(title, impact, units, draft, case_id)}
    except Exception as exc:
        return {"channel": "email", "ok": False, "detail": f"{type(exc).__name__}: {exc}"}
