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

---

# Addendum: verified resolutions (coordinator, same day)

The three failures above were reproduced independently and driven to a working
invocation for each CLI. These are **demonstrated**, not proposed.

## agy — resolution verified

`-p` is a **value-taking flag**, not a boolean. It consumes the next argv token
as the prompt, which is why `--input-format` was swallowed. The prompt must be
attached to the flag; stdin is never read.

Verified working:

```
agy -p="Reply with exactly: POLYPHONY_OK" --mode plan --sandbox --add-dir <cwd>
-> stdout: POLYPHONY_OK      exit: 0
```

**This bug predates the redesign.** The original adapter (commit `58ee2db^`)
built `[binary, "-p", "--input-format", "text", "--dangerously-skip-permissions",
"--add-dir", cwd]` and piped the instruction via stdin — the same malformed
shape. `AgyExecutor` has never successfully executed anything.

Required change: `build_argv` takes the instruction and emits `-p=<instruction>`;
`execute()` stops passing `input=instruction` to `subprocess.run`. Drop
`--input-format text`, which only applies to stdin-driven invocations.

## cursor-agent — two resolutions verified

**1. Workspace trust.** `--mode plan` alone hits a trust gate on an unseen
directory and exits before reading input. `--trust` ("Trust the current
workspace without prompting") clears it and is the correct flag for REVIEW mode
— `-f`/`--yolo` would also clear it but additionally force-allow command
execution, which contradicts read-only intent.

**2. The prompt is positional, not stdin.** Usage is
`agent [options] [command] [prompt...]`. Answers Open Question 1 in the spec.

**3. Default model is out of quota on this account.** With trust cleared:

```
cursor-agent -p --mode plan --trust "<prompt>"
-> stdout: ActionRequiredError: ... You're out of usage. Switch to Auto or
           Composer 2.5, or ask your admin to increase your limit to continue.
   exit: 0
```

Verified working with an explicit model:

```
cursor-agent -p --mode plan --trust --model composer-2.5 "<prompt>"
-> stdout: POLYPHONY_OK      exit: 0
```

`--model auto` does NOT work despite the error text recommending it — it
returns the same quota error. `composer-2.5` must be set explicitly.

## Critical finding for the quota ledger (spec §3)

**`cursor-agent` returns exit code 0 when it is out of quota**, emitting
`ActionRequiredError` on *stdout*. Both the quota-exhausted run and the
successful run exited 0.

Consequences for the ledger design:

- Exit-code-based failure detection will **silently classify a quota failure as
  a successful execution**. The orchestrator would record an iteration as
  succeeding while nothing happened.
- Output-content inspection is therefore mandatory, at least for cursor.
  `ActionRequiredError` and `out of usage` are the first two real entries for
  the pattern list the spec said to derive from evidence rather than invent.
- This also means `ExecutorResult.success`, currently derived from
  `returncode == 0` in every adapter, is unreliable for cursor and needs a
  per-adapter output check.

## Status summary

| Adapter | Before Plan 1 | After Plan 1 | Fix verified |
|---|---|---|---|
| claude | worked | works | n/a |
| agy | never worked (malformed `-p`) | still broken | yes — `-p=<prompt>` |
| cursor | never worked (wrong binary name) | binary found, invocation still broken | yes — `--trust` + positional prompt + `--model composer-2.5` |

Two of the three executors in this multi-agent orchestrator had never been
capable of executing anything.
