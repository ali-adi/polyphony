#!/bin/bash
# Guard rail for read-only database access. `sqlite3 -safe -readonly` is the real guarantee:
# -readonly stops writes to the database, and -safe stops writefile(), .backup, .shell and the
# other CLI features that write elsewhere. REPLACE is deliberately absent from the keyword list:
# the flags already stop REPLACE INTO, and the keyword would block the replace() function.
#
# Ported from .claude/hooks/validate-readonly-query.sh, which was wired to a specific db-reader
# subagent in Claude Code. agy hooks match by tool name only (no per-subagent scoping), so this
# version only inspects commands that actually invoke sqlite3, to avoid misfiring on unrelated
# commands (e.g. `git commit -m "insert new feature"`) the way an unconditional keyword grep
# would across all Bash commands.
INPUT=$(cat)
COMMAND=$(jq -r '.toolCall.args.CommandLine // empty' <<<"$INPUT")

if ! grep -qw 'sqlite3' <<<"$COMMAND"; then
  echo '{"decision": "allow"}'
  exit 0
fi

if grep -qiwE 'INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|ATTACH|VACUUM' <<<"$COMMAND"; then
  jq -nc '{decision: "deny", reason: "Blocked: only read queries are allowed against the taxonomy databases."}'
  exit 0
fi

# Count invocations rather than grepping for the flags anywhere, so an unsafe sqlite3 chained
# after a safe one can't slip through.
ALL=$(grep -ow 'sqlite3' <<<"$COMMAND" | wc -l | tr -d ' ')
SAFE=$(grep -oE 'sqlite3[[:space:]]+-safe[[:space:]]+-readonly' <<<"$COMMAND" | wc -l | tr -d ' ')
if [ "$ALL" != "$SAFE" ]; then
  jq -nc '{decision: "deny", reason: "Blocked: open the taxonomy databases with sqlite3 -safe -readonly."}'
  exit 0
fi

echo '{"decision": "allow"}'
