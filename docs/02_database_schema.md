# Database Schema Context

## Source of Truth
- DBML file: `docs/agendasv1.dbml`

## Core Design Notes
- PostgreSQL is required.
- All tenant-scoped tables must include `tenant_id`.
- Tenant-scoped foreign keys must preserve isolation boundaries.
- Operational indexes should include `tenant_id` as first key when possible.

## Appointment Collision Rule
- Use PostgreSQL exclusion constraints to prevent overlapping appointments.
- Constraint strategy:
  - `EXCLUDE USING gist`
  - compare `resource_id`/`staff_id` with `=`
  - compare `tsrange(start_at, end_at, '[)')` with `&&`
- Enable extension `btree_gist` through Alembic migration when needed.

## Migration Strategy
- Manage schema evolution through Alembic revisions.
- Keep constraints and indexes explicit in migrations.
- Use transactional migrations and reversible operations where possible.
