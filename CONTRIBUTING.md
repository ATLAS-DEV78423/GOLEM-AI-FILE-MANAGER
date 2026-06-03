# Contributing to GOLEM

Thanks for your interest in making GOLEM better. This document covers the
mechanics of contributing. For the design vision, see
[`GOLEM_Master_Reference.md`](GOLEM_Master_Reference.md).

## Development setup

GOLEM targets Python 3.11+ on Windows and macOS.

```bash
git clone https://github.com/ATLAS-DEV78423/GOLEM-AI-FILE-MANAGER
cd GOLEM-AI-FILE-MANAGER
python -m venv .venv
source .venv/bin/activate     # or .venv\Scripts\activate on Windows
pip install -r requirements.txt -r requirements-dev.txt
python main.py
```

Pre-commit hooks catch the most common style issues before they reach CI:

```bash
pip install pre-commit
pre-commit install
```

## Running the tests

```bash
pytest                       # all tests
pytest -k installer          # one suite
pytest --cov=golem --cov-fail-under=70
```

The tests use `tempfile.mkdtemp()` to create isolated sandboxes; they
clean up after themselves. The installer tests mock PowerShell and the
Windows registry, so they run on any platform.

## Code style

- Black-style 100-character lines. `ruff format` enforces it.
- Type hints on every public function. `mypy golem/` must pass.
- Prefer small, named functions over clever one-liners. Tests should be
  able to mock individual helpers.
- Use the `GolemError` hierarchy in `golem/errors.py` for any exception
  that the user might see. Bare `Exception` is for truly unexpected
  cases.
- Log with a module-level logger: `logger = logging.getLogger(__name__)`.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add case-insensitive path comparison in search rerank
fix: migrate legacy groq_api_key to llm_api_key on initialize
docs: document --export-db CLI flag
chore: split requirements.txt into dev and build variants
```

## Pull request process

1. Open an issue first for non-trivial changes. The maintainer may have
   context you do not.
2. Fork and branch from `main`. Use a descriptive branch name:
   `fix/scanner-rollback-when-stat-fails`.
3. Keep PRs focused. One concern per PR.
4. Make sure `pytest` and `ruff check .` pass before pushing.
5. Reference the issue in the PR description: "Closes #42".
6. Wait for review. We aim to respond within a week.

## Security

If you find a security vulnerability, **do not open a public issue.**
See [`docs/SECURITY.md`](docs/SECURITY.md) for the disclosure process.
