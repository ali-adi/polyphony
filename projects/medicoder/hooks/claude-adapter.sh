#!/bin/bash
# Runs a Claude Code hook from a Cursor hook, so both tools share one copy of each rule.
# Usage: claude-adapter.sh <shell|file|stop> <Claude hook script>
# Exit 1 on anything unexpected; hooks.json sets failClosed so Cursor blocks instead of proceeding.
MODE=$1
HOOK=$2
INPUT=$(cat)
ROOT=$(jq -r '.workspace_roots[0] // empty' <<< "$INPUT")
export CLAUDE_PROJECT_DIR=${CURSOR_PROJECT_DIR:-${ROOT:-$PWD}}

case $MODE in
  shell)
    PAYLOAD=$(jq -c '{tool_input: {command: (.command // .tool_input.command // "")}}' <<< "$INPUT")
    ;;
  file)
    # Cursor doesn't document the Write/Delete input shape, so try the likely names and
    # refuse rather than wave the edit through if none is present.
    FILE_PATH=$(jq -r '.tool_input.file_path // .tool_input.path // .tool_input.target_file // .file_path // empty' <<< "$INPUT")
    if [ -z "$FILE_PATH" ]; then
      MSG="Blocked: couldn't find the file path in this $(jq -r '.tool_name' <<< "$INPUT") call, so the database guard can't check it. Input keys: $(jq -c '.tool_input | keys? // []' <<< "$INPUT")"
      jq -n --arg m "$MSG" '{permission: "deny", user_message: $m, agent_message: $m}'
      exit 0
    fi
    PAYLOAD=$(jq -nc --arg p "$FILE_PATH" '{tool_input: {file_path: $p}}')
    ;;
  stop)
    [ "$(jq -r '.status' <<< "$INPUT")" = completed ] || { echo '{}'; exit 0; }
    PAYLOAD='{"stop_hook_active": false}'
    ;;
  *)
    echo "claude-adapter.sh: unknown mode $MODE" >&2
    exit 1
    ;;
esac

ERR=$("$HOOK" 2>&1 > /dev/null <<< "$PAYLOAD")
CODE=$?

if [ $CODE -eq 2 ]; then
  if [ "$MODE" = stop ]; then
    jq -n --arg m "$ERR" '{followup_message: ($m + "\n\nFix this before finishing.")}'
  else
    jq -n --arg m "$ERR" '{permission: "deny", user_message: $m, agent_message: $m}'
  fi
  exit 0
fi
if [ $CODE -ne 0 ]; then
  echo "claude-adapter.sh: $HOOK exited $CODE: $ERR" >&2
  exit 1
fi
[ "$MODE" = stop ] && echo '{}' || echo '{"permission": "allow"}'
