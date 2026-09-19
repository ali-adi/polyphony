---
name: catchup
description: Summarize what changed on this branch and why
disable-model-invocation: true
allowed-tools:
  - Bash(git log *)
  - Bash(git diff *)
  - Bash(git status *)
  - Bash(tail *)
---

## Commits on this branch (vs main)
!`git log --oneline main..HEAD`

## Files changed on this branch vs main
!`git diff --stat main...HEAD | tail -25`

## Uncommitted changes
!`git status --short`

!`git diff --stat`

## Instructions
Summarize the above: what changed, why (infer from the commit messages and the files they
touch), and anything that looks unfinished or worth flagging before picking this back up.
The full branch diff is too big to inject, so read specific diffs
(`git diff main...HEAD -- <path>`) only when you need the detail. Uncommitted changes may
belong to another session working in this repo, so report them separately from the branch's
commits.
