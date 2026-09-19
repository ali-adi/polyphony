#!/bin/bash
# Every pipeline run makes paid Gemini calls, and a session sweeping configs in a loop once ran
# 18 of them in half an hour. agy may only run the one-case configs/smoke.yml; anything bigger
# the user runs themselves. Each invocation in a compound command is checked, so a paid run
# chained after a smoke run can't slip through.
#
# The one sanctioned exception is scripts/tune_level.py, the per-level tuning harness: it runs
# one system at one level, and its `run --on full` is budgeted in Python (one discovery run per
# level, then only after two tuning runs). Its `--force-full` escape hatch is blocked here so
# that budget can't be overridden from a session; the user runs a forced full run themselves.
#
# Ported from .claude/hooks/block-paid-runs.sh.
INPUT=$(cat)
COMMAND=$(jq -r '.toolCall.args.CommandLine // empty' <<<"$INPUT")

REASON=$(python3 - "$COMMAND" <<'EOF'
import os, re, sys
cmd = sys.argv[1]
for args in re.findall(r"(?:-m\s+medicoder(?:\.(?:main|cli|__main__))?(?![\w.])|python3?\s+\S*medicoder/(?:main|cli|__main__)\.py)([^;&|\n]*)", cmd):
    if re.search(r"(?:^|\s)(?:--help|-h)(?:\s|$)", args):
        continue
    m = re.search(r"--config[=\s]+(\S+)", args)
    if not m or os.path.normpath(m.group(1).strip("'\"")) != "configs/smoke.yml":
        print("Blocked: agy may only run the pipeline with --config configs/smoke.yml (one case). "
              "For any other run, tell the user the command to run themselves.")
        sys.exit(0)
for args in re.findall(r"scripts/tune_level\.py([^;&|\n]*)", cmd):
    if re.search(r"(?:^|\s)--force-full(?:\s|$)", args):
        print("Blocked: --force-full overrides the full-dataset budget. Run tuning rounds instead, "
              "or tell the user the command to run themselves.")
        sys.exit(0)
EOF
)

if [ -n "$REASON" ]; then
  jq -nc --arg reason "$REASON" '{decision: "deny", reason: $reason}'
else
  echo '{"decision": "allow"}'
fi
