---
name: fix-until-green
description: Iterative test fixing loop until all tests pass or 2 stalled rounds
---

## Procedure
1. Run the test suite: `python -m unittest discover -s tests -t .` or `pytest`.
2. If all tests pass, stop and mark green.
3. If failures occur:
   - Identify the failing test cases.
   - Apply the smallest correct change to fix the code, not the test (unless test is obsolete).
   - Rerun suite.
4. If stalled for 2 consecutive rounds without reducing failures, halt and report.
