#!/usr/bin/env bash
# Restart a Sunny service and say so FIRST.
#
# A restart and a crash are indistinguishable from inside the process that
# comes back, so the distinction has to be recorded before the restart, by
# whoever is doing it. Use this instead of `systemctl restart` and a deploy
# stops looking like an incident.
#
#   ./restart-sunny.sh                 # sunny.service, reason "deploy"
#   ./restart-sunny.sh sunny "config change"
set -euo pipefail

SERVICE="${1:-sunny}"
REASON="${2:-deploy}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$ROOT/logs"
printf '%s\n%s\n' "$(date -Iseconds)" "$REASON" > "$ROOT/logs/${SERVICE}.restarting"

sudo systemctl restart "${SERVICE}.service"

# Wait for it rather than returning immediately -- "restarted" that turns
# out to mean "failed to start" is worse than no message at all.
for _ in $(seq 1 20); do
    sleep 1
    if systemctl is-active --quiet "${SERVICE}.service"; then
        echo "${SERVICE}.service restarted (${REASON})"
        exit 0
    fi
done

echo "${SERVICE}.service did NOT come back — check: journalctl -u ${SERVICE}.service -n 50" >&2
exit 1
