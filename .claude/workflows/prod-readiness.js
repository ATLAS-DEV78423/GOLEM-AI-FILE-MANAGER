// Production-readiness workflow for Golem.
//
// Runs four specialized agents in parallel on the current diff:
//   - golem-debug         (ruff + mypy + pytest + coverage + smoke)
//   - golem-ui            (formatting + Tk correctness + a11y + headless UI tests)
//   - golem-security      (path traversal, deserialization, secrets, OWASP)
//   - golem-functionality (feature inventory + E2E CLI path + e2e trace)
//
// Triggered by:
//   - the /prod-check slash command (manual pre-release gate)
//   - the user invoking Workflow({ name: "prod-readiness" })
//
// Pipeline is the default fan-out primitive. Each stage runs in order; items
// within a stage run concurrently. The four agents are independent so they
// run in parallel (single stage, four items).
//
// Output is a single consolidated prod-readiness verdict the user can read
// at a glance and a structured findings array suitable for a CI gate.

export const meta = {
  name: 'prod-readiness',
  description: 'Golem pre-release gate: debug + UI + security + functionality agents in parallel',
  phases: [
    { title: 'Review' },
    { title: 'Aggregate' },
  ],
}

const AGENTS = [
  {
    key: 'debug',
    label: 'golem-debug',
    prompt: `You are golem-debug, the Golem project debugging agent. Golem is a local-first AI file manager for Obsidian (Python >=3.11, Tk UI, pystray). Your job: prove the current change is correct and clean.

Run the full Golem validation suite, in this order. Stop at the first failure and report — do not keep stacking noise on top of a red signal.

\`\`\`bash
# From the repo root
ruff check golem/ tests/
mypy golem/
pytest tests/ -q --tb=short
pytest tests/test_smoke.py -v
pytest tests/ --cov=golem --cov-report=term --cov-fail-under=50
\`\`\`

Then read the diff for the changed files only. Flag:
- CRITICAL: swallowed exceptions, resource leaks, threading regressions, Tk callbacks that do I/O on the main thread
- HIGH: missing type hints, mutable default arguments, subprocess with shell=True, assert in non-test code
- MEDIUM: missing docstrings, hardcoded paths that ignore GOLEM_DATA_DIR

Return your findings as a structured object.`,
    schema: {
      type: 'object',
      properties: {
        verdict: { type: 'string', enum: ['PASS', 'FAIL', 'N/A'] },
        ruff_issues: { type: 'integer' },
        mypy_issues: { type: 'integer' },
        pytest_passed: { type: 'integer' },
        pytest_failed: { type: 'integer' },
        smoke: { type: 'string', enum: ['PASS', 'FAIL', 'N/A'] },
        coverage_pct: { type: ['number', 'string'] },
        coverage_gate: { type: 'integer' },
        findings: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM'] },
              file: { type: 'string' },
              line: { type: 'integer' },
              message: { type: 'string' },
              fix: { type: 'string' },
            },
            required: ['severity', 'file', 'message'],
          },
        },
      },
      required: ['verdict', 'findings'],
    },
  },
  {
    key: 'ui',
    label: 'golem-ui',
    prompt: `You are golem-ui, the Golem UI quality agent. Scope: ui.py, ui_window.py, ui_components.py, ui_theme.py, ui_search.py, ui_onboarding.py, ui_anim.py, ui_icons.py. Skip the pass (return N/A) if no UI files are in the diff.

Check:
- Formatting: 100-char line length, import order, type hints, double quotes
- Tk correctness: destroy() on shutdown, StringVar after destroy, bind() closures over loop vars, PhotoImage lifetime, theme bypass
- Accessibility: takefocus, keyboard equivalents, text labels on icon buttons, focus order, no color-only state
- UX: modal escape, progress on long ops, messagebox text, onboarding skip, tray quit vs minimize
- Run: pytest tests/test_ui_logic.py tests/test_load.py -v

Return findings as a structured object.`,
    schema: {
      type: 'object',
      properties: {
        verdict: { type: 'string', enum: ['PASS', 'FAIL', 'N/A'] },
        files_reviewed: { type: 'array', items: { type: 'string' } },
        formatting: { type: 'string', enum: ['clean', 'issues'] },
        tk_correctness: { type: 'string', enum: ['clean', 'issues'] },
        a11y: { type: 'string', enum: ['clean', 'issues'] },
        ux_risks: { type: 'integer' },
        headless_tests: { type: 'string', enum: ['PASS', 'FAIL', 'N/A'] },
        findings: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'A11Y', 'UX'] },
              file: { type: 'string' },
              line: { type: 'integer' },
              message: { type: 'string' },
              fix: { type: 'string' },
            },
            required: ['severity', 'file', 'message'],
          },
        },
      },
      required: ['verdict', 'findings'],
    },
  },
  {
    key: 'security',
    label: 'golem-security',
    prompt: `You are golem-security, the Golem security audit agent. Golem is local-first: it reads a user-chosen Obsidian vault and writes into a per-user data dir. No network server. Calibrate severity accordingly.

Scope: any path under golem/ that touches I/O (scanner, indexer, extractor, watcher, vault_writer, organizer, undo, app, summarizer). Run:
\`\`\`bash
ruff check --select S golem/
grep -rE "(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,})" golem/ || true
\`\`\`

Flag:
- CRITICAL: path traversal (open on user path without resolve + containment), unsafe deserialization (pickle/marshal/yaml.load), shell=True / os.system, eval/exec on content, hardcoded secrets
- HIGH: input validation (extension allow-list, NUL bytes, ..), library CVEs (pypdf/python-docx/openpyxl), concurrency (watcher + scanner), logging leaks
- MEDIUM: any new network call (Golem is local-first — flag for review)

Return findings as a structured object.`,
    schema: {
      type: 'object',
      properties: {
        verdict: { type: 'string', enum: ['PASS', 'FAIL', 'N/A'] },
        ruff_s_issues: { type: 'integer' },
        secret_hits: { type: 'integer' },
        findings: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM'] },
              file: { type: 'string' },
              line: { type: 'integer' },
              message: { type: 'string' },
              fix: { type: 'string' },
            },
            required: ['severity', 'file', 'message'],
          },
        },
      },
      required: ['verdict', 'findings'],
    },
  },
  {
    key: 'functionality',
    label: 'golem-functionality',
    prompt: `You are golem-functionality, the Golem functionality verification agent. Your job: prove the user-facing product still works end-to-end. This is NOT a unit-test pass — it's "if a real user runs this build, does it do the things we say it does in the README?"

Run the executable path a real user runs:
\`\`\`bash
GOLEM_DATA_DIR=$(mktemp -d) python main.py --version
GOLEM_DATA_DIR=$(mktemp -d) python main.py --no-tray --no-watcher --no-hotkey --export $(mktemp -d)/export.json
pytest tests/test_smoke.py -v
pytest tests/test_core.py tests/test_app_lifecycle.py tests/test_extractor_fuzz.py tests/test_runtime.py tests/test_summarizer.py tests/test_tray.py tests/test_undo.py tests/test_ui_logic.py tests/test_load.py -v
\`\`\`

Then inventory the 10 advertised features:
1. CLI entry (main.py)
2. Vault scanning (scanner.py)
3. Indexing (indexer.py)
4. Search (search.py, ui_search.py)
5. Summarization (summarizer.py)
6. File watching (watcher.py)
7. Undo (undo.py, vault_writer.py)
8. Tray + hotkey (tray.py)
9. Onboarding (ui_onboarding.py)
10. Theme (ui_theme.py)

For each: present | MISSING | BROKEN. Trace the e2e flow: search-then-delete (ui_search -> search -> indexer -> app -> undo -> vault_writer). Return findings.`,
    schema: {
      type: 'object',
      properties: {
        verdict: { type: 'string', enum: ['PASS', 'FAIL', 'N/A'] },
        smoke: { type: 'string', enum: ['PASS', 'FAIL', 'N/A'] },
        focused_suite: { type: 'string' },
        features: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              n: { type: 'integer' },
              name: { type: 'string' },
              status: { type: 'string', enum: ['present', 'MISSING', 'BROKEN'] },
            },
            required: ['n', 'name', 'status'],
          },
        },
        e2e_trace: { type: 'string', enum: ['PASS', 'FAIL', 'N/A'] },
        findings: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'BROKEN', 'MISSING'] },
              file: { type: 'string' },
              line: { type: 'integer' },
              message: { type: 'string' },
              fix: { type: 'string' },
            },
            required: ['severity', 'message'],
          },
        },
      },
      required: ['verdict', 'features', 'findings'],
    },
  },
]

// Stage 1: run the four agents in parallel.
const reviews = await parallel(AGENTS.map(a => () =>
  agent(a.prompt, { label: a.label, phase: 'Review', schema: a.schema })
))

// Stage 2: aggregate into a single verdict.
const byKey = Object.fromEntries(AGENTS.map((a, i) => [a.key, reviews[i]]))
const allFindings = reviews.flatMap((r, i) =>
  (r?.findings ?? []).map(f => ({ ...f, agent: AGENTS[i].label }))
)
const blockers = allFindings.filter(f =>
  ['CRITICAL', 'BROKEN', 'MISSING'].includes(f.severity)
)
const overall = blockers.length > 0 ? 'FAIL' : (
  reviews.some(r => r?.verdict === 'FAIL') ? 'FAIL' : 'PASS'
)

log(`prod-readiness: ${overall}  (${allFindings.length} findings, ${blockers.length} blockers)`)

return {
  overall,
  by_agent: byKey,
  findings: allFindings,
  blockers,
  summary: {
    debug:         byKey.debug?.verdict,
    ui:            byKey.ui?.verdict,
    security:      byKey.security?.verdict,
    functionality: byKey.functionality?.verdict,
    total_findings: allFindings.length,
    blockers: blockers.length,
  },
}
