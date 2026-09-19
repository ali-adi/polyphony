#!/bin/bash
# Refuse to let the agent stop while tests are failing. Ported from .claude/hooks/verify-before-stop.sh.
#
# Claude's version re-entrancy-guards with `stop_hook_active`; agy's Stop event has no equivalent
# flag, so this tracks its own attempt count in a per-conversation marker file and gives up after
# 2 retries rather than looping forever if tests stay broken.
INPUT=$(cat)
FULLY_IDLE=$(jq -r '.fullyIdle' <<<"$INPUT")
TERM_REASON=$(jq -r '.terminationReason' <<<"$INPUT")
ARTIFACT_DIR=$(jq -r '.artifactDirectoryPath // empty' <<<"$INPUT")
ROOT=$(jq -r '.workspacePaths[0] // empty' <<<"$INPUT")

# Only gate a clean model-initiated stop with nothing still running in the background.
if [ "$FULLY_IDLE" != "true" ] || [ "$TERM_REASON" != "model_stop" ] || [ -z "$ROOT" ]; then
  echo '{}'
  exit 0
fi

GUARD_FILE="$ARTIFACT_DIR/.verify-before-stop-attempts"
ATTEMPTS=0
[ -f "$GUARD_FILE" ] && ATTEMPTS=$(cat "$GUARD_FILE")
if [ "$ATTEMPTS" -ge 2 ]; then
  rm -f "$GUARD_FILE"
  echo '{}'
  exit 0
fi

OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT

if ! (cd "$ROOT" && ./env/bin/python -m unittest discover -s tests -t . -q) > "$OUT" 2>&1; then
  echo $((ATTEMPTS + 1)) > "$GUARD_FILE"
  TAIL=$(tail -n 60 "$OUT")
  jq -nc --arg reason "Blocked: tests are failing.
$TAIL" '{decision: "continue", reason: $reason}'
  exit 0
fi

rm -f "$GUARD_FILE"
echo '{}'
