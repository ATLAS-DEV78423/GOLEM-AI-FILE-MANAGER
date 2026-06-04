---
description: Run the Golem production-readiness gate (debug + UI + security + functionality)
---

# /prod-check — Golem production-readiness gate

Run the four-agent pre-release gate before shipping. This is the manual counterpart to the post-edit hook: the hook runs on every `Edit`/`Write` (cheap, finds obvious bugs), and this command runs the full gate (slower, but reads the whole codebase and runs the real test suite).

## What it does

Invokes the `prod-readiness` workflow at `.claude/workflows/prod-readiness.js`. The workflow runs four agents **in parallel**:

| Agent            | What it checks                                                                  |
|------------------|---------------------------------------------------------------------------------|
| `golem-debug`         | ruff + mypy + pytest + smoke + 50% coverage gate                          |
| `golem-ui`            | Tk UI formatting, Tk correctness, WCAG-style a11y, headless UI tests       |
| `golem-security`      | path traversal, deserialization, secrets, OWASP, network-call regressions  |
| `golem-functionality` | smoke + focused suite + 10-feature inventory + search→delete e2e trace   |

## When to use

- Before `git commit` if you want a stronger signal than the per-edit hook
- Before `git push` and opening a PR
- Before tagging a release (`git tag v2.x.y`)
- After pulling main and resolving conflicts

## Usage

```
/prod-check
```

The command runs the workflow with no arguments. The four agents fan out in parallel; the workflow aggregates findings into a single verdict:

```
prod-readiness: PASS  (3 findings, 0 blockers)
```

or

```
prod-readiness: FAIL  (7 findings, 2 blockers)
```

## How to read the output

- **overall** = `PASS` only if no agent returned `FAIL` and no `CRITICAL`/`BROKEN`/`MISSING` findings exist
- **by_agent** = the raw structured output of each agent — open these to see the details
- **findings** = flat list with `severity`, `file`, `line`, `message`, `fix`, `agent` — directly actionable
- **blockers** = the subset of findings that fail the gate (`CRITICAL` / `BROKEN` / `MISSING`)

## Editing the gate

The four agent prompts live in `.claude/agents/golem-*.md` and the orchestrator lives in `.claude/workflows/prod-readiness.js`. Edit either to retune the gate for a new project version.

## Related

- The post-edit hook in `.claude/settings.json` runs a *lightweight* version of the same four checks on every Edit/Write. It uses inline prompts, not the agent files, so it stays cheap. Use `/prod-check` for the full gate.
