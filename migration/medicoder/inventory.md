# Migration Inventory: `medicoder`

Generated automatically by `ai-orch migrate`.

## Summary

- **Total Discovered Assets**: 278
- **Global Assets**: 9
- **Project Assets**: 262
- **Executor Configs**: 5
- **Sensitive/Blocked Items**: 1
- **Ephemeral/Ignored Items**: 1

## Discovered AI Configurations

| Source Tool | Category | Scope | File Path | Action | Target Destination | Rationale |
|---|---|---|---|---|---|---|
| Antigravity | Hook | Project | `.agents/hooks/block-ai-attribution.sh` | translate | `projects/medicoder/safety.md` | Git safety: prevents co-authored AI commit metadata |
| Antigravity | Hook | Project | `.agents/hooks/block-paid-runs.sh` | translate | `projects/medicoder/safety.md` | Cost protection: blocks costly external API runs without explicit flags |
| Antigravity | Hook | Project | `.agents/hooks/protect-databases.sh` | translate | `projects/medicoder/safety.md` | File protection: prevents modifications to taxonomy database snapshots |
| Antigravity | Hook | Project | `.agents/hooks/validate-readonly-query.sh` | translate | `projects/medicoder/safety.md` | Database safety: validates SQLite queries are strictly SELECT statements |
| Antigravity | Hook | Global | `.agents/hooks/verify-before-stop.sh` | translate | `skills/verify-before-stop/` | Generic reusable workflow or skill across engineering repos: verify-before-stop |
| Antigravity | Other | Ephemeral | `.gemini/antigravity-ide/scratch/analyze.py` | ignore | `IGNORE` | IDE ephemeral state or scratch workspace. |
| Antigravity | Setting | Executor | `.agents/hooks.json` | copy_as_is | `migration/medicoder/original/.agents/hooks.json` | Executor adapter / tool-specific configuration (antigravity). |
| Claude | Agent | Project | `.claude/agents/am-achi-notes-author.md` | translate | `projects/medicoder/skills/am-achi-notes-author/SKILL.md` | Project domain agent: Authoring agent for ICD-10-AM and ACHI notes |
| Claude | Agent | Project | `.claude/agents/db-reader.md` | translate | `projects/medicoder/skills/db-reader/SKILL.md` | Project domain agent: Read-only database inspector agent for taxonomy tables |
| Claude | Agent | Project | `.claude/agents/pcs-editor.md` | translate | `projects/medicoder/skills/pcs-editor/SKILL.md` | Project domain agent: Precise ICD-10-PCS code editor agent |
| Claude | Agent | Project | `.claude/agents/pcs-notes-author.md` | translate | `projects/medicoder/skills/pcs-notes-author/SKILL.md` | Project domain agent: Authoring agent for ICD-10-PCS notes |
| Claude | Doc | Global | `.claude/worktrees/rewrite/.claude/skills/catchup/SKILL.md` | translate | `skills/catchup/` | Generic reusable workflow or skill across engineering repos: catchup |
| Claude | Doc | Global | `.claude/worktrees/rewrite/.claude/skills/pr/SKILL.md` | translate | `skills/pr/` | Generic reusable workflow or skill across engineering repos: pr |
| Claude | Doc | Project | `.claude/worktrees/rewrite/README.md` | translate | `projects/medicoder/context.md` | Project context and instructions: README.md |
| Claude | Hook | Project | `.claude/hooks/block-ai-attribution.sh` | translate | `projects/medicoder/safety.md` | Git safety: prevents co-authored AI commit metadata |
| Claude | Hook | Project | `.claude/hooks/block-paid-runs.sh` | translate | `projects/medicoder/safety.md` | Cost protection: blocks costly external API runs without explicit flags |
| Claude | Hook | Project | `.claude/hooks/protect-databases.sh` | translate | `projects/medicoder/safety.md` | File protection: prevents modifications to taxonomy database snapshots |
| Claude | Hook | Project | `.claude/hooks/validate-readonly-query.sh` | translate | `projects/medicoder/safety.md` | Database safety: validates SQLite queries are strictly SELECT statements |
| Claude | Hook | Global | `.claude/hooks/verify-before-stop.sh` | translate | `skills/verify-before-stop/` | Generic reusable workflow or skill across engineering repos: verify-before-stop |
| Claude | Mcp | Project | `.claude/worktrees/rewrite/.mcp.json` | translate | `projects/medicoder/project.yaml` | MCP tools configuration. |
| Claude | Other | Project | `.claude/worktrees/rewrite/.claude/agents/db-reader.md` | translate | `projects/medicoder/skills/db-reader/SKILL.md` | Project domain agent: Read-only database inspector agent for taxonomy tables |
| Claude | Other | Project | `.claude/worktrees/rewrite/.claude/hooks/block-ai-attribution.sh` | translate | `projects/medicoder/safety.md` | Git safety: prevents co-authored AI commit metadata |
| Claude | Other | Project | `.claude/worktrees/rewrite/.claude/hooks/block-paid-runs.sh` | translate | `projects/medicoder/safety.md` | Cost protection: blocks costly external API runs without explicit flags |
| Claude | Other | Project | `.claude/worktrees/rewrite/.claude/hooks/protect-databases.sh` | translate | `projects/medicoder/safety.md` | File protection: prevents modifications to taxonomy database snapshots |
| Claude | Other | Project | `.claude/worktrees/rewrite/.claude/hooks/validate-readonly-query.sh` | translate | `projects/medicoder/safety.md` | Database safety: validates SQLite queries are strictly SELECT statements |
| Claude | Other | Global | `.claude/worktrees/rewrite/.claude/hooks/verify-before-stop.sh` | translate | `skills/verify-before-stop/` | Generic reusable workflow or skill across engineering repos: verify-before-stop |
| Claude | Other | Project | `.claude/worktrees/rewrite/.claude/workflows/audit-eval-contamination.js` | copy_as_is | `projects/medicoder/misc/audit-eval-contamination.js` | Unclassified AI asset from claude |
| Claude | Other | Global | `.claude/worktrees/rewrite/.claude/workflows/fix-until-green.js` | translate | `skills/fix-until-green/` | Generic reusable workflow or skill across engineering repos: fix-until-green |
| Claude | Other | Project | `.claude/worktrees/rewrite/.git` | copy_as_is | `projects/medicoder/misc/.git` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/.gitignore` | copy_as_is | `projects/medicoder/misc/.gitignore` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/configs/config.yml` | copy_as_is | `projects/medicoder/misc/config.yml` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/configs/prompts/icd10achi.yml` | copy_as_is | `projects/medicoder/misc/icd10achi.yml` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/configs/prompts/icd10am.yml` | copy_as_is | `projects/medicoder/misc/icd10am.yml` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/configs/prompts/icd10cm.yml` | copy_as_is | `projects/medicoder/misc/icd10cm.yml` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/configs/prompts/icd10pcs.yml` | copy_as_is | `projects/medicoder/misc/icd10pcs.yml` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/configs/smoke.yml` | copy_as_is | `projects/medicoder/misc/smoke.yml` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/configs/systems/icd10achi.yml` | copy_as_is | `projects/medicoder/misc/icd10achi.yml` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/configs/systems/icd10am.yml` | copy_as_is | `projects/medicoder/misc/icd10am.yml` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/configs/systems/icd10cm.yml` | copy_as_is | `projects/medicoder/misc/icd10cm.yml` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/configs/systems/icd10pcs.yml` | copy_as_is | `projects/medicoder/misc/icd10pcs.yml` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/database/icd10am_achi/icd10achi.sqlite` | copy_as_is | `projects/medicoder/misc/icd10achi.sqlite` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/database/icd10am_achi/icd10am.sqlite` | copy_as_is | `projects/medicoder/misc/icd10am.sqlite` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/database/icd10cm_pcs/icd10cm.sqlite` | copy_as_is | `projects/medicoder/misc/icd10cm.sqlite` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/database/icd10cm_pcs/icd10pcs.sqlite` | copy_as_is | `projects/medicoder/misc/icd10pcs.sqlite` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/database/tosp.sqlite` | copy_as_is | `projects/medicoder/misc/tosp.sqlite` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000001.json` | copy_as_is | `projects/medicoder/misc/000001.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000002.json` | copy_as_is | `projects/medicoder/misc/000002.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000003.json` | copy_as_is | `projects/medicoder/misc/000003.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000004.json` | copy_as_is | `projects/medicoder/misc/000004.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000005.json` | copy_as_is | `projects/medicoder/misc/000005.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000006.json` | copy_as_is | `projects/medicoder/misc/000006.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000007.json` | copy_as_is | `projects/medicoder/misc/000007.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000008.json` | copy_as_is | `projects/medicoder/misc/000008.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000009.json` | copy_as_is | `projects/medicoder/misc/000009.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000010.json` | copy_as_is | `projects/medicoder/misc/000010.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000011.json` | copy_as_is | `projects/medicoder/misc/000011.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000012.json` | copy_as_is | `projects/medicoder/misc/000012.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000013.json` | copy_as_is | `projects/medicoder/misc/000013.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000014.json` | copy_as_is | `projects/medicoder/misc/000014.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000015.json` | copy_as_is | `projects/medicoder/misc/000015.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000016.json` | copy_as_is | `projects/medicoder/misc/000016.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000017.json` | copy_as_is | `projects/medicoder/misc/000017.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000018.json` | copy_as_is | `projects/medicoder/misc/000018.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000019.json` | copy_as_is | `projects/medicoder/misc/000019.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000020.json` | copy_as_is | `projects/medicoder/misc/000020.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000021.json` | copy_as_is | `projects/medicoder/misc/000021.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000022.json` | copy_as_is | `projects/medicoder/misc/000022.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000023.json` | copy_as_is | `projects/medicoder/misc/000023.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000024.json` | copy_as_is | `projects/medicoder/misc/000024.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000025.json` | copy_as_is | `projects/medicoder/misc/000025.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000026.json` | copy_as_is | `projects/medicoder/misc/000026.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000027.json` | copy_as_is | `projects/medicoder/misc/000027.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000028.json` | copy_as_is | `projects/medicoder/misc/000028.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000029.json` | copy_as_is | `projects/medicoder/misc/000029.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000030.json` | copy_as_is | `projects/medicoder/misc/000030.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000031.json` | copy_as_is | `projects/medicoder/misc/000031.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000032.json` | copy_as_is | `projects/medicoder/misc/000032.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000033.json` | copy_as_is | `projects/medicoder/misc/000033.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000035.json` | copy_as_is | `projects/medicoder/misc/000035.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000036.json` | copy_as_is | `projects/medicoder/misc/000036.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000037.json` | copy_as_is | `projects/medicoder/misc/000037.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000038.json` | copy_as_is | `projects/medicoder/misc/000038.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000039.json` | copy_as_is | `projects/medicoder/misc/000039.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000040.json` | copy_as_is | `projects/medicoder/misc/000040.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000041.json` | copy_as_is | `projects/medicoder/misc/000041.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000042.json` | copy_as_is | `projects/medicoder/misc/000042.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000043.json` | copy_as_is | `projects/medicoder/misc/000043.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000044.json` | copy_as_is | `projects/medicoder/misc/000044.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000045.json` | copy_as_is | `projects/medicoder/misc/000045.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000046.json` | copy_as_is | `projects/medicoder/misc/000046.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000047.json` | copy_as_is | `projects/medicoder/misc/000047.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000048.json` | copy_as_is | `projects/medicoder/misc/000048.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000049.json` | copy_as_is | `projects/medicoder/misc/000049.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000050.json` | copy_as_is | `projects/medicoder/misc/000050.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000051.json` | copy_as_is | `projects/medicoder/misc/000051.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000052.json` | copy_as_is | `projects/medicoder/misc/000052.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000053.json` | copy_as_is | `projects/medicoder/misc/000053.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000054.json` | copy_as_is | `projects/medicoder/misc/000054.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000055.json` | copy_as_is | `projects/medicoder/misc/000055.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000057.json` | copy_as_is | `projects/medicoder/misc/000057.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000058.json` | copy_as_is | `projects/medicoder/misc/000058.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000059.json` | copy_as_is | `projects/medicoder/misc/000059.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000060.json` | copy_as_is | `projects/medicoder/misc/000060.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000062.json` | copy_as_is | `projects/medicoder/misc/000062.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000063.json` | copy_as_is | `projects/medicoder/misc/000063.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000064.json` | copy_as_is | `projects/medicoder/misc/000064.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000065.json` | copy_as_is | `projects/medicoder/misc/000065.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000066.json` | copy_as_is | `projects/medicoder/misc/000066.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000067.json` | copy_as_is | `projects/medicoder/misc/000067.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000068.json` | copy_as_is | `projects/medicoder/misc/000068.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000069.json` | copy_as_is | `projects/medicoder/misc/000069.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000070.json` | copy_as_is | `projects/medicoder/misc/000070.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000071.json` | copy_as_is | `projects/medicoder/misc/000071.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000072.json` | copy_as_is | `projects/medicoder/misc/000072.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000073.json` | copy_as_is | `projects/medicoder/misc/000073.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000074.json` | copy_as_is | `projects/medicoder/misc/000074.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000075.json` | copy_as_is | `projects/medicoder/misc/000075.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000076.json` | copy_as_is | `projects/medicoder/misc/000076.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000077.json` | copy_as_is | `projects/medicoder/misc/000077.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000078.json` | copy_as_is | `projects/medicoder/misc/000078.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000079.json` | copy_as_is | `projects/medicoder/misc/000079.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000080.json` | copy_as_is | `projects/medicoder/misc/000080.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000081.json` | copy_as_is | `projects/medicoder/misc/000081.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000082.json` | copy_as_is | `projects/medicoder/misc/000082.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000083.json` | copy_as_is | `projects/medicoder/misc/000083.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000084.json` | copy_as_is | `projects/medicoder/misc/000084.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000085.json` | copy_as_is | `projects/medicoder/misc/000085.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000086.json` | copy_as_is | `projects/medicoder/misc/000086.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000087.json` | copy_as_is | `projects/medicoder/misc/000087.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000088.json` | copy_as_is | `projects/medicoder/misc/000088.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000089.json` | copy_as_is | `projects/medicoder/misc/000089.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000090.json` | copy_as_is | `projects/medicoder/misc/000090.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000091.json` | copy_as_is | `projects/medicoder/misc/000091.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000092.json` | copy_as_is | `projects/medicoder/misc/000092.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000093.json` | copy_as_is | `projects/medicoder/misc/000093.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000094.json` | copy_as_is | `projects/medicoder/misc/000094.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000095.json` | copy_as_is | `projects/medicoder/misc/000095.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000096.json` | copy_as_is | `projects/medicoder/misc/000096.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000097.json` | copy_as_is | `projects/medicoder/misc/000097.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000098.json` | copy_as_is | `projects/medicoder/misc/000098.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000099.json` | copy_as_is | `projects/medicoder/misc/000099.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000100.json` | copy_as_is | `projects/medicoder/misc/000100.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000101.json` | copy_as_is | `projects/medicoder/misc/000101.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000102.json` | copy_as_is | `projects/medicoder/misc/000102.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000103.json` | copy_as_is | `projects/medicoder/misc/000103.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000104.json` | copy_as_is | `projects/medicoder/misc/000104.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000105.json` | copy_as_is | `projects/medicoder/misc/000105.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000106.json` | copy_as_is | `projects/medicoder/misc/000106.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000107.json` | copy_as_is | `projects/medicoder/misc/000107.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000108.json` | copy_as_is | `projects/medicoder/misc/000108.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000109.json` | copy_as_is | `projects/medicoder/misc/000109.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000110.json` | copy_as_is | `projects/medicoder/misc/000110.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000111.json` | copy_as_is | `projects/medicoder/misc/000111.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000112.json` | copy_as_is | `projects/medicoder/misc/000112.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000113.json` | copy_as_is | `projects/medicoder/misc/000113.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000114.json` | copy_as_is | `projects/medicoder/misc/000114.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000115.json` | copy_as_is | `projects/medicoder/misc/000115.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000116.json` | copy_as_is | `projects/medicoder/misc/000116.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000117.json` | copy_as_is | `projects/medicoder/misc/000117.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000118.json` | copy_as_is | `projects/medicoder/misc/000118.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000119.json` | copy_as_is | `projects/medicoder/misc/000119.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000120.json` | copy_as_is | `projects/medicoder/misc/000120.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/cases/000121.json` | copy_as_is | `projects/medicoder/misc/000121.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/smoke/0.json` | copy_as_is | `projects/medicoder/misc/0.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l2/000074.json` | copy_as_is | `projects/medicoder/misc/000074.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l2/000076.json` | copy_as_is | `projects/medicoder/misc/000076.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l2/000077.json` | copy_as_is | `projects/medicoder/misc/000077.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l2/000079.json` | copy_as_is | `projects/medicoder/misc/000079.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l2/000082.json` | copy_as_is | `projects/medicoder/misc/000082.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l2/000085.json` | copy_as_is | `projects/medicoder/misc/000085.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l2/000089.json` | copy_as_is | `projects/medicoder/misc/000089.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l2/000104.json` | copy_as_is | `projects/medicoder/misc/000104.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l2/000107.json` | copy_as_is | `projects/medicoder/misc/000107.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l2/000110.json` | copy_as_is | `projects/medicoder/misc/000110.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l2/000119.json` | copy_as_is | `projects/medicoder/misc/000119.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l3/000073.json` | copy_as_is | `projects/medicoder/misc/000073.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l3/000074.json` | copy_as_is | `projects/medicoder/misc/000074.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l3/000075.json` | copy_as_is | `projects/medicoder/misc/000075.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l3/000079.json` | copy_as_is | `projects/medicoder/misc/000079.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l3/000089.json` | copy_as_is | `projects/medicoder/misc/000089.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l3/000090.json` | copy_as_is | `projects/medicoder/misc/000090.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l3/000094.json` | copy_as_is | `projects/medicoder/misc/000094.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l3/000111.json` | copy_as_is | `projects/medicoder/misc/000111.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/datasets/tuning/l3/000113.json` | copy_as_is | `projects/medicoder/misc/000113.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/__main__.py` | copy_as_is | `projects/medicoder/misc/__main__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/cli.py` | copy_as_is | `projects/medicoder/misc/cli.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/config/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/config/loader.py` | copy_as_is | `projects/medicoder/misc/loader.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/config/models.py` | copy_as_is | `projects/medicoder/misc/models.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/output/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/output/html.py` | copy_as_is | `projects/medicoder/misc/html.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/output/markdown.py` | copy_as_is | `projects/medicoder/misc/markdown.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/output/metrics.py` | copy_as_is | `projects/medicoder/misc/metrics.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/output/report.py` | copy_as_is | `projects/medicoder/misc/report.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/output/summary.py` | copy_as_is | `projects/medicoder/misc/summary.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/pipeline/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/pipeline/checkpoint.py` | copy_as_is | `projects/medicoder/misc/checkpoint.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/pipeline/results.py` | copy_as_is | `projects/medicoder/misc/results.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/pipeline/runner.py` | copy_as_is | `projects/medicoder/misc/runner.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/pipeline/walk.py` | copy_as_is | `projects/medicoder/misc/walk.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/ranking/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/ranking/gemini.py` | copy_as_is | `projects/medicoder/misc/gemini.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/ranking/parse.py` | copy_as_is | `projects/medicoder/misc/parse.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/ranking/prompts.py` | copy_as_is | `projects/medicoder/misc/prompts.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/ranking/render.py` | copy_as_is | `projects/medicoder/misc/render.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/ranking/result.py` | copy_as_is | `projects/medicoder/misc/result.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/taxonomy/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/taxonomy/achi.py` | copy_as_is | `projects/medicoder/misc/achi.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/taxonomy/companions.py` | copy_as_is | `projects/medicoder/misc/companions.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/taxonomy/core.py` | copy_as_is | `projects/medicoder/misc/core.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/taxonomy/entry.py` | copy_as_is | `projects/medicoder/misc/entry.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/taxonomy/ground_truth.py` | copy_as_is | `projects/medicoder/misc/ground_truth.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/taxonomy/hierarchical.py` | copy_as_is | `projects/medicoder/misc/hierarchical.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/taxonomy/notes.py` | copy_as_is | `projects/medicoder/misc/notes.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/taxonomy/pcs.py` | copy_as_is | `projects/medicoder/misc/pcs.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/taxonomy/stubs.py` | copy_as_is | `projects/medicoder/misc/stubs.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/medicoder/taxonomy/systems.py` | copy_as_is | `projects/medicoder/misc/systems.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/pdf/ACHI.pdf` | copy_as_is | `projects/medicoder/misc/ACHI.pdf` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/pdf/ICD-10-AM.pdf` | copy_as_is | `projects/medicoder/misc/ICD-10-AM.pdf` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/requirements.txt` | copy_as_is | `projects/medicoder/misc/requirements.txt` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/results/run_2026-09-14_20-36-38/audit.json` | copy_as_is | `projects/medicoder/misc/audit.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/results/run_2026-09-14_20-36-38/checkpoint.jsonl` | copy_as_is | `projects/medicoder/misc/checkpoint.jsonl` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/results/run_2026-09-14_20-36-38/config.json` | copy_as_is | `projects/medicoder/misc/config.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/results/run_2026-09-14_20-36-38/report.html` | copy_as_is | `projects/medicoder/misc/report.html` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/results/run_2026-09-14_20-36-38/report.md` | copy_as_is | `projects/medicoder/misc/report.md` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/results/run_2026-09-14_20-36-38/results.json` | copy_as_is | `projects/medicoder/misc/results.json` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/scripts/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/scripts/generate_pcs_notes.py` | copy_as_is | `projects/medicoder/misc/generate_pcs_notes.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/scripts/lookup_icd10am.py` | copy_as_is | `projects/medicoder/misc/lookup_icd10am.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/scripts/pcs_level1_notes.yml` | copy_as_is | `projects/medicoder/misc/pcs_level1_notes.yml` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/scripts/pcs_notes.py` | copy_as_is | `projects/medicoder/misc/pcs_notes.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/config/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/config/test_loader.py` | copy_as_is | `projects/medicoder/misc/test_loader.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/output/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/output/test_metrics.py` | copy_as_is | `projects/medicoder/misc/test_metrics.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/output/test_report.py` | copy_as_is | `projects/medicoder/misc/test_report.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/output/test_summary.py` | copy_as_is | `projects/medicoder/misc/test_summary.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/pipeline/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/pipeline/fixtures.py` | copy_as_is | `projects/medicoder/misc/fixtures.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/pipeline/test_checkpoint.py` | copy_as_is | `projects/medicoder/misc/test_checkpoint.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/pipeline/test_runner.py` | copy_as_is | `projects/medicoder/misc/test_runner.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/pipeline/test_walk.py` | copy_as_is | `projects/medicoder/misc/test_walk.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/pipeline/test_walk_systems.py` | copy_as_is | `projects/medicoder/misc/test_walk_systems.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/ranking/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/ranking/test_gemini.py` | copy_as_is | `projects/medicoder/misc/test_gemini.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/ranking/test_parse.py` | copy_as_is | `projects/medicoder/misc/test_parse.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/ranking/test_prompts.py` | copy_as_is | `projects/medicoder/misc/test_prompts.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/ranking/test_render.py` | copy_as_is | `projects/medicoder/misc/test_render.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/scripts/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/scripts/test_pcs_notes.py` | copy_as_is | `projects/medicoder/misc/test_pcs_notes.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/support.py` | copy_as_is | `projects/medicoder/misc/support.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/taxonomy/__init__.py` | copy_as_is | `projects/medicoder/misc/__init__.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/taxonomy/test_achi.py` | copy_as_is | `projects/medicoder/misc/test_achi.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/taxonomy/test_companions.py` | copy_as_is | `projects/medicoder/misc/test_companions.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/taxonomy/test_core.py` | copy_as_is | `projects/medicoder/misc/test_core.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/taxonomy/test_ground_truth.py` | copy_as_is | `projects/medicoder/misc/test_ground_truth.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/taxonomy/test_hierarchical.py` | copy_as_is | `projects/medicoder/misc/test_hierarchical.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/taxonomy/test_pcs.py` | copy_as_is | `projects/medicoder/misc/test_pcs.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/test_cli.py` | copy_as_is | `projects/medicoder/misc/test_cli.py` | Unclassified AI asset from claude |
| Claude | Other | Project | `.claude/worktrees/rewrite/tests/test_end_to_end.py` | copy_as_is | `projects/medicoder/misc/test_end_to_end.py` | Unclassified AI asset from claude |
| Claude | Setting | Project | `.claude/settings.json` | translate | `projects/medicoder/project.yaml` | Claude Code workspace permissions and command allow/deny lists. |
| Claude | Setting | Executor | `.claude/settings.local.json` | copy_as_is | `migration/medicoder/original/.claude/settings.local.json` | Executor adapter / tool-specific configuration (claude). |
| Claude | Setting | Project | `.claude/worktrees/rewrite/.claude/settings.json` | translate | `projects/medicoder/project.yaml` | Claude Code workspace permissions and command allow/deny lists. |
| Claude | Setting | Executor | `.claude/worktrees/rewrite/.claude/settings.local.json` | copy_as_is | `migration/medicoder/original/.claude/worktrees/rewrite/.claude/settings.local.json` | Executor adapter / tool-specific configuration (claude). |
| Claude | Skill | Global | `.claude/skills/catchup/SKILL.md` | translate | `skills/catchup/` | Generic reusable workflow or skill across engineering repos: catchup |
| Claude | Skill | Global | `.claude/skills/pr/SKILL.md` | translate | `skills/pr/` | Generic reusable workflow or skill across engineering repos: pr |
| Claude | Workflow | Project | `.claude/workflows/audit-eval-contamination.js` | translate | `projects/medicoder/skills/audit-eval-contamination/` | Project-specific automated workflow: audit-eval-contamination.js |
| Claude | Workflow | Global | `.claude/workflows/fix-until-green.js` | translate | `skills/fix-until-green/` | Generic reusable workflow or skill across engineering repos: fix-until-green |
| Cursor | Hook | Project | `.cursor/hooks/block-bulk-git-add.sh` | translate | `projects/medicoder/safety.md` | Git safety: prevents indiscriminate git add -A or git add . |
| Cursor | Hook | Executor | `.cursor/hooks/claude-adapter.sh` | copy_as_is | `migration/medicoder/original/.cursor/hooks/claude-adapter.sh` | Executor adapter / tool-specific configuration (cursor). |
| Cursor | Hook | Project | `.cursor/hooks/readonly-sqlite.sh` | translate | `projects/medicoder/safety.md` | Database safety: ensures sqlite connections are opened in readonly mode |
| Cursor | Rule | Project | `.cursor/rules/am-full-runs.mdc` | translate | `projects/medicoder/safety.md` | Cost safety: prohibits running full evaluation pipeline without approval |
| Cursor | Setting | Executor | `.cursor/hooks.json` | copy_as_is | `migration/medicoder/original/.cursor/hooks.json` | Executor adapter / tool-specific configuration (cursor). |
| Generic | Doc | Project | `README.md` | translate | `projects/medicoder/context.md` | Project context and instructions: README.md |
| Generic | Secret | Sensitive | `.env` | security_block | `DO_NOT_MIGRATE` | Contains API keys or secrets (e.g. GEMINI_API_KEY). Must not be migrated. |
| Mcp | Mcp | Project | `.mcp.json` | translate | `projects/medicoder/project.yaml` | MCP tools configuration. |

## Safety Policies Identified

- **Database Protection**: Denies edits to `database/` snapshots.
- **Cost Controls**: Prohibits full Gemini API pipeline evaluation runs without explicit approval.
- **Git Integrity**: Blocks bulk adds (`git add -A`, `git add .`) and removes AI co-author attribution.
- **Database Integrity**: Validates SQLite queries are read-only (`-readonly`).
- **Stop Verification**: Runs test suite before completing task execution.
