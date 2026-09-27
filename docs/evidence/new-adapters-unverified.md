# codex, gemini, opencode adapters: flags from docs, UNVERIFIED

**None of these adapters has been run against a real binary.** No `codex`,
`gemini`, or `opencode` is installed on the machine they were written on. Every
flag below is taken from the CLI's official documentation, read on 2026-09-27.
The argv each adapter builds is unit-tested (`tests/test_executor_modes.py`);
whether the CLI accepts it is not. Until a smoke run exists, treat a failure
from one of these as possibly Polyphony's argv, not the task.

All three are opt-in: registered in `EXECUTORS`, never in `DEFAULT_POOL`.

## codex (OpenAI Codex CLI)

Sources:
- https://learn.chatgpt.com/docs/developer-commands?surface=cli (where
  https://developers.openai.com/codex/cli/reference redirects), `codex exec` table
- https://learn.chatgpt.com/docs/non-interactive-mode?surface=cli

| Use | Flag | Quoted from the docs |
|---|---|---|
| Non-interactive | `codex exec` | "for scripted or CI-style runs that should finish without human interaction" |
| Prompt on stdin | `-` | `PROMPT`: "Use `-` to pipe the prompt from stdin." |
| review | `--sandbox read-only` | "By default, `codex exec` runs in a read-only sandbox." |
| code | `--sandbox workspace-write` | "Allow edits: `codex exec --sandbox workspace-write "<task>"`" |
| Workspace | `--cd` | "Set the workspace root before executing the task." |
| Model | `--model` | "Override the configured model for this run." |

Not used: `--dangerously-bypass-approvals-and-sandbox` / `--yolo` ("Bypass
approval prompts and sandboxing"), `--sandbox danger-full-access`, and
`--full-auto` ("Deprecated compatibility flag").

Binary discovery: `shutil.which("codex")` only. The docs give no fixed install path.

## gemini (Google Gemini CLI)

Sources:
- https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/cli-reference.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/plan-mode.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/policy-engine.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/trusted-folders.md

| Use | Flag | Quoted from the docs |
|---|---|---|
| Non-interactive | `--prompt=<text>` | "Prompt text. Appended to stdin input if provided. Forces non-interactive mode." |
| Modes | `--approval-mode` | "Choices: `default`, `auto_edit`, `yolo`, `plan`" |
| review | `--approval-mode plan` | "Plan Mode is a read-only environment" |
| code | `--approval-mode auto_edit` | "`autoEdit`: Optimized for automated code editing; some write tools may be auto-approved." |
| Model | `--model` | "Model to use." |

Why `auto_edit` is not a bypass: anything still needing approval is refused in
headless runs. The policy engine doc says of `ask_user`: "In non-interactive
mode, this is treated as `deny`."

The prompt is attached with `=` so an instruction starting with `-` stays the
flag's value. That relies on standard option parsing and is unverified.

Not used: `yolo`, `--yolo` ("Deprecated. Auto-approve all actions.").

Known gap: if the user has enabled Folder Trust (off by default), a headless
run in an untrusted folder "will throw a `FatalUntrustedWorkspaceError` and
exit". Every job runs in a fresh clone, so such a user gets that error until
they set `GEMINI_CLI_TRUST_WORKSPACE=true`. Polyphony does not pass
`--skip-trust`, which would also load the repository's own Gemini settings.

Binary discovery: `shutil.which("gemini")` only.

## opencode

Sources:
- https://opencode.ai/docs/cli/ (source:
  https://github.com/sst/opencode/blob/dev/packages/web/src/content/docs/cli.mdx)
- https://opencode.ai/docs/agents/
- https://opencode.ai/docs/permissions/

| Use | Flag | Quoted from the docs |
|---|---|---|
| Non-interactive | `opencode run [message..]` | "Run opencode in non-interactive mode by passing a prompt directly." |
| review | `--agent plan` | Plan agent: "By default, all of the following are set to `ask`" (file edits, bash) |
| Workspace | `--dir` | "Directory to run in" |
| Model | `--model` | "Model to use in the form of provider/model" |

**No code mode.** The edit-capable agent is Build, "the default primary agent
with all tools enabled", and the permission defaults say "Most permissions
default to `"allow"`." opencode has no sandbox. Build is therefore an
unprompted shell with write access, a bypass in all but name. `--auto`
("Auto-approve permissions that are not explicitly denied") is the same. So
`OpencodeExecutor.modes` is review only, `build_argv` raises for `code`, and the
server refuses `executor="opencode", mode="code"` and skips opencode in a
code-mode pool. A scoped code mode would need Polyphony to supply an opencode
permission config (edit allowed, bash denied), which the executor interface
cannot do today.

Unknowns in review mode: the docs do not say what `run` does when the plan
agent hits an `ask`. It may deny or it may wait; if it waits, the job's timeout
ends it. A user config that loosens the plan agent's permissions would also
loosen review mode. The job runs in a private clone either way.

The message is positional and goes last, as with cursor-agent. An instruction
starting with `-` may be parsed as a flag.

Binary discovery: `shutil.which("opencode")` only.
