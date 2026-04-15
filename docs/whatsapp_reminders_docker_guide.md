# Guia Docker: Webhook y recordatorios WhatsApp

Esta guia concentra comandos para operar flujo WhatsApp en contenedor `backend`.

## 0) Prerrequisito clave

Si agregaste archivos Python nuevos (por ejemplo `app/scripts/send_tomorrow_reminders.py`), debes reconstruir imagen de `backend`.

Comandos:

```bash
docker compose build backend
docker compose up -d backend
```

Si usas alias `dc`:

```bash
dc build backend
dc up -d backend
```

## 1) Migraciones (incluye schema `whatsapp`)

```bash
dc exec backend alembic upgrade head
```

Verifica tablas movidas:

```bash
dc exec db psql -U postgres -d agenda -c "\dt whatsapp.*"
```

## 2) Ejecutar script de recordatorios de manana

### Enviar a todas citas de manana (forzado por defecto)

```bash
dc exec backend python -m app.scripts.send_tomorrow_reminders
```

### Solo ver candidatos (sin enviar)

```bash
dc exec backend python -m app.scripts.send_tomorrow_reminders --dry-run
```

### Respetar ya enviados (`reminder_24h_sent=true`)

```bash
dc exec backend python -m app.scripts.send_tomorrow_reminders --respect-sent
```

### Filtrar por tenant

```bash
dc exec backend python -m app.scripts.send_tomorrow_reminders --tenant-id <TENANT_UUID>
```

## 3) Error comun: `No module named app.scripts.send_tomorrow_reminders`

Causa tipica: contenedor corre imagen vieja (sin script nuevo).

Pasos:

```bash
dc build backend
dc up -d backend
dc exec backend python -m app.scripts.send_tomorrow_reminders --dry-run
```

Si persiste:

```bash
dc exec backend ls app/scripts
```

Debe aparecer `send_tomorrow_reminders.py`.

## 4) Sync webhook de Evolution (por tenant)

Endpoint nuevo:

`POST /api/v1/whatsapp/sync-webhook`

Ejemplo:

```bash
curl -X POST "http://localhost:8000/api/v1/whatsapp/sync-webhook" \
  -H "Authorization: Bearer <OWNER_JWT>" \
  -H "Content-Type: application/json"
```

Respuesta esperada incluye `ok`, `instance_name`, `webhook_url`.

## 5) Variables recomendadas en `.env`

Para entorno con ngrok en Evolution API:

```env
EVOLUTION_API_BASE_URL=https://swollenly-congregational-felicia.ngrok-free.dev
EVOLUTION_WEBHOOK_URL=https://<tu-backend-publico>/api/v1/webhooks/whatsapp
WHATSAPP_DB_SCHEMA=whatsapp
```

Luego reinicia backend:

```bash
dc up -d --build backend
```

## 6) Comandos de verificacion rapida

```bash
dc logs backend --tail=200
dc logs evolution-api --tail=200
dc exec backend python -m app.scripts.send_tomorrow_reminders --dry-run
```

Busca logs de scheduler/outbox con contexto de `tenant`, `appointment`, `phone` para diagnostico.
