# Execution Plan (Build -> Pause -> Test)

## Phase 1 - Context Generation
- Create context docs for architecture, schema, and execution plan.
- Ensure folder scaffolding by domain exists.
- Add base runtime files:
  - `app/core/config.py`
  - `app/db/session.py`
  - `app/main.py`
- Initialize Alembic environment (`alembic init`).
- Pause and wait for approval.

## Phase 2 - Modular Development
1. auth + super_admin
2. tenant + users
3. clients + services
4. appointments

For each module:
- Implement model, schema, repository, service, and router.
- Enforce tenant filtering in repositories.
- Stop after module completion and request test confirmation before continuing.

## Test Gate Per Module
- Run app import smoke check and API startup.
- Validate repository tenant filters.
- Validate migration generation and upgrade for new entities.
- For appointments: validate overlap prevention by exclusion constraint.
