# Contributing to StockLens AI

Thank you for your interest in contributing. This document covers everything you need
to get a working development environment, run the test suite, follow the coding
standards, and submit a well-formed pull request.

---

## Development Environment Setup

### Prerequisites

| Tool | Minimum Version | Install Guide |
|---|---|---|
| Docker Desktop | 24.0 | <https://docs.docker.com/get-docker/> |
| Python | 3.11 | <https://www.python.org/downloads/> |
| Node.js | 18 LTS | <https://nodejs.org/> |
| Git | 2.40 | <https://git-scm.com/> |

### 1. Fork and clone

```bash
git clone https://github.com/<your-fork>/stocklens-ai.git
cd stocklens-ai
git remote add upstream https://github.com/govindp47/stocklens-ai.git
```

### 2. Create a feature branch

Always work on a branch — never commit directly to `develop` or `main`.

```bash
git checkout develop
git pull upstream develop
git checkout -b feat/your-feature-name
```

Branch naming conventions:

| Prefix | When to use |
|---|---|
| `feat/` | New feature |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `refactor/` | Refactoring with no functional change |
| `test/` | Adding or fixing tests only |
| `chore/` | Tooling, CI, dependency updates |

### 3. Set up the Python backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Verify the installation:

```bash
python -c "import app; print('OK')"
```

### 4. Set up the Node.js frontend

```bash
cd frontend
npm ci
```

### 5. Configure environment variables

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` with values appropriate for local development. The defaults in
`.env.example` work without modification when using the Docker Compose stack.

To use NVIDIA free-tier models, set `NVIDIA_API_KEY` in `backend/.env`. Get a free
key at <https://integrate.api.nvidia.com>. This is optional — Ollama is the default.

### 6. Start infrastructure services

```bash
docker compose -f infra/docker-compose.yml up -d db redis ollama
```

Pull the LLM model (one-time, ~4.1 GB):

```bash
docker compose -f infra/docker-compose.yml exec ollama ollama pull mistral:7b-instruct
```

### 7. Run the backend and frontend

```bash
# Backend (with hot-reload) — in one terminal
make dev-backend

# Frontend — in a second terminal
make dev-frontend
```

The API is available at `http://localhost:8000` and the UI at `http://localhost:3000`.

---

## Running Tests

### Unit tests (no Docker required)

```bash
make test-unit
# Equivalent: cd backend && source .venv/bin/activate && pytest tests/unit -m unit -v
```

Unit tests use `fakeredis` and `asyncpg` test utilities — no live database or Redis
instance is required.

### Integration tests (requires Docker)

```bash
make test-integration
```

This command automatically starts the test Docker Compose stack (`infra/docker-compose.test.yml`),
runs the integration test suite against a dedicated test database (port 5433), and tears down
the stack when done.

### Frontend tests

```bash
# Vitest unit tests
cd frontend && npm test

# Playwright E2E tests (requires full stack running)
cd frontend && npm run test:e2e
```

### Full test suite

```bash
make test
```

### Coverage

Backend coverage is reported by pytest-cov:

```bash
cd backend && source .venv/bin/activate && \
  pytest tests/unit -m unit --cov=app --cov-report=term-missing
```

Target: ≥ 80% coverage for all modules under `app/`.

---

## Coding Standards

### Python (backend)

**Linter: `ruff`**

```bash
cd backend && source .venv/bin/activate && ruff check app tests
cd backend && source .venv/bin/activate && ruff format app tests
```

Key rules enforced:

- `E` / `W` — pycodestyle errors and warnings
- `F` — pyflakes (undefined names, unused imports)
- `I` — isort (import ordering)
- `UP` — pyupgrade (modern Python syntax)
- `B` — flake8-bugbear (common bug patterns)

**Type checker: `mypy` (strict mode)**

```bash
cd backend && source .venv/bin/activate && mypy app --strict
```

Requirements:

- All function arguments and return types must be annotated.
- No `Any` unless explicitly justified with a `# type: ignore[misc]` comment.
- `Optional[X]` must be written as `X | None` (Python 3.10+ union syntax).

**Architecture rules:**

- Pipeline steps (`app/pipeline/steps/`) must **not** import from `app/api/` or
  `app/infrastructure/`. All dependencies are injected via `PipelineContext`.
- Prompt text must **not** appear in step implementations. All prompts live in
  `backend/prompts/*.j2` templates loaded by `PromptLoader`.
- SQL queries must use parameterised asyncpg bindings (`$1`, `$2`, …) — no string
  interpolation in queries.
- All new environment variables must be added to both `app/config.py` (as a `Settings`
  field) and `backend/.env.example` (with an inline comment).
- New LLM providers must satisfy the `LLMProvider` Protocol
  (`app/infrastructure/providers/llm_provider.py`) structurally — implement `model_name`
  property and `async complete(prompt, max_tokens, temperature) -> str`. Wire the new
  provider into `get_llm_provider()` in `app/api/dependencies.py` via a new
  `X-LLM-Provider` header value.

### TypeScript / React (frontend)

**Linter + formatter: `eslint` + `prettier`**

```bash
cd frontend && npx eslint .
cd frontend && npx prettier --check .
cd frontend && npx prettier --write .      # auto-format
```

**Type checker: `tsc`**

```bash
cd frontend && npx tsc --noEmit
```

Requirements:

- Strict TypeScript (`strict: true` in `tsconfig.json`) — no `any`, no implicit `any`.
- All Zustand store slices must be fully typed.
- React components must use named exports; no default exports for components.
- Recharts must be imported with `dynamic(..., { ssr: false })` to prevent
  Next.js hydration errors.

**Accessibility requirements:**

- All new interactive elements must have an `aria-label` or associated `<label>`.
- Colour contrast must meet WCAG 2.1 AA (4.5:1 for normal text, 3:1 for large text).
- Run `axe-core` locally before submitting UI changes:

```bash
cd frontend && npm run test:e2e -- --grep "axe"
```

### Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```bash
<type>(<scope>): <short description>

[optional body]

[optional footer(s)]
```

Examples:

```bash
feat(pipeline): add corrective retry to LLM output parser
fix(sse): prevent subscriber leak on client disconnect
docs(readme): update Quick Start for Docker Compose v2
test(sentiment): add property test for distribution rounding invariant
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `perf`, `build`.

---

## Pull Request Checklist

Before opening a pull request, verify every item below:

### Code Quality

- [ ] `make lint` passes with zero warnings (`ruff` + `eslint`)
- [ ] `make typecheck` passes with zero errors (`mypy --strict` + `tsc --noEmit`)
- [ ] No `print()` statements in backend code (use `structlog` logger)
- [ ] No `console.log()` statements in frontend code (remove or replace with no-op)
- [ ] No hardcoded secrets, API keys, or passwords anywhere in the diff

### Tests

- [ ] `make test-unit` passes (all unit tests green)
- [ ] New functionality has corresponding unit tests
- [ ] Integration tests pass if the change touches database queries, Redis, or API routes
- [ ] Frontend Vitest tests pass (`cd frontend && npm test`)
- [ ] If the change affects the UI, Playwright E2E tests pass

### Architecture

- [ ] Pipeline step changes do not introduce imports from `app/api/` or `app/infrastructure/`
- [ ] New SQL uses parameterised queries (no f-strings in SQL)
- [ ] New environment variables are added to `app/config.py` and `backend/.env.example`
- [ ] New API endpoints include Pydantic request/response models in `app/api/models/`
- [ ] New LLM providers satisfy the `LLMProvider` Protocol and are wired in `dependencies.py`

### Documentation

- [ ] Docstrings added for new public functions and classes
- [ ] `CHANGELOG.md` updated under `[Unreleased]` with a brief description of the change
- [ ] `README.md` updated if the change affects the Quick Start or public-facing behaviour

### Git Hygiene

- [ ] Branch is up to date with `upstream/develop` (rebased, not merged)
- [ ] Commit messages follow Conventional Commits format
- [ ] No fixup/WIP commits in the branch — squash before opening the PR
- [ ] PR title follows the Conventional Commits format

### Review

Pull requests require **1 approving review** from a maintainer before merging.
Maintainers merge using **squash-and-merge** to keep the `develop` branch history linear.

---

## Questions?

Open a [GitHub Discussion](https://github.com/govindp47/stocklens-ai/discussions) for
general questions, or file a [GitHub Issue](https://github.com/govindp47/stocklens-ai/issues)
for bugs and feature requests.
