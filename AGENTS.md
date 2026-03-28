# AGENTS.md

Guidance for coding agents working in `agenda-backend`.

## Project Snapshot

- Stack: FastAPI + SQLAlchemy + Alembic + PostgreSQL.
- Runtime: Python 3.12.
- Async HTTP integration: `httpx` (Evolution API / WhatsApp).
- Background jobs:
  - APScheduler reminder jobs (24h and 2h).
  - Optional WhatsApp outbox worker (env-controlled).
- API prefix default: `/api/v1`.

## Rules Files Check

- `.cursorrules`: **not present**.
- `.cursor/rules/`: **not present**.
- `.github/copilot-instructions.md`: **not present**.

If those files are added later, they override this document for conflicting guidance.

## Environment Setup

1. Create/activate venv (if needed):
   - `python -m venv venv`
   - `source venv/bin/activate`
2. Install deps:
   - `pip install -r requirements.txt`
3. Configure env:
   - `cp .env.example .env`
4. Ensure PostgreSQL is running and `DATABASE_URL` is valid.

## Core Commands

### Run app (dev)

- `python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

### Migrations

- Apply all migrations:
  - `alembic upgrade head`
- Create migration:
  - `alembic revision -m "short_description"`
- Roll back one step:
  - `alembic downgrade -1`

### Tests

- Run all tests:
  - `pytest`
- Run a file:
  - `pytest tests/test_http_integration.py`
- Run a single test function:
  - `pytest tests/test_http_integration.py::test_health_check`
- Run tests by keyword:
  - `pytest -k "whatsapp and webhook"`
- Quiet mode:
  - `pytest -q`

### Single-test workflow (recommended)

Use this sequence while iterating:

1. `pytest tests/path_to_file.py::test_name -q`
2. Fix.
3. Repeat until green.
4. Run broader subset: `pytest tests/path_to_file.py -q`.
5. Run full suite before finalizing: `pytest`.

### Docker (app image)

- Build image:
  - `docker build -t agenda-backend .`
- Container start command already runs migrations:
  - `alembic upgrade head && uvicorn app.main:app ...`

### Evolution API (local helper)

- Compose file: `infrastructure/whatsapp/docker-compose.yml`
- Start:
  - `docker compose -f infrastructure/whatsapp/docker-compose.yml up -d`

## Known Testing Caveat

- Current `tests/conftest.py` uses in-memory SQLite.
- Some models use PostgreSQL-specific types (e.g., `JSONB`), which can break schema creation under SQLite.
- If tests fail on metadata creation, run against PostgreSQL test DB or adjust test engine/type handling first.

## Architecture and Layering

Preserve the existing domain structure:

- `app/api/v1/<domain>/` -> HTTP routes only.
- `app/services/<domain>/` -> business logic / orchestration.
- `app/repositories/<domain>/` -> DB access.
- `app/models/<domain>/` -> ORM entities.
- `app/schemas/<domain>/` -> Pydantic DTOs.

Do not collapse service/repository boundaries for convenience.

## Multi-tenant Guardrails (Critical)

- Always scope operational data by `tenant_id`.
- Never trust tenant identifiers from arbitrary client payloads.
- Derive tenant context from authenticated user/session.
- Validate ownership in service/repository layers.

## Python Style Guidelines

### Imports

- Group imports in this order:
  1. stdlib
  2. third-party
  3. local `app.*`
- Keep one import per line unless tuple-style import is already idiomatic in file.
- Avoid circular imports; move imports local to function only when needed.

### Formatting

- Follow PEP 8 defaults (4-space indent, sensible line length).
- Use expressive names over comments.
- Keep functions small and focused.
- Avoid unrelated refactors in feature/fix PRs.

### Types

- Use type hints on public functions and methods.
- Prefer precise return types (`dict[str, Any]`, `list[Model]`, etc.).
- Keep optionality explicit (`str | None`).

### Naming

- Files/modules: `snake_case`.
- Classes: `PascalCase`.
- Functions/variables: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Enum values should remain backward-compatible unless migration and API impact are handled.

### FastAPI conventions

- Routes handle transport concerns only (parsing, response mapping, dependency wiring).
- Business logic belongs in services.
- DB query logic belongs in repositories.
- Keep response models explicit in route decorators.

### SQLAlchemy conventions

- Use repository methods instead of ad-hoc SQL in routes.
- Commit/refresh patterns should be consistent with existing repository style.
- Add indexes/constraints via Alembic when schema changes affect performance or integrity.

### Error handling

- Fail loudly in services/repositories when state is invalid.
- In webhook/provider callbacks, prefer safe handling:
  - log internal errors,
  - avoid retry loops caused by non-200 provider responses when appropriate.
- Never swallow exceptions silently; at minimum, log context.

### Logging

- Use structured, contextual logs when possible.
- Include tenant/message/action context in WhatsApp/webhook flows.
- Avoid logging secrets, tokens, API keys, or raw credentials.

## WhatsApp / Evolution Integration Notes

- Use `httpx` async client paths already implemented in `EvolutionClient`.
- Normalize sender phone carefully (payloads may include `@lid` and real sender JIDs).
- Webhook handlers should be idempotent (message id deduplication).
- Keep template rendering variable-compatible with frontend-configured templates.

## Scheduler / Worker Notes

- Reminder scheduler currently runs at 5-minute intervals.
- Outbox worker startup depends on `WHATSAPP_WORKER_ENABLED`.
- When changing schedule logic, verify both 24h and 2h reminder behavior.

## Security and Secrets

- Do not commit `.env` or credential files.
- Keep JWT and provider keys in env vars.
- Sanitize examples in docs and tests.

## Agent Working Practices

- Prefer minimal, targeted diffs.
- Update related schemas/tests when changing models.
- If changing DB schema, include Alembic migration in same change.
- Validate syntax quickly (`python -m py_compile ...`) when full tests are blocked.

## Definition of Done (for agent tasks)

- Code compiles.
- Relevant tests updated/added.
- Migration included for schema changes.
- Endpoints/schemas/docs kept in sync.
- No tenant isolation regressions introduced.
