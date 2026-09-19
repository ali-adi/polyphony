# Migration Inventory: `medicoder`

Generated automatically by `ai-orch migrate`.

## Summary

- **Total Discovered Assets**: 143
- **Global Skills & Workflows**: 106
- **Project Domain Assets**: 32
- **Executor Adapter Configs**: 4
- **Sensitive/Blocked Credentials**: 1
- **Ephemeral/Ignored State**: 0

## Discovered AI Configurations

| Source Tool | Category | Scope | File Path | Action | Target Destination | Rationale |
|---|---|---|---|---|---|---|
| Antigravity | Hook | Project | `.agents/hooks/block-ai-attribution.sh` | translate | `projects/medicoder/hooks/block-ai-attribution.sh` | Git safety: prevents co-authored AI commit metadata |
| Antigravity | Hook | Project | `.agents/hooks/block-paid-runs.sh` | translate | `projects/medicoder/hooks/block-paid-runs.sh` | Cost protection: blocks costly external API runs without explicit flags |
| Antigravity | Hook | Project | `.agents/hooks/protect-databases.sh` | translate | `projects/medicoder/hooks/protect-databases.sh` | File protection: prevents modifications to taxonomy database snapshots |
| Antigravity | Hook | Project | `.agents/hooks/validate-readonly-query.sh` | translate | `projects/medicoder/hooks/validate-readonly-query.sh` | Database safety: validates SQLite queries are strictly SELECT statements |
| Antigravity | Hook | Project | `.agents/hooks/verify-before-stop.sh` | translate | `projects/medicoder/hooks/verify-before-stop.sh` | Quality gate: enforces running test suite before completing tasks |
| Antigravity | Setting | Executor | `.agents/hooks.json` | copy_as_is | `migration/medicoder/original/.agents/hooks.json` | Executor adapter / tool-specific configuration (antigravity). |
| Antigravity | Skill | Global | `.agents/skills/ask-matt/PHASE-BOUNDARIES.md` | translate | `skills/ask-matt/` | Global skill asset: ask-matt |
| Antigravity | Skill | Global | `.agents/skills/ask-matt/SKILL.md` | translate | `skills/ask-matt/` | Global skill asset: ask-matt |
| Antigravity | Skill | Global | `.agents/skills/ask-matt/agents/openai.yaml` | translate | `skills/ask-matt/` | Global skill asset: ask-matt |
| Antigravity | Skill | Global | `.agents/skills/claude-handoff/SKILL.md` | translate | `skills/claude-handoff/` | Global skill asset: claude-handoff |
| Antigravity | Skill | Global | `.agents/skills/claude-handoff/agents/openai.yaml` | translate | `skills/claude-handoff/` | Global skill asset: claude-handoff |
| Antigravity | Skill | Global | `.agents/skills/code-review/SKILL.md` | translate | `skills/code-review/` | Global reusable engineering skill: code-review |
| Antigravity | Skill | Global | `.agents/skills/code-review/agents/openai.yaml` | translate | `skills/code-review/` | Global reusable engineering skill: code-review |
| Antigravity | Skill | Global | `.agents/skills/codebase-design/DEEPENING.md` | translate | `skills/codebase-design/` | Global skill asset: codebase-design |
| Antigravity | Skill | Global | `.agents/skills/codebase-design/DESIGN-IT-TWICE.md` | translate | `skills/codebase-design/` | Global skill asset: codebase-design |
| Antigravity | Skill | Global | `.agents/skills/codebase-design/SKILL.md` | translate | `skills/codebase-design/` | Global skill asset: codebase-design |
| Antigravity | Skill | Global | `.agents/skills/codebase-design/agents/openai.yaml` | translate | `skills/codebase-design/` | Global skill asset: codebase-design |
| Antigravity | Skill | Global | `.agents/skills/diagnosing-bugs/SKILL.md` | translate | `skills/diagnosing-bugs/` | Global reusable engineering skill: diagnosing-bugs |
| Antigravity | Skill | Global | `.agents/skills/diagnosing-bugs/agents/openai.yaml` | translate | `skills/diagnosing-bugs/` | Global reusable engineering skill: diagnosing-bugs |
| Antigravity | Skill | Global | `.agents/skills/diagnosing-bugs/scripts/hitl-loop.template.sh` | translate | `skills/diagnosing-bugs/` | Global reusable engineering skill: diagnosing-bugs |
| Antigravity | Skill | Global | `.agents/skills/domain-modeling/ADR-FORMAT.md` | translate | `skills/domain-modeling/` | Global skill asset: domain-modeling |
| Antigravity | Skill | Global | `.agents/skills/domain-modeling/CONTEXT-FORMAT.md` | translate | `skills/domain-modeling/` | Global skill asset: domain-modeling |
| Antigravity | Skill | Global | `.agents/skills/domain-modeling/SKILL.md` | translate | `skills/domain-modeling/` | Global skill asset: domain-modeling |
| Antigravity | Skill | Global | `.agents/skills/domain-modeling/agents/openai.yaml` | translate | `skills/domain-modeling/` | Global skill asset: domain-modeling |
| Antigravity | Skill | Global | `.agents/skills/git-guardrails-claude-code/SKILL.md` | translate | `skills/git-guardrails-claude-code/` | Global reusable engineering skill: git-guardrails-claude-code |
| Antigravity | Skill | Global | `.agents/skills/git-guardrails-claude-code/agents/openai.yaml` | translate | `skills/git-guardrails-claude-code/` | Global reusable engineering skill: git-guardrails-claude-code |
| Antigravity | Skill | Global | `.agents/skills/git-guardrails-claude-code/scripts/block-dangerous-git.sh` | translate | `skills/git-guardrails-claude-code/` | Global reusable engineering skill: git-guardrails-claude-code |
| Antigravity | Skill | Global | `.agents/skills/grill-me/SKILL.md` | translate | `skills/grill-me/` | Global reusable engineering skill: grill-me |
| Antigravity | Skill | Global | `.agents/skills/grill-me/agents/openai.yaml` | translate | `skills/grill-me/` | Global reusable engineering skill: grill-me |
| Antigravity | Skill | Global | `.agents/skills/grill-with-docs/SKILL.md` | translate | `skills/grill-with-docs/` | Global reusable engineering skill: grill-with-docs |
| Antigravity | Skill | Global | `.agents/skills/grill-with-docs/agents/openai.yaml` | translate | `skills/grill-with-docs/` | Global reusable engineering skill: grill-with-docs |
| Antigravity | Skill | Global | `.agents/skills/grilling/SKILL.md` | translate | `skills/grilling/` | Global skill asset: grilling |
| Antigravity | Skill | Global | `.agents/skills/grilling/agents/openai.yaml` | translate | `skills/grilling/` | Global skill asset: grilling |
| Antigravity | Skill | Global | `.agents/skills/handoff/SKILL.md` | translate | `skills/handoff/` | Global skill asset: handoff |
| Antigravity | Skill | Global | `.agents/skills/handoff/agents/openai.yaml` | translate | `skills/handoff/` | Global skill asset: handoff |
| Antigravity | Skill | Global | `.agents/skills/implement-spec/SKILL.md` | translate | `skills/implement-spec/` | Global skill asset: implement-spec |
| Antigravity | Skill | Global | `.agents/skills/implement-spec/agents/openai.yaml` | translate | `skills/implement-spec/` | Global skill asset: implement-spec |
| Antigravity | Skill | Global | `.agents/skills/implement/SKILL.md` | translate | `skills/implement/` | Global skill asset: implement |
| Antigravity | Skill | Global | `.agents/skills/implement/agents/openai.yaml` | translate | `skills/implement/` | Global skill asset: implement |
| Antigravity | Skill | Global | `.agents/skills/improve-codebase-architecture/HTML-REPORT.md` | translate | `skills/improve-codebase-architecture/` | Global reusable engineering skill: improve-codebase-architecture |
| Antigravity | Skill | Global | `.agents/skills/improve-codebase-architecture/SKILL.md` | translate | `skills/improve-codebase-architecture/` | Global reusable engineering skill: improve-codebase-architecture |
| Antigravity | Skill | Global | `.agents/skills/improve-codebase-architecture/agents/openai.yaml` | translate | `skills/improve-codebase-architecture/` | Global reusable engineering skill: improve-codebase-architecture |
| Antigravity | Skill | Global | `.agents/skills/loop-me/SKILL.md` | translate | `skills/loop-me/` | Global skill asset: loop-me |
| Antigravity | Skill | Global | `.agents/skills/loop-me/agents/openai.yaml` | translate | `skills/loop-me/` | Global skill asset: loop-me |
| Antigravity | Skill | Global | `.agents/skills/migrate-to-shoehorn/SKILL.md` | translate | `skills/migrate-to-shoehorn/` | Global skill asset: migrate-to-shoehorn |
| Antigravity | Skill | Global | `.agents/skills/migrate-to-shoehorn/agents/openai.yaml` | translate | `skills/migrate-to-shoehorn/` | Global skill asset: migrate-to-shoehorn |
| Antigravity | Skill | Global | `.agents/skills/pr/CREDITS.md` | translate | `skills/pr/` | Global reusable engineering skill: pr |
| Antigravity | Skill | Global | `.agents/skills/pr/SKILL.md` | translate | `skills/pr/` | Global reusable engineering skill: pr |
| Antigravity | Skill | Global | `.agents/skills/pr/agents/openai.yaml` | translate | `skills/pr/` | Global reusable engineering skill: pr |
| Antigravity | Skill | Global | `.agents/skills/prototype/LOGIC.md` | translate | `skills/prototype/` | Global skill asset: prototype |
| Antigravity | Skill | Global | `.agents/skills/prototype/SKILL.md` | translate | `skills/prototype/` | Global skill asset: prototype |
| Antigravity | Skill | Global | `.agents/skills/prototype/UI.md` | translate | `skills/prototype/` | Global skill asset: prototype |
| Antigravity | Skill | Global | `.agents/skills/prototype/agents/openai.yaml` | translate | `skills/prototype/` | Global skill asset: prototype |
| Antigravity | Skill | Global | `.agents/skills/research/SKILL.md` | translate | `skills/research/` | Global skill asset: research |
| Antigravity | Skill | Global | `.agents/skills/research/agents/openai.yaml` | translate | `skills/research/` | Global skill asset: research |
| Antigravity | Skill | Global | `.agents/skills/resolving-merge-conflicts/SKILL.md` | translate | `skills/resolving-merge-conflicts/` | Global reusable engineering skill: resolving-merge-conflicts |
| Antigravity | Skill | Global | `.agents/skills/resolving-merge-conflicts/agents/openai.yaml` | translate | `skills/resolving-merge-conflicts/` | Global reusable engineering skill: resolving-merge-conflicts |
| Antigravity | Skill | Global | `.agents/skills/retro/SKILL.md` | translate | `skills/retro/` | Global skill asset: retro |
| Antigravity | Skill | Global | `.agents/skills/retro/agents/openai.yaml` | translate | `skills/retro/` | Global skill asset: retro |
| Antigravity | Skill | Global | `.agents/skills/scaffold-exercises/SKILL.md` | translate | `skills/scaffold-exercises/` | Global skill asset: scaffold-exercises |
| Antigravity | Skill | Global | `.agents/skills/scaffold-exercises/agents/openai.yaml` | translate | `skills/scaffold-exercises/` | Global skill asset: scaffold-exercises |
| Antigravity | Skill | Global | `.agents/skills/setup-matt-pocock-skills/SKILL.md` | translate | `skills/setup-matt-pocock-skills/` | Global skill asset: setup-matt-pocock-skills |
| Antigravity | Skill | Global | `.agents/skills/setup-matt-pocock-skills/agents/openai.yaml` | translate | `skills/setup-matt-pocock-skills/` | Global skill asset: setup-matt-pocock-skills |
| Antigravity | Skill | Global | `.agents/skills/setup-matt-pocock-skills/domain.md` | translate | `skills/setup-matt-pocock-skills/` | Global skill asset: setup-matt-pocock-skills |
| Antigravity | Skill | Global | `.agents/skills/setup-matt-pocock-skills/issue-tracker-github.md` | translate | `skills/setup-matt-pocock-skills/` | Global skill asset: setup-matt-pocock-skills |
| Antigravity | Skill | Global | `.agents/skills/setup-matt-pocock-skills/issue-tracker-gitlab.md` | translate | `skills/setup-matt-pocock-skills/` | Global skill asset: setup-matt-pocock-skills |
| Antigravity | Skill | Global | `.agents/skills/setup-matt-pocock-skills/issue-tracker-local.md` | translate | `skills/setup-matt-pocock-skills/` | Global skill asset: setup-matt-pocock-skills |
| Antigravity | Skill | Global | `.agents/skills/setup-matt-pocock-skills/triage-labels.md` | translate | `skills/setup-matt-pocock-skills/` | Global skill asset: setup-matt-pocock-skills |
| Antigravity | Skill | Global | `.agents/skills/setup-pre-commit/SKILL.md` | translate | `skills/setup-pre-commit/` | Global skill asset: setup-pre-commit |
| Antigravity | Skill | Global | `.agents/skills/setup-pre-commit/agents/openai.yaml` | translate | `skills/setup-pre-commit/` | Global skill asset: setup-pre-commit |
| Antigravity | Skill | Global | `.agents/skills/setup-ts-deep-modules/SKILL.md` | translate | `skills/setup-ts-deep-modules/` | Global skill asset: setup-ts-deep-modules |
| Antigravity | Skill | Global | `.agents/skills/setup-ts-deep-modules/agents/openai.yaml` | translate | `skills/setup-ts-deep-modules/` | Global skill asset: setup-ts-deep-modules |
| Antigravity | Skill | Global | `.agents/skills/setup-ts-deep-modules/dependency-cruiser.config.cjs` | translate | `skills/setup-ts-deep-modules/` | Global skill asset: setup-ts-deep-modules |
| Antigravity | Skill | Global | `.agents/skills/tdd/SKILL.md` | translate | `skills/tdd/` | Global reusable engineering skill: tdd |
| Antigravity | Skill | Global | `.agents/skills/tdd/agents/openai.yaml` | translate | `skills/tdd/` | Global reusable engineering skill: tdd |
| Antigravity | Skill | Global | `.agents/skills/tdd/mocking.md` | translate | `skills/tdd/` | Global reusable engineering skill: tdd |
| Antigravity | Skill | Global | `.agents/skills/tdd/tests.md` | translate | `skills/tdd/` | Global reusable engineering skill: tdd |
| Antigravity | Skill | Global | `.agents/skills/teach/GLOSSARY-FORMAT.md` | translate | `skills/teach/` | Global skill asset: teach |
| Antigravity | Skill | Global | `.agents/skills/teach/LEARNING-RECORD-FORMAT.md` | translate | `skills/teach/` | Global skill asset: teach |
| Antigravity | Skill | Global | `.agents/skills/teach/MISSION-FORMAT.md` | translate | `skills/teach/` | Global skill asset: teach |
| Antigravity | Skill | Global | `.agents/skills/teach/RESOURCES-FORMAT.md` | translate | `skills/teach/` | Global skill asset: teach |
| Antigravity | Skill | Global | `.agents/skills/teach/SKILL.md` | translate | `skills/teach/` | Global skill asset: teach |
| Antigravity | Skill | Global | `.agents/skills/teach/agents/openai.yaml` | translate | `skills/teach/` | Global skill asset: teach |
| Antigravity | Skill | Global | `.agents/skills/to-questionnaire/SKILL.md` | translate | `skills/to-questionnaire/` | Global skill asset: to-questionnaire |
| Antigravity | Skill | Global | `.agents/skills/to-questionnaire/agents/openai.yaml` | translate | `skills/to-questionnaire/` | Global skill asset: to-questionnaire |
| Antigravity | Skill | Global | `.agents/skills/to-spec/SKILL.md` | translate | `skills/to-spec/` | Global skill asset: to-spec |
| Antigravity | Skill | Global | `.agents/skills/to-spec/agents/openai.yaml` | translate | `skills/to-spec/` | Global skill asset: to-spec |
| Antigravity | Skill | Global | `.agents/skills/to-tickets/SKILL.md` | translate | `skills/to-tickets/` | Global skill asset: to-tickets |
| Antigravity | Skill | Global | `.agents/skills/to-tickets/agents/openai.yaml` | translate | `skills/to-tickets/` | Global skill asset: to-tickets |
| Antigravity | Skill | Global | `.agents/skills/triage/AGENT-BRIEF.md` | translate | `skills/triage/` | Global skill asset: triage |
| Antigravity | Skill | Global | `.agents/skills/triage/OUT-OF-SCOPE.md` | translate | `skills/triage/` | Global skill asset: triage |
| Antigravity | Skill | Global | `.agents/skills/triage/SKILL.md` | translate | `skills/triage/` | Global skill asset: triage |
| Antigravity | Skill | Global | `.agents/skills/triage/agents/openai.yaml` | translate | `skills/triage/` | Global skill asset: triage |
| Antigravity | Skill | Global | `.agents/skills/wait-what/SKILL.md` | translate | `skills/wait-what/` | Global skill asset: wait-what |
| Antigravity | Skill | Global | `.agents/skills/wait-what/agents/openai.yaml` | translate | `skills/wait-what/` | Global skill asset: wait-what |
| Antigravity | Skill | Global | `.agents/skills/wayfinder/SKILL.md` | translate | `skills/wayfinder/` | Global skill asset: wayfinder |
| Antigravity | Skill | Global | `.agents/skills/wayfinder/agents/openai.yaml` | translate | `skills/wayfinder/` | Global skill asset: wayfinder |
| Antigravity | Skill | Global | `.agents/skills/wizard/SKILL.md` | translate | `skills/wizard/` | Global skill asset: wizard |
| Antigravity | Skill | Global | `.agents/skills/wizard/agents/openai.yaml` | translate | `skills/wizard/` | Global skill asset: wizard |
| Antigravity | Skill | Global | `.agents/skills/wizard/template.sh` | translate | `skills/wizard/` | Global skill asset: wizard |
| Antigravity | Skill | Global | `.agents/skills/writing-beats/SKILL.md` | translate | `skills/writing-beats/` | Global skill asset: writing-beats |
| Antigravity | Skill | Global | `.agents/skills/writing-beats/agents/openai.yaml` | translate | `skills/writing-beats/` | Global skill asset: writing-beats |
| Antigravity | Skill | Global | `.agents/skills/writing-for-agents/SKILL-MECHANICS.md` | translate | `skills/writing-for-agents/` | Global skill asset: writing-for-agents |
| Antigravity | Skill | Global | `.agents/skills/writing-for-agents/SKILL.md` | translate | `skills/writing-for-agents/` | Global skill asset: writing-for-agents |
| Antigravity | Skill | Global | `.agents/skills/writing-for-agents/agents/openai.yaml` | translate | `skills/writing-for-agents/` | Global skill asset: writing-for-agents |
| Antigravity | Skill | Global | `.agents/skills/writing-fragments/SKILL.md` | translate | `skills/writing-fragments/` | Global skill asset: writing-fragments |
| Antigravity | Skill | Global | `.agents/skills/writing-fragments/agents/openai.yaml` | translate | `skills/writing-fragments/` | Global skill asset: writing-fragments |
| Antigravity | Skill | Global | `.agents/skills/writing-shape/SKILL.md` | translate | `skills/writing-shape/` | Global skill asset: writing-shape |
| Antigravity | Skill | Global | `.agents/skills/writing-shape/agents/openai.yaml` | translate | `skills/writing-shape/` | Global skill asset: writing-shape |
| Claude | Agent | Project | `.claude/agents/am-achi-notes-author.md` | translate | `projects/medicoder/skills/am-achi-notes-author/` | Medicoder domain skill/agent: am-achi-notes-author |
| Claude | Agent | Project | `.claude/agents/db-reader.md` | translate | `projects/medicoder/skills/db-reader/` | Medicoder domain skill/agent: db-reader |
| Claude | Agent | Project | `.claude/agents/pcs-editor.md` | translate | `projects/medicoder/skills/pcs-editor/` | Medicoder domain skill/agent: pcs-editor |
| Claude | Agent | Project | `.claude/agents/pcs-notes-author.md` | translate | `projects/medicoder/skills/pcs-notes-author/` | Medicoder domain skill/agent: pcs-notes-author |
| Claude | Hook | Project | `.claude/hooks/block-ai-attribution.sh` | translate | `projects/medicoder/hooks/block-ai-attribution.sh` | Git safety: prevents co-authored AI commit metadata |
| Claude | Hook | Project | `.claude/hooks/block-paid-runs.sh` | translate | `projects/medicoder/hooks/block-paid-runs.sh` | Cost protection: blocks costly external API runs without explicit flags |
| Claude | Hook | Project | `.claude/hooks/protect-databases.sh` | translate | `projects/medicoder/hooks/protect-databases.sh` | File protection: prevents modifications to taxonomy database snapshots |
| Claude | Hook | Project | `.claude/hooks/validate-readonly-query.sh` | translate | `projects/medicoder/hooks/validate-readonly-query.sh` | Database safety: validates SQLite queries are strictly SELECT statements |
| Claude | Hook | Project | `.claude/hooks/verify-before-stop.sh` | translate | `projects/medicoder/hooks/verify-before-stop.sh` | Quality gate: enforces running test suite before completing tasks |
| Claude | Setting | Project | `.claude/settings.json` | translate | `projects/medicoder/project.yaml` | Workspace permissions and command allow/deny lists. |
| Claude | Setting | Executor | `.claude/settings.local.json` | copy_as_is | `migration/medicoder/original/.claude/settings.local.json` | Executor adapter / tool-specific configuration (claude). |
| Claude | Skill | Global | `.claude/skills/catchup/SKILL.md` | translate | `skills/catchup/` | Global reusable engineering skill: catchup |
| Claude | Skill | Global | `.claude/skills/pr/SKILL.md` | translate | `skills/pr/` | Global reusable engineering skill: pr |
| Claude | Workflow | Project | `.claude/workflows/audit-eval-contamination.js` | translate | `projects/medicoder/skills/audit-eval-contamination/` | Medicoder domain skill/agent: audit-eval-contamination |
| Claude | Workflow | Global | `.claude/workflows/fix-until-green.js` | translate | `skills/fix-until-green/` | Global reusable engineering skill: fix-until-green |
| Cursor | Hook | Project | `.cursor/hooks/block-bulk-git-add.sh` | translate | `projects/medicoder/hooks/block-bulk-git-add.sh` | Git safety: prevents indiscriminate git add -A or git add . |
| Cursor | Hook | Executor | `.cursor/hooks/claude-adapter.sh` | copy_as_is | `migration/medicoder/original/.cursor/hooks/claude-adapter.sh` | Executor adapter / tool-specific configuration (cursor). |
| Cursor | Hook | Project | `.cursor/hooks/readonly-sqlite.sh` | translate | `projects/medicoder/hooks/readonly-sqlite.sh` | Database safety: ensures sqlite connections are opened in readonly mode |
| Cursor | Rule | Project | `.cursor/rules/am-full-runs.mdc` | translate | `projects/medicoder/rules/am-full-runs.md` | Project operational rule: am-full-runs |
| Cursor | Setting | Executor | `.cursor/hooks.json` | copy_as_is | `migration/medicoder/original/.cursor/hooks.json` | Executor adapter / tool-specific configuration (cursor). |
| Cursor | Skill | Project | `.cursor/skills/analyze-runs/SKILL.md` | translate | `projects/medicoder/skills/analyze-runs/` | Medicoder domain skill/agent: analyze-runs |
| Cursor | Skill | Project | `.cursor/skills/icd10am-achi/SKILL.md` | translate | `projects/medicoder/skills/icd10am-achi/` | Medicoder domain skill/agent: icd10am-achi |
| Cursor | Skill | Project | `.cursor/skills/icd10am-achi/examples.md` | translate | `projects/medicoder/skills/icd10am-achi/` | Medicoder domain skill/agent: icd10am-achi |
| Cursor | Skill | Project | `.cursor/skills/icd10am-achi/language.md` | translate | `projects/medicoder/skills/icd10am-achi/` | Medicoder domain skill/agent: icd10am-achi |
| Cursor | Skill | Project | `.cursor/skills/icd10am-achi/schema.md` | translate | `projects/medicoder/skills/icd10am-achi/` | Medicoder domain skill/agent: icd10am-achi |
| Cursor | Skill | Project | `.cursor/skills/icd10cm-pcs/SKILL.md` | translate | `projects/medicoder/skills/icd10cm-pcs/` | Medicoder domain skill/agent: icd10cm-pcs |
| Cursor | Skill | Project | `.cursor/skills/icd10cm-pcs/examples.md` | translate | `projects/medicoder/skills/icd10cm-pcs/` | Medicoder domain skill/agent: icd10cm-pcs |
| Cursor | Skill | Project | `.cursor/skills/icd10cm-pcs/language.md` | translate | `projects/medicoder/skills/icd10cm-pcs/` | Medicoder domain skill/agent: icd10cm-pcs |
| Cursor | Skill | Project | `.cursor/skills/icd10cm-pcs/schema.md` | translate | `projects/medicoder/skills/icd10cm-pcs/` | Medicoder domain skill/agent: icd10cm-pcs |
| Generic | Convention | Project | `docs/tune-level-runbook.md` | translate | `projects/medicoder/conventions.md` | Project conventions, notes rules, and hard constraints: tune-level-runbook.md |
| Generic | Convention | Project | `tuning/runbook.md` | translate | `projects/medicoder/conventions.md` | Project conventions, notes rules, and hard constraints: runbook.md |
| Generic | Doc | Project | `README.md` | translate | `projects/medicoder/context.md` | Project architecture and overview: README.md |
| Generic | Secret | Sensitive | `.env` | security_block | `DO_NOT_MIGRATE` | Contains API keys or secrets (e.g. GEMINI_API_KEY). Blocked from copying. |
| Mcp | Mcp | Project | `.mcp.json` | translate | `projects/medicoder/project.yaml` | MCP tools configuration. |

## Consolidated Policies & Artifacts

- **Hooks**: Executable safety hook scripts preserved in `projects/<project>/hooks/` with executable bits.
- **Rules**: Enforced operational policies saved in `projects/<project>/rules/`.
- **Conventions & Style**: Coding standards, prompt structure, notes authoring syntax in `projects/<project>/conventions.md`.
- **Safety Engine**: Unified safety gates in `projects/<project>/safety.md`.
- **Domain Skills**: Specialized agents and schemas in `projects/<project>/skills/`.
- **Global Skills**: Reusable engineering workflows in `skills/`.
