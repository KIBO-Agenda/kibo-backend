# API Contract Update - 2026-03-18

## Scope
This document describes backend contract changes for staff activation, plan-quota enforcement, appointment filtering by active staff, tenant settings read endpoint, and services price consistency.

## 1) Staff Activation Endpoint

### Endpoint
`PATCH /api/v1/users/{user_id}/activate`

### Auth
- Tenant owner only (`owner` role in the same tenant).

### Behavior
- Activates an inactive `staff` user from the same tenant.

### Validations
- `404`: user does not exist in owner tenant.
- `400`: user exists but role is not `staff`.
- `409`: user is already active.
- `403`: activation would exceed `tenant.max_users` considering only active `staff`.

### Success Response (200)
```json
{
  "id": "uuid",
  "name": "string",
  "email": "string",
  "role": "staff",
  "is_active": true
}
```

## 2) Plan Quota Rule (`max_users`)
- Rule is shared by:
  - `POST /api/v1/users/staff`
  - `PATCH /api/v1/users/{user_id}/activate`
- Quota count uses active `staff` only.
- `owner` does not consume specialist quota.
- Error when exceeded:
```json
{
  "detail": "Limite de especialistas alcanzado"
}
```

## 3) Appointments with Inactive Staff

### Affected endpoints
- `GET /api/v1/appointments/agenda`
- `GET /api/v1/appointments/weekly`
- `GET /api/v1/appointments/availability`
- `POST /api/v1/appointments`

### Behavior
- Agenda/weekly exclude appointments assigned to inactive staff.
- Availability returns `400` when `staff_id` belongs to inactive staff.
- Create appointment returns `400` when `user_id` is inactive.

### Error payload examples
```json
{
  "detail": "Staff user is inactive"
}
```

```json
{
  "detail": "Assigned user is inactive"
}
```

## 4) Tenant Settings Read/Write Contract

### Stable read endpoint
`GET /api/v1/tenants/settings` (owner only)

### Update endpoint
`PATCH /api/v1/tenants/settings` (owner only)

### Response shape (both)
```json
{
  "id": "uuid",
  "name": "string",
  "phone": "string|null",
  "subscription_status": "active|past_due|suspended",
  "slot_duration": 15,
  "max_users": 5,
  "business_hours": {
    "monday": {"is_open": true, "open": "08:00", "close": "18:00"},
    "tuesday": {"is_open": true, "open": "08:00", "close": "18:00"},
    "wednesday": {"is_open": true, "open": "08:00", "close": "18:00"},
    "thursday": {"is_open": true, "open": "08:00", "close": "18:00"},
    "friday": {"is_open": true, "open": "08:00", "close": "18:00"},
    "saturday": {"is_open": true, "open": "08:00", "close": "18:00"},
    "sunday": {"is_open": false, "open": "08:00", "close": "18:00"}
  }
}
```

## 5) Services Contract (`price`)
- `GET /api/v1/services` returns `price` for each service.
- `POST /api/v1/services` and `PATCH /api/v1/services/{service_id}` persist decimal `price` correctly.
- No schema migration was required in this update because `price` already exists and is persisted.

## Error Envelope
Errors remain consistent:
```json
{
  "detail": "mensaje claro"
}
```

## Basic Audit Logging
- Staff activation emits an audit info log.
- Staff deactivation via soft-delete emits an audit info log.

## Breaking Changes
1. New owner endpoint `GET /api/v1/tenants/settings` added. This is additive and non-breaking.
2. `POST /api/v1/appointments` now rejects inactive assignees with `400`.
3. Agenda/weekly now omit appointments linked to inactive staff, which may change totals in existing dashboards.
4. `GET /api/v1/appointments/availability` now returns `400` for inactive `staff_id` instead of computing slots.
