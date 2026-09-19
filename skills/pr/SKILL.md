---
name: pr
description: Verify, stage, commit, and open a PR for the current branch
disable-model-invocation: true
allowed-tools:
  - Bash(git add *)
  - Bash(git commit *)
  - Bash(git push *)
  - Bash(gh pr create *)
  - Bash(gh auth status *)
  - Bash(python -m unittest *)
---

1. Run `gh auth status`. If it fails, stop and tell the user to authenticate the GitHub CLI
   (`gh auth login`).
2. Run the unit tests: `python -m unittest discover -s tests -t .`. Stop if any fail.
3. Run `git status` and `git diff` to see everything that changed.
4. Stage the relevant files by explicit path. Other sessions often leave unrelated dirty
   files in this repo, so if a dirty file isn't clearly part of this change, ask before
   staging it. Never use `git add -A`, `git add -u` or `git commit -a`.
5. Write a commit message: a one-line summary, then a short body that explains why, not just
   what.
6. Push with `git push -u origin HEAD`. Then open the PR with `gh pr create`, using the commit
   message as the PR description.
