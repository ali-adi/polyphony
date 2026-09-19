#!/bin/bash
# Resolve ".." and compare case-insensitively (APFS is case-insensitive), so tests/../Database/x
# can't slip past. Ported from .claude/hooks/protect-databases.sh: agy has no $CLAUDE_PROJECT_DIR
# env var, so the workspace root comes from the hook's own stdin payload instead.
INPUT=$(cat)
TARGET_FILE=$(jq -r '.toolCall.args.TargetFile // empty' <<<"$INPUT")
ROOT=$(jq -r '.workspacePaths[0] // empty' <<<"$INPUT")

if [ -z "$TARGET_FILE" ] || [ -z "$ROOT" ]; then
  echo '{"decision": "allow"}'
  exit 0
fi

REL=$(python3 -c 'import os, sys; print(os.path.relpath(os.path.normpath(os.path.join(sys.argv[2], sys.argv[1])), sys.argv[2]).lower())' "$TARGET_FILE" "$ROOT")

if [[ "$REL" != ../* && ( "$REL" == database/* || "$REL" == */database/* ) ]]; then
  jq -nc --arg reason "Blocked: $TARGET_FILE is a versioned taxonomy snapshot built outside this repo. Don't edit or overwrite anything under database/." \
    '{decision: "deny", reason: $reason}'
  exit 0
fi

echo '{"decision": "allow"}'
