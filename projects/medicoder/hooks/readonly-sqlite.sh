#!/bin/bash
# The db-reader guard applies to every Cursor shell command that calls sqlite3, since Cursor
# can't scope a hook to one subagent. Commands without sqlite3 are left alone, so words like
# "update" in a commit message aren't caught.
COMMAND=$(jq -r '.tool_input.command // empty')
grep -qw 'sqlite3' <<< "$COMMAND" || exit 0
jq -nc --arg c "$COMMAND" '{tool_input: {command: $c}}' | "$CLAUDE_PROJECT_DIR"/.claude/hooks/validate-readonly-query.sh
