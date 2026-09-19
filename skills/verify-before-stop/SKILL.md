---
name: verify-before-stop
description: Enforce full test suite verification before completing task
---

## Quality Gate Procedure
Before declaring any task or iteration DONE:
1. Run repository test suite (`env/bin/python -m unittest discover -s tests -t .`).
2. Verify git status has no stray, dirty, or broken edits.
3. If tests fail, report failure and do NOT complete task.
