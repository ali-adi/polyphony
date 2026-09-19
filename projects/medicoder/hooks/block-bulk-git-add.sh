#!/bin/bash
# Cursor has no repo-level deny list, so this mirrors the git add/commit denies in
# .claude/settings.json: stage files by name, never in bulk.
COMMAND=$(jq -r '.tool_input.command // empty')
if grep -qE '(^|[;&|[:space:]])git[[:space:]]+(add[[:space:]]+(-A|--all|-u|--update|\.)([[:space:]]|$|[;&|])|commit[[:space:]]+(-a|-am|--all)([[:space:]]|$|[;&|]))' <<< "$COMMAND"; then
  echo "Blocked: stage files by name (git add <files>); bulk git add -A/-u/. and git commit -a aren't allowed." >&2
  exit 2
fi
exit 0
