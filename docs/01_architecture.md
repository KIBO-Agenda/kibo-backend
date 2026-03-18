# Architecture Overview

## Objective
Backend for a multi-tenant appointment micro-SaaS using FastAPI, PostgreSQL, SQLAlchemy, and Alembic.

## Principles
- KISS first: simple and explicit implementations.
- Repository pattern for data access.
- Service layer for business rules.
- Dependency injection with FastAPI `Depends`.
- Strict tenant isolation: all operational queries must include `tenant_id`.

## Layered Structure by Domain
- `app/api/v1/<domain>/`: HTTP routes and request wiring.
- `app/services/<domain>/`: business use cases.
- `app/repositories/<domain>/`: database access with SQLAlchemy.
- `app/models/<domain>/`: ORM entities.
- `app/schemas/<domain>/`: Pydantic DTOs.
- `app/core/`: app settings, security, JWT helpers.
- `app/db/`: SQLAlchemy base and session management.
- `app/seeds/`: seed scripts.

## Multi-Tenant Guardrails
- Every repository operation (list/get/update/delete/create when relevant) must enforce `tenant_id` in filters or ownership checks.
- Domain services must receive `tenant_id` from authenticated context and pass it to repositories.
- API handlers must never accept cross-tenant access from client-controlled input.

## Concurrency and Appointments
- Appointment collisions will be prevented at DB level with PostgreSQL `EXCLUDE USING gist` over a `tsrange`.
- Application-level availability checks are complementary, not a replacement for DB constraints.

## Planned Module Order
1. auth + super_admin
2. tenant + users
3. clients + services
4. appointments
