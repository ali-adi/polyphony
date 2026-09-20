# Plan 1 Task 6: Real-subprocess smoke test results

**Date:** 2026-09-21
**Command run:** `.venv/bin/python -m pytest tests/smoke -m smoke -v`
**Outcome:** 1 passed (claude), 2 failed (agy, cursor)

This file records, verbatim, what actually happened the first time Polyphony
invoked each real CLI binary with `Mode.REVIEW`. Nothing below has been
patched around; the failures are the deliverable.

---

## claude — PASSED

**Argv (from `ClaudeExecutor().build_argv(Mode.REVIEW)`):**

```
['/Users/ali/.local/bin/claude', '-p', '--permission-mode', 'plan', '--permission-prompts', 'none']
```

**Exit code:** `0`

**Stdout (first 500 chars, verbatim):**

```
POLYPHONY_OK
```

**Stderr (first 500 chars, verbatim):**

```
(empty)
```

**Notes:** Worked exactly as designed. `--permission-mode plan` +
`--permission-prompts none` produced a clean, non-interactive response with
no prompt hang and no bypass flag.

---

## agy — FAILED

**Argv (from `AgyExecutor().build_argv(Mode.REVIEW, cwd="<scratch repo path>")`):**

```
['/Users/ali/.local/bin/agy', '-p', '--input-format', 'text', '--mode', 'plan', '--sandbox', '--add-dir', '<scratch repo path>', '--output-format', 'text']
```

Actual command executed (from `res.metadata["cmd"]`):

```
/Users/ali/.local/bin/agy -p --input-format text --mode plan --sandbox --add-dir /var/folders/8l/m8gg5p1j7jqf5dq2fn96bvcr0000gn/T/tmptiu5mlee/scratch --output-format text
```

**Exit code:** `2`

**Stdout (first 500 chars, verbatim):**

```
(empty)
```

**Stderr (first 500 chars, verbatim):**

```
Error: -p took "--input-format" as its prompt, so the intended prompt was left as an argument and ignored.
Attach the prompt to the flag (-p='your prompt') and move --input-format elsewhere on the command line.
```

**Notes:** `agy` treats `-p` as a value-taking flag whose argument is the very
next token on the command line, not a boolean "prompt mode" switch. Because
`build_argv` emits `-p` followed immediately by `--input-format`, agy parses
`--input-format` itself as the value of `-p` (the prompt text), leaving the
instruction piped on stdin (via `input=instruction` in `execute()`)
completely unused. agy never received the actual instruction text at all —
it errored out before reading stdin. This is a genuine argv-construction bug
in `AgyExecutor.build_argv`, not a permissions or sandbox issue.

---

## cursor-agent — FAILED

**Argv (from `CursorExecutor().build_argv(Mode.REVIEW)`):**

```
['/Users/ali/.local/bin/cursor-agent', '-p', '--mode', 'plan']
```

**Exit code:** `1`

**Stdout (first 500 chars, verbatim):**

```
(empty)
```

**Stderr (first 500 chars, verbatim):**

```
⚠ Workspace Trust Required

  Cursor Agent can execute code and access files in this directory.
  Do you trust the contents of this directory?

    /private/var/folders/8l/m8gg5p1j7jqf5dq2fn96bvcr0000gn/T/tmptiu5mlee/scratch

  To proceed, you can either:
    • Run 'agent' interactively to decide
    • Pass --trust, --yolo, or -f if you trust this directory
```

**Notes:** `cursor-agent` refuses to run non-interactively in a directory it
has not previously seen unless one of `--trust`, `--yolo`, or `-f` is passed.
`build_argv` only adds `-f` in `Mode.CODE` (paired with `--sandbox enabled`);
in `Mode.REVIEW` it adds only `--mode plan`, which is not sufficient on its
own to clear the workspace-trust gate for a brand-new scratch directory.
This did not reach the point of testing whether the prompt needs to be a
positional argument instead of stdin — the process exited before consuming
stdin at all, at the trust prompt.

---

## Summary of findings for Plan 2

- **claude:** works as designed with the native `--permission-mode` /
  `--permission-prompts` flags. No further action implied by this evidence.
- **agy:** `build_argv`'s flag ordering is wrong — `-p` immediately followed
  by another flag token causes agy's CLI parser to swallow that next flag as
  the prompt value instead of reading the prompt from stdin. The prompt
  never reaches agy.
- **cursor-agent:** `Mode.REVIEW` (`--mode plan` alone) is not enough to run
  non-interactively against an unseen directory — cursor-agent's
  workspace-trust gate blocks before stdin is even read. Whether the prompt
  also needs to be positional rather than piped via stdin was not observed,
  since the process exited at the trust prompt first.
