# Frontend Context: WhatsApp Automation (KIBO)

This document is the handoff context for the frontend AI agent (React) to implement UI changes aligned with the current backend behavior.

## 1) Scope and Goal

Enable owners to configure and monitor WhatsApp automation flows for appointments:

- Auto reminders (24h and 2h)
- Inbound command outcomes (`1` confirm, `2` cancel, `3` reschedule request)
- Waitlist suggestion flow after cancellation
- Message template customization with preview

Important: inbound webhook processing is backend-only. Frontend must expose status/observability and settings.

## 2) Backend Behavior Implemented

### 2.1 Appointment status lifecycle (updated)

`AppointmentStatus` now includes:

- `pending`
- `confirmed`
- `cancelled`
- `attended`
- `reschedule_req` (new)

`reschedule_req` is set when user replies `3` on WhatsApp.

### 2.2 Notification tracking (updated)

Appointments now track:

- `last_notification_type`: `none | reminder_24h | reminder_2h`

Used by scheduler to prevent repeated sends.

### 2.3 Webhook processing (updated)

Inbound endpoint:

- `POST /api/v1/webhooks/whatsapp`

Current processing:

- Normalizes event (`messages.upsert` accepted)
- Ignores outgoing (`fromMe=true`)
- Uses sender phone from real JID fields (prioritizes sender JID, ignores `@lid`)
- Deduplicates by message id (`key.id`) internally
- Commands:
  - `1` -> nearest pending appointment -> `confirmed`
  - `2` -> nearest pending appointment -> `cancelled`, then waitlist trigger
  - `3` -> nearest pending appointment -> `reschedule_req`, sends reschedule link + available hours
- If no command and no pending in next 24h for sender, sends welcome message
- Always returns HTTP 200 (even on internal errors, with reason in body)

### 2.4 Scheduler behavior (updated)

Background jobs run every 5 minutes:

- 24h job: pending appointments for tomorrow -> sends `reminder_24h` if `last_notification_type != reminder_24h`
- 2h job: pending appointments in next 2 hours -> sends `reminder_2h` if `last_notification_type != reminder_2h`

## 3) Endpoints Frontend Should Use

## 3.1 WhatsApp connection/session

- `POST /api/v1/whatsapp/create-instance`
- `GET /api/v1/whatsapp/get-qr`
- `GET /api/v1/whatsapp/status`
- `DELETE /api/v1/whatsapp/logout`

Use these for onboarding and connection status card.

### 3.2 Outbox monitoring (already available)

- `GET /api/v1/messaging/outbox/stats`
- `GET /api/v1/messaging/outbox/messages`
- `POST /api/v1/messaging/outbox/enqueue`
- `POST /api/v1/messaging/outbox/{message_id}/retry`

Use for observability panel (sent/failed/pending, recent deliveries, manual retry).

### 3.3 Appointments

- `GET /api/v1/appointments`
- `GET /api/v1/appointments/agenda`
- `GET /api/v1/appointments/weekly`
- `GET /api/v1/appointments/{appointment_id}`
- `PATCH /api/v1/appointments/{appointment_id}/status`

Frontend must support rendering `status = reschedule_req` in all relevant views.

### 3.4 Waitlist

- `POST /api/v1/waitlists`
- `GET /api/v1/waitlists`
- `PATCH /api/v1/waitlists/{waitlist_id}/resolve`

Contract change:

- Request now supports `service_id` (optional)
- Response now includes `service_id`

## 4) Template Configuration and Preview

Templates are stored in tenant settings (`message_templates`) and already include keys:

- `welcome_message`
- `reminder_24h`
- `reminder_2h`
- `waitlist_notification`

Allowed tokens currently recognized by backend template engine:

- `{nombre}`
- `{negocio}`
- `{fecha}`
- `{hora}`
- `{servicio}`
- `{horas_disponibles_hoy}`
- `{hora_disponible}`

Frontend requirements:

- Keep template editor + live preview for these message types
- Validate token usage client-side (warn unknown tokens)
- Show realistic preview examples like:
  - `Hola Laura, Bienvenido a Kibo Studio... {horas_disponibles_hoy}`
  - `Hola Laura, recordatorio de tu cita manana...`

## 5) UI Changes Required in React

### 5.1 Appointment UI

- Add visual state for `reschedule_req`
- Suggested label: `Reagendacion solicitada`
- Add filter chip for `reschedule_req` in agenda/weekly

### 5.2 WhatsApp automation dashboard

- Connection widget (status/QR/connect/logout)
- Automation health widget:
  - outbox stats
  - last messages list
  - failed/retry actions
- Explain command flow to owner:
  - `1 confirmar`
  - `2 cancelar`
  - `3 reagendar`

### 5.3 Waitlist UX

- On waitlist create form, include optional `service_id`
- Add hint that cancellation may notify owner before offering slot

### 5.4 Templates UX

- Group templates by message type
- Include preview with mock variables
- Show backend-supported tokens helper

## 6) Missing/To Coordinate with Backend

The following config exists at model level but currently has no dedicated public owner endpoint in this repo snapshot:

- `waitlist_manual_approval`
- `whatsapp_enabled`

Frontend agent should prepare settings UI, but API wiring requires backend endpoint exposure (recommended: GET/PATCH tenant WhatsApp config endpoint).

## 7) Suggested Frontend Acceptance Tests

- Appointment list renders `reschedule_req` correctly.
- WhatsApp status card reflects connected/disconnected and QR flow.
- Outbox list and stats refresh works.
- Template editor preserves supported placeholders and warns invalid tokens.
- Waitlist create sends optional `service_id`.

## 8) Operational Notes

- Scheduler dispatch is asynchronous and interval-based (5 minutes).
- For “appointment tomorrow”, reminder can be sent on next scheduler cycle after creation.
- Webhook activity depends on Evolution webhook URL pointing to:
  - `/api/v1/webhooks/whatsapp`
