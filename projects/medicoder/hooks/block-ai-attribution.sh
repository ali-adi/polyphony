#!/bin/bash
# This work is presented as the user's own: no AI attribution in commits or PRs, ever.
# Ported from .claude/hooks/block-ai-attribution.sh (agy PreToolUse schema).
INPUT=$(cat)
COMMAND=$(jq -r '.toolCall.args.CommandLine // empty' <<<"$INPUT")

if echo "$COMMAND" | grep -qE 'git commit|gh pr (create|edit)' \
   && echo "$COMMAND" | grep -qiE 'co-authored-by|generated with|claude-session'; then
  jq -nc '{decision: "deny", reason: "Blocked: attribution lines (Co-Authored-By / Generated with / Claude-Session) are not allowed in this repo."}'
  exit 0
fi

echo '{"decision": "allow"}'
