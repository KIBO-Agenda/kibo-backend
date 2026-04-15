# Contexto Tecnico: Confirmaciones WhatsApp Multi-Tenant

## 1) Objetivo del documento

Este documento resume el problema actual del flujo de confirmaciones por WhatsApp en KIBO, el estado tecnico real del sistema, lo que se esta implementando y los resultados esperados para tener un comportamiento 100% multi-tenant, trazable y seguro.

## 2) Tecnologias involucradas

- Backend: FastAPI (Python 3.12)
- ORM y migraciones: SQLAlchemy + Alembic
- Base de datos: PostgreSQL (esquemas `public` y `whatsapp`)
- Integracion WhatsApp: Evolution API v2.x
- Cliente HTTP: `httpx`
- Procesos asincronos/periodicos:
  - Scheduler de recordatorios (24h y 2h)
  - Worker de outbox opcional (segun `WHATSAPP_WORKER_ENABLED`)
- Contenedores locales: `docker compose` (`agenda-backend`, `agenda-db`, `evolution-api`)

## 3) Modelo de datos relevante

### Esquema `public` (dominio de negocio)

- `tenants`
  - Identidad del negocio
  - `whatsapp_instance_id` para mapear webhook -> tenant
  - `whatsapp_apikey` para credencial por tenant (si aplica)
- `clients`
  - Telefono del cliente y opt-out
- `appointments`
  - Estado de cita (`pending`, `confirmed`, etc.)
  - `whatsapp_remote_id` para correlacion de conversacion/jid
  - marcadores de recordatorio (`reminder_24h_sent`, `reminder_2h_sent`)
- `tenant_configs`
  - `whatsapp_enabled`, aprobacion manual de waitlist

### Esquema `whatsapp` (operacion/mensajeria)

- `processed_webhooks`
  - idempotencia por `message_id`
- `whatsapp_outbox`, `whatsapp_sessions`, `conversation_contexts`
  - soporte de envio y contexto conversacional
- Tablas internas Evolution (`Instance`, `Message`, `Contact`, `Chat`, `Webhook`, etc.)
  - metadata operativa del proveedor

## 4) Flujo esperado (target funcional)

Cuando llega un webhook con texto `"1"`:

1. Identificar `instance` del payload.
2. Resolver el tenant por `tenants.whatsapp_instance_id`.
3. Buscar cita pendiente **solo dentro de ese tenant**:
   - prioridad: `whatsapp_remote_id` (jid/lid)
   - fallback: telefono del remitente normalizado
4. Si hay cita:
   - actualizar a `CONFIRMED`
   - enviar confirmacion al cliente que respondio
   - usar credenciales dinamicas de ese tenant (instance + apikey)
5. Registrar evento en `whatsapp.processed_webhooks` para idempotencia.

## 5) Problema observado en produccion/local

Sintoma reportado:

- El cliente responde `"1"` al recordatorio.
- El webhook se acepta (`200 OK`), pero retorna:
  - `processed=false`
  - `reason=pending_appointment_not_found`

Detalle tecnico del caso reportado:

- Payload entrante:
  - `instance`: `fbff3237-45ce-4045-8d35-c355f293d495`
  - `sender`: `573008862735@s.whatsapp.net`
  - `data.key.remoteJid`: `138646644625645@lid`
- Citas `pending` del tenant involucrado estaban con:
  - telefono cliente: `3134054628`
  - `whatsapp_remote_id`: `573134054628@s.whatsapp.net`

Conclusion del mismatch:

- No coincide ni por `remote_id` ni por telefono del remitente.
- El sistema no puede asociar de forma deterministica esa respuesta a una cita pendiente.

## 6) Hallazgos operativos importantes

- En una inspeccion previa hubo desalineacion de runtime:
  - contenedor backend corriendo codigo anterior al ultimo refactor
  - version de migracion no siempre alineada con cambios (`alembic_version`)
- El 403 en `create-instance` no siempre era auth:
  - Evolution tambien responde 403 cuando el nombre de instancia ya existe
- Se validaron multiples instancias activas en Evolution con distintos `ownerJid`.

## 7) Causa raiz tecnica actual

La confirmacion falla porque el identificador entrante en webhook (`@lid`/`sender`) no mapea a la cita pendiente guardada (`whatsapp_remote_id`/telefono) dentro del tenant de forma consistente en todos los escenarios.

En otras palabras:

- El sistema ya esta aislando por tenant (correcto).
- Pero falta robustez en la correlacion `respuesta -> cita` cuando Evolution entrega `remoteJid` tipo `@lid` y el reminder original quedo con otro identificador.

## 8) Lineas de trabajo en curso

1. Enrutamiento multi-tenant por `instance` (ya implementado).
2. Envio dinamico por tenant (instance + apikey).
3. Eliminacion de respuestas a numero hardcodeado y uso de remitente real.
4. Endurecer estrategia de matching para `@lid`:
   - `remote_id` exacto
   - telefono normalizado
   - fallback controlado y seguro (sin romper aislamiento tenant)
5. Observabilidad:
   - logs de entrada, criterio de match, id de cita y salida

## 9) Resultados esperados (criterios de aceptacion)

- Si el cliente correcto responde `"1"`:
  - la cita del tenant correcto pasa de `pending` a `confirmed`
  - se envia mensaje de confirmacion al cliente correcto
- Si responde un numero no asociado:
  - no se confirma ninguna cita
  - se responde `pending_appointment_not_found` o mensaje de guia
- Nunca se cruza informacion entre tenants.
- Idempotencia: reintentos con mismo `message_id` no duplican acciones.
- Logs minimos requeridos:
  - identificacion de `instance` y tenant
  - criterio de match usado
  - `[WH] Respuesta enviada desde Instancia: {instance} hacia Cliente: {customer_number}.`

## 10) Proceso recomendado de validacion end-to-end

1. Confirmar despliegue de codigo y migraciones (`alembic upgrade head`).
2. Verificar `tenant.whatsapp_instance_id` y, si aplica, `tenant.whatsapp_apikey`.
3. Crear cita `pending` para un cliente de prueba.
4. Forzar/envio de recordatorio 24h o 2h.
5. Responder `"1"` desde el mismo chat.
6. Validar:
   - estado en `appointments`
   - `processed_webhooks`
   - logica de match registrada en logs
   - mensaje de confirmacion emitido

## 11) Entregable de esquema completo

Se genero el DBML completo desde metadata real de PostgreSQL, incluyendo tablas `public` y `whatsapp`:

- `docs/kibo_full_schema.dbml`

Este archivo representa el estado actual de la base de datos y relaciones FK existentes en el entorno inspeccionado.
