# Provisioning spike: does a cloned virtualenv work in a worktree?

> Recorded 2026-09-21, under the earlier orchestrator design. "The spec" and
> "Plan N" refer to documents since removed (see git history). The findings
> about the CLIs and provisioning still hold; `docs/design.md` is current.

**Date:** 2026-09-21
**Question:** The spec's Session design (§1) assumes a `cp -Rc` (APFS copy-on-write)
clone of a project's gitignored `env/` produces a working virtualenv inside a
git worktree. That was reasoning, not evidence. This spike settles it.
**Answer: yes, completely.**

## Method

Simulated a provisioned worktree **without touching the medicoder repo** — no
branch, no worktree, no index change. `git archive HEAD | tar -x` exports
exactly the tracked files a fresh worktree would contain, with zero footprint
in the source repo.

```bash
git archive HEAD | tar -x -C $S/repo      # tracked files only
cp -Rc $M/env            $S/repo/env       # provision
cp -Rc $M/datasets/smoke $S/repo/datasets/smoke
cp -Rc $M/datasets/tuning $S/repo/datasets/tuning
cd $S/repo && env/bin/python -m unittest discover -s tests -t .
```

## Results

**1. Provisioning is genuinely required.** The tracked-files export contained
392 files / 100M and **no `env/`**. Without provisioning, medicoder's test
command (`env/bin/python -m unittest ...`) cannot start at all.

**2. Copy-on-write is effectively free.** Cloning the 73M virtualenv:

```
real 0.71   user 0.00   sys 0.63
```

Sub-second, and consumes no additional disk until something writes.

**3. A cloned venv is self-contained.** This was the real risk — that shebangs
or `sys.prefix` would point back at the original location, making a "cloned"
venv secretly share state with the source:

```
prefix: .../provision/env
exe   : .../provision/env/bin/python
```

Both resolve to the **clone**. `pyvenv.cfg` travels with the copy and
determines the prefix, so site-packages resolve locally. Packages import from
the clone's own path.

**4. The spec's provision list is correct and sufficient.** With only `env/`
provisioned, **613 tests ran** and exactly one failed:

```
FileNotFoundError: [Errno 2] No such file or directory: 'datasets/smoke/0.json'
```

— which is precisely the second entry the spec already listed. After adding
`datasets/smoke/` and `datasets/tuning/`:

```
Ran 615 tests in 7.018s
OK (skipped=4)
```

**5. Total footprint: 175M** for a fully working isolated workspace, almost all
of it copy-on-write rather than real disk.

## Consequences for the design

- `mode: clone` is confirmed as the correct default. `mode: link` (symlink),
  which punches a hole in the isolation boundary, is not needed for medicoder
  at all and can stay an escape hatch.
- The `worktree.provision` list in `projects/medicoder/project.yaml` should be
  exactly:

  ```yaml
  worktree:
    provision:
      - { path: env/,             mode: clone }
      - { path: datasets/smoke/,  mode: clone }
      - { path: datasets/tuning/, mode: clone }
  ```

- `results/` (3.9G, gitignored) is correctly **not** provisioned — tests write
  into the worktree's own `results/`, which is the isolation working as
  intended.
- `database/` (98M) needs no entry: it is tracked, so every worktree gets its
  own copy and the agent physically cannot corrupt the real one. The existing
  `protected_paths: database/` rule becomes structurally true rather than
  regex-enforced.
- **Provisioning failure must be fatal.** The 613-vs-615 result shows the
  failure mode: a partially-provisioned worktree runs and produces a
  *plausible-looking* test failure that has nothing to do with the agent's
  work. An orchestrator would feed that to the lead reasoner as a real
  regression and send it chasing a phantom bug.

## Not yet verified

This spike simulated a worktree with `git archive`. It did **not** create a
real `git worktree`, because that writes a branch ref into the user's repo.
The remaining untested surface is small — `git worktree add` produces the same
tracked-file content this export did — but the first real worktree creation
should still be watched.
