# Golem Claude Agents & Workflows

Project-local definitions for the four-agent production-readiness gate and its orchestrator workflow.

## Layout

```
.claude/
├── agents/
│   ├── golem-debug.md          # ruff + mypy + pytest + smoke + coverage
│   ├── golem-ui.md             # Tk UI: formatting + correctness + a11y
│   ├── golem-security.md       # path traversal, secrets, OWASP, no-network
│   └── golem-functionality.md  # 10-feature inventory + e2e CLI path
├── workflows/
│   └── prod-readiness.js       # Orchestrator: runs all 4 agents in parallel
├── commands/
│   └── prod-check.md           # /prod-check slash command
└── settings.json               # PostToolUse hooks (lightweight, inline)
```

## Two ways to run the gate

### 1. Per-edit (cheap, auto)
The four `agent`-type hooks in `.claude/settings.json` fire on every `Edit`/`Write` with inline prompts. They run inline and are tuned to be fast — they don't always run the test suite.

### 2. Pre-release (full, manual)
Run the full gate any time with:

```
/prod-check
```

This invokes `Workflow({ name: 'prod-readiness' })` which loads `.claude/workflows/prod-readiness.js`. The four agents fan out **in parallel**, return structured findings, and the workflow aggregates them into a single verdict.

Use `/prod-check` before:
- `git commit` (optional, if you want stronger signal than the hook)
- `git push` and opening a PR
- Tagging a release (`git tag vX.Y.Z`)
- After pulling `main` and resolving conflicts

## How to read the verdict

```
prod-readiness: PASS  (3 findings, 0 blockers)   ← ship it
prod-readiness: FAIL  (7 findings, 2 blockers)   ← fix the blockers first
```

- `blockers` are findings with severity `CRITICAL` / `BROKEN` / `MISSING`
- Each finding has `file`, `line`, `message`, `fix`, and the `agent` that found it

## Tuning the gate

- Edit any agent file under `.claude/agents/` to change what one agent looks for
- Edit `.claude/workflows/prod-readiness.js` to change aggregation logic, timeouts, or which agents run
- The post-edit hook prompts in `.claude/settings.json` are intentionally separate — keep them inline so they stay fast

## Reuse across projects

The agent files are Golem-specific (cite Golem modules, the Tk UI, the 50% coverage gate, `test_smoke.py`). To use them in another project, copy the structure and rewrite the project-specific bits. The shape (one agent per concern + one orchestrator) is the reusable part.
