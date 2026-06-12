#!/bin/sh
# One-command demo reset: fresh DB, seeded lifecycle cases, server up.
#   ./scripts/demo_reset.sh            (poll interval via DEMO_POLL_SECONDS, default 10)
cd "$(dirname "$0")/.." || exit 1
pkill -f harness.server 2>/dev/null
sleep 1
rm -f data/canary.db data/inject_queue.json data/injected_at.json data/poll_status.json
uv run python -m harness.backfill
echo "demo trigger:  uv run python -m harness.redetect"
exec env PYTHONUNBUFFERED=1 uv run python -m harness.server "$@"
