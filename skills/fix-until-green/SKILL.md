---
name: fix-until-green
description: Iterative test fixing loop until all tests pass or 2 stalled rounds
---

## Procedure
1. Run test suite: `env/bin/python -m unittest discover -s tests -t .`.
2. If all tests pass, mark green and complete.
3. If failures occur:
   - Analyze failure tracebacks.
   - Apply minimal correct fix to the implementation code.
   - Rerun test suite.
4. If 2 consecutive rounds make no progress, halt and report.
