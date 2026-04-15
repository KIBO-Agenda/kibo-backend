# KIBO Agenda Backend

Multi-tenant appointment SaaS backend built with FastAPI, SQLAlchemy, Alembic, and PostgreSQL. It automates WhatsApp confirmations/reminders via Evolution API, enforces tenant isolation, and ships with schedulers for 24h/2h reminders plus an optional WhatsApp outbox worker.

## Table of Contents
- [Stack & Features](#stack--features)
- [Architecture Overview](#architecture-overview)
- [Project Layout](#project-layout)
- [Prerequisites](#prerequisites)
- [Environment Configuration](#environment-configuration)
- [Local Development](#local-development)
- [Running with Docker Compose](#running-with-docker-compose)
- [Database & Migrations](#database--migrations)
- [Seed Data](#seed-data)
- [Testing](#testing)
- [Scheduler & WhatsApp Workers](#scheduler--whatsapp-workers)
- [Docs & References](#docs--references)

## Quick Start

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec backend python app/seeds/create_frontend_test_users.py
```

## Stack & Features
- **FastAPI + SQLAlchemy** service layer orchestrating multi-tenant CRUD.
- **PostgreSQL** persistence with Alembic migrations and exclusion constraints for overlapping appointments.
- **Evolution API (WhatsApp)** integration with idempotent webhook handling and template-based notifications.
- **APScheduler** background reminders (24h/2h) plus optional WhatsApp outbox worker.
- **JWT auth** with tenant isolation enforced in repositories/services.

## Architecture Overview
Directory boundaries follow domain-driven layering; never collapse responsibilities:

```
app/
├── api/v1/<domain>/     # FastAPI routes & transport concerns
├── services/<domain>/   # Business rules and orchestration
├── repositories/<domain>/
├── models/<domain>/
├── schemas/<domain>/
├── core/                # config, security, dependencies
└── db/                  # SQLAlchemy session/base
```

### Multi-Tenant Guardrails
- All repository queries include `tenant_id` filters.
- Tenant context is derived from authenticated user/session, never from arbitrary payload data.
- Webhooks, schedulers, and background workers must validate ownership before acting on resources.

### WhatsApp / Evolution API Notes
- Use `EvolutionClient` in `app/services/whatsapp` for outbound calls.
- Webhook deduplication managed by `ProcessedWebhook` records.
- Phone normalization avoids `@lid` artifacts and ensures consistent matching.
- Always respond `200 OK` to provider webhooks, even on internal errors (errors should be logged and handled internally).

## Project Layout
```
.
├── app/                      # FastAPI application modules
├── alembic/                  # Migration scripts & env
├── docs/                     # Architecture, schema, API context
├── infrastructure/           # Supporting tooling (e.g., whatsapp compose)
├── tests/                    # Pytest suite using SQLite test DB by default
├── requirements.txt          # Python dependencies
├── Dockerfile                # Production-ready container image
└── docker-compose.yml        # Backend + Evolution API + Postgres stack
```

## Prerequisites
- Python 3.12+
- PostgreSQL 15+ (local or containerized)
- Poetry/pip & virtualenv (optional but recommended)
- Docker & Docker Compose (for container workflow)

## Environment Configuration
1. Copy the sample env file:
   ```bash
   cp .env.example .env
   ```
2. Update critical entries:
   - `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/agenda`
   - `EVOLUTION_API_BASE_URL=http://localhost:8080`
   - `EVOLUTION_API_KEY=<your-dev-key>`
   - `JWT_SECRET_KEY=<random-string>`
   - `BACKEND_BASE_URL=http://127.0.0.1:8000` (used to auto-build webhook URL)

## Local Development
```bash
# 1. Create virtualenv (optional)
python -m venv venv && source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Apply migrations (requires PostgreSQL running)

# 4. Start FastAPI server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Useful Commands
- `pytest` — run entire test suite.
- `pytest tests/path::test_case -q` — focused run.
- `alembic revision -m "description"` — create migration.
- `alembic downgrade -1` — rollback last migration.
- `python -m uvicorn app.main:app --reload` — hot-reload dev server.

## Running with Docker Compose
The root `docker-compose.yml` provisions PostgreSQL, Evolution API, and the backend container using the existing `Dockerfile`.

```bash
# Build images (backend) and start entire stack
docker compose up --build

# Run stack in background
docker compose up -d

# Tear down containers + default volumes
docker compose down

# Tear down and remove volumes (destructive)
```

### Services exposed
- Backend API: `http://localhost:8000`
- Evolution API: `http://localhost:8080`
- PostgreSQL: `localhost:5432` (credentials: postgres/postgres)

### Compose Notes
- Backend container loads env vars from `.env` plus overrides defined in compose file (database host switches to `db`).
- Evolution API receives its own DB connection via the same Postgres service and posts webhooks to the backend service URL (`http://backend:8000/api/v1/webhooks/whatsapp`).
- Persistent data lives in `postgres_data` and `evolution_instances` volumes.

## Database & Migrations
- Alembic environment lives under `alembic/` with autogenerated revision scripts named `YYYYMMDD_##_description.py`.
- When adding migrations, update both the SQLAlchemy models and the Alembic script, then run `alembic upgrade head` locally and inside Docker (compose `backend` command already executes migrations at startup).
- `docs/02_database_schema.md` and `docs/agendasv1.dbml` capture schema decisions and relationships.

## Seed Data
Deterministic QA tenants/users are available via `app/seeds/create_frontend_test_users.py`.

```bash
# Inside Docker (recommended once compose stack is up)

# Directly on host (requires venv + env vars)
python app/seeds/create_frontend_test_users.py
```

The script provisions:
- Super admin `qa.superadmin@example.com / Admin1234!`
- Tenants “Barberia Centro” and “Salon Norte” with owner/staff accounts for UI testing (see script output for credentials).
  - Reminder automation is available only on `plan_tier=pro` or `plan_tier=business`. Upgrade tenants via owner settings or a direct DB/repository call before testing WhatsApp flows.

## Testing
- Default tests rely on SQLite in-memory DB (see `tests/conftest.py`).
- Some models require PostgreSQL types (`JSONB`). If SQLite fails, run tests against a PostgreSQL test DB or adjust type fallbacks.
- Recommended workflow:
  1. `pytest tests/<path>::<test> -q`
  2. Fix code until green.
  3. Run broader subset per module.
  4. Run `pytest` before committing.

## Scheduler & WhatsApp Workers
- APScheduler reminder lifecycle (`app/services/scheduler`) runs automatically on app startup, sending 24h and 2h reminders per appointment.
- WhatsApp outbox worker (`app/services/whatsapp/worker.py`) is toggled by `WHATSAPP_WORKER_ENABLED=true` in env vars; enable it when Evolution API credentials are valid.
- Both workers use asyncio tasks created in `app/main.py` lifespan hook.
- Reminder automation only runs for tenants on `plan_tier=pro` or `plan_tier=business`. Starter tenants (seed defaults) must be upgraded via owner settings or `TenantService.assign_plan`/`TenantService.update_tenant` before automatic reminders are queued.

## Docs & References
- `docs/01_architecture.md` — architectural principles.
- `docs/02_database_schema.md` — schema rules & DBML reference.
- `docs/03_execution_plan.md` — historical build plan / sequencing.
- `docs/frontend_whatsapp_automation_context.md` — frontend expectations & API contracts.
- `infrastructure/whatsapp/docker-compose.yml` — standalone Evolution API helper (legacy, superseded by root compose but still available).

For questions about strategy, tenant isolation, or WhatsApp flows, review `AGENTS.md` (agent guidance) and the docs directory before making changes.
