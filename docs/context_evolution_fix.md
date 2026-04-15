Déjame leer primero el schema completo y el contexto antes de buscar en la documentación.Ahora busco la documentación oficial de Evolution API v2 para entender el payload exacto de webhooks y el comportamiento de `@lid`.Tengo todo lo que necesito. La investigación confirma exactamente el problema y además encontré el campo clave que resuelve todo. Aquí va el diagnóstico y plan completo.

---

## Diagnóstico: lo que está pasando exactamente

Primero, la buena noticia: **tu arquitectura multi-tenant está correcta**. El aislamiento por `instance` ya funciona. El problema es específico del protocolo de WhatsApp, no de tu código.

### El bug `@lid` — qué es y por qué ocurre

Cuando un mensaje llega de un contacto con Android, Evolution API recibe el `remoteJid` como un LID numérico (`138646644625645@lid`) en lugar del número real (`573134054628@s.whatsapp.net`). Con iPhone el número llega correcto. Es un bug conocido que afecta múltiples versiones.

Tu caso en producción lo demuestra exactamente:
- Tú guardaste en `appointments.whatsapp_remote_id` → `573134054628@s.whatsapp.net`  
- El webhook llegó con `remoteJid` → `138646644625645@lid`
- No hay match → `pending_appointment_not_found`

En versiones v2.3.0+, cuando el `remoteJid` viene como `@lid`, aparece un nuevo campo llamado `senderPn` en el payload que contiene el `remoteJid` real con el número de teléfono. Ese campo es tu salvación.

---

## El plan de implementación completo

### Paso 1 — Actualiza Evolution API a v2.3.0 o superior (hoy)

Antes de cambiar una sola línea de código, asegúrate de estar en v2.3.0+. Es la versión que introdujo `senderPn`. Verifica con:

```bash
curl -s http://tu-hetzner:8080/manager/info | grep version
```

Si estás en versión anterior, actualiza el contenedor antes de continuar.

---

### Paso 2 — Entiende el payload completo que llega

El webhook `MESSAGES_UPSERT` de Evolution tiene esta estructura relevante para ti:

```json
{
  "event": "messages.upsert",
  "instance": "fbff3237-45ce-4045-8d35-c355f293d495",
  "data": {
    "key": {
      "remoteJid": "138646644625645@lid",
      "fromMe": false,
      "id": "AC480D75BAFBB29B688D9F897E590325"
    },
    "pushName": "Carlos Cliente",
    "message": {
      "conversation": "1"
    },
    "messageType": "conversation",
    "messageTimestamp": 1757201641,
    "sender": "573008862735@s.whatsapp.net",
    "senderPn": "573134054628@s.whatsapp.net"
  }
}
```

Los tres campos que debes extraer siempre son `data.key.remoteJid`, `data.sender`, y `data.senderPn`. La estrategia de matching se construye sobre los tres.

---

### Paso 3 — La función de extracción de número (el núcleo del fix)

Este es el código que necesitas en tu backend FastAPI. Reemplaza cualquier lógica de extracción de JID que tengas actualmente:

```python
import re

def extract_phone_from_jid(jid: str | None) -> str | None:
    """
    Extrae número normalizado de un JID de WhatsApp.
    Retorna None si es @lid o si jid es None.
    """
    if not jid:
        return None
    if jid.endswith("@lid"):
        return None
    # Quita sufijos @s.whatsapp.net, @c.us, etc.
    number = re.sub(r"@.*$", "", jid)
    # Quita caracteres no numéricos
    number = re.sub(r"\D", "", number)
    return number if number else None


def resolve_sender_phone(payload_data: dict) -> str | None:
    """
    Estrategia de resolución de número en orden de confiabilidad:
    1. senderPn  → número real, presente en v2.3.0+ cuando remoteJid es @lid
    2. sender    → número del remitente (más confiable que remoteJid en 1:1)
    3. remoteJid → fallback, puede ser @lid en usuarios Android
    """
    for field in ["senderPn", "sender", "remoteJid"]:
        phone = extract_phone_from_jid(payload_data.get(field))
        if phone:
            return phone
    return None


def resolve_remote_jid_for_reply(payload_data: dict) -> str | None:
    """
    Para enviar la respuesta, Evolution necesita el JID al que responder.
    Usar senderPn o sender (no remoteJid si es @lid).
    """
    for field in ["senderPn", "sender"]:
        jid = payload_data.get(field)
        if jid and not jid.endswith("@lid"):
            return jid
    # Si solo tenemos @lid, no podemos responder de forma confiable
    return None
```

---

### Paso 4 — El webhook handler completo y corregido

```python
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import logging

router = APIRouter()
logger = logging.getLogger("kibo.whatsapp")


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()

    # ── 1. Filtros rápidos ──────────────────────────────────────────
    event = body.get("event", "")
    if event != "messages.upsert":
        return {"ok": True}

    data = body.get("data", {})
    
    # Ignorar mensajes enviados por nosotros mismos
    if data.get("key", {}).get("fromMe"):
        return {"ok": True}

    # Extraer texto del mensaje
    msg = data.get("message", {})
    text = (
        msg.get("conversation")
        or msg.get("extendedTextMessage", {}).get("text")
        or ""
    ).strip()

    if text not in ("1", "2"):
        # Respuesta fuera de contexto — registrar y salir limpio
        logger.info(f"[WH] Mensaje fuera de contexto: '{text[:50]}' ignorado")
        return {"ok": True}

    # ── 2. Resolución de tenant ─────────────────────────────────────
    instance_id = body.get("instance")
    if not instance_id:
        logger.warning("[WH] Webhook sin instance_id")
        return {"ok": True}

    tenant = await db.execute(
        select(Tenant).where(Tenant.whatsapp_instance_id == instance_id)
    )
    tenant = tenant.scalar_one_or_none()

    if not tenant:
        logger.warning(f"[WH] Instancia {instance_id} no asociada a ningún tenant")
        return {"ok": True}

    # ── 3. Idempotencia ─────────────────────────────────────────────
    message_id = data.get("key", {}).get("id")
    if message_id:
        existing = await db.execute(
            select(ProcessedWebhook).where(
                ProcessedWebhook.message_id == message_id
            )
        )
        if existing.scalar_one_or_none():
            logger.info(f"[WH] message_id {message_id} ya procesado, skip")
            return {"ok": True, "processed": False, "reason": "duplicate"}

    # ── 4. Resolución de número con estrategia @lid-safe ───────────
    sender_phone = resolve_sender_phone(data)
    reply_jid = resolve_remote_jid_for_reply(data)

    logger.info(
        f"[WH] Tenant={tenant.id} | instance={instance_id} | "
        f"sender_phone={sender_phone} | reply_jid={reply_jid} | texto='{text}'"
    )

    if not sender_phone:
        logger.warning(
            f"[WH] No se pudo resolver teléfono del remitente. "
            f"remoteJid={data.get('key', {}).get('remoteJid')} "
            f"sender={data.get('sender')} senderPn={data.get('senderPn')}"
        )
        return {"ok": True, "processed": False, "reason": "unresolvable_sender"}

    # ── 5. Matching de cita (estrategia en capas) ───────────────────
    appointment = await find_pending_appointment(
        db=db,
        tenant_id=tenant.id,
        sender_phone=sender_phone,
        remote_jid_raw=data.get("key", {}).get("remoteJid"),
        reply_jid=reply_jid,
    )

    if not appointment:
        logger.info(
            f"[WH] pending_appointment_not_found | tenant={tenant.id} | "
            f"phone={sender_phone}"
        )
        # Guardar igualmente para idempotencia
        await register_processed_webhook(db, message_id, tenant.id, sender_phone, reply_jid)
        return {"ok": True, "processed": False, "reason": "pending_appointment_not_found"}

    # ── 6. Ejecutar acción ─────────────────────────────────────────
    if text == "1":
        await confirm_appointment(db, appointment, tenant, reply_jid)
        logger.info(f"[WH] Cita {appointment.id} CONFIRMADA | tenant={tenant.id}")
    elif text == "2":
        await cancel_appointment(db, appointment, tenant, reply_jid)
        logger.info(f"[WH] Cita {appointment.id} CANCELADA | tenant={tenant.id}")

    await register_processed_webhook(db, message_id, tenant.id, sender_phone, reply_jid)
    return {"ok": True, "processed": True, "appointment_id": str(appointment.id)}
```

---

### Paso 5 — La función de matching en capas (resuelve el problema de raíz)

```python
async def find_pending_appointment(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    sender_phone: str,
    remote_jid_raw: str | None,
    reply_jid: str | None,
) -> Appointment | None:
    """
    Busca cita pendiente dentro del tenant usando 3 estrategias en orden.
    NUNCA cruza datos entre tenants.
    """
    
    # Normalizar teléfono: quitar código de país si hay duplicidad
    # Colombia: 573001234567 → también probar 3001234567
    phone_variants = _build_phone_variants(sender_phone)

    # ── Estrategia 1: match exacto por whatsapp_remote_id ──────────
    # Esto funciona cuando enviaste el reminder con el JID correcto
    # y el cliente responde desde el mismo número/dispositivo
    if reply_jid:
        result = await db.execute(
            select(Appointment)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.status == "pending",
                Appointment.confirmation_status == "pending",
                Appointment.whatsapp_remote_id == reply_jid,
            )
            .order_by(Appointment.appointment_time.asc())
            .limit(1)
        )
        appt = result.scalar_one_or_none()
        if appt:
            logger.info(f"[WH] Match por remote_jid exacto: {reply_jid}")
            return appt

    # ── Estrategia 2: match por teléfono del cliente ────────────────
    # JOIN con clients para buscar por número de teléfono normalizado
    for phone_variant in phone_variants:
        result = await db.execute(
            select(Appointment)
            .join(Client, Appointment.client_id == Client.id)
            .where(
                Appointment.tenant_id == tenant_id,
                Client.tenant_id == tenant_id,  # doble check tenant
                Appointment.status == "pending",
                Appointment.confirmation_status == "pending",
                Client.phone.in_(phone_variants),
            )
            .order_by(Appointment.appointment_time.asc())
            .limit(1)
        )
        appt = result.scalar_one_or_none()
        if appt:
            logger.info(f"[WH] Match por teléfono normalizado: {phone_variant}")
            # Actualizar whatsapp_remote_id con el JID correcto para futuros matches
            if reply_jid:
                appt.whatsapp_remote_id = reply_jid
            return appt

    # ── Estrategia 3: match por conversation_context ────────────────
    # Si tienes un contexto activo (token enviado con el reminder)
    result = await db.execute(
        select(Appointment)
        .join(
            ConversationContext,
            ConversationContext.appointment_id == Appointment.id
        )
        .where(
            ConversationContext.tenant_id == tenant_id,
            ConversationContext.client_phone.in_(phone_variants),
            ConversationContext.expires_at > func.now(),
            Appointment.status == "pending",
        )
        .order_by(Appointment.appointment_time.asc())
        .limit(1)
    )
    appt = result.scalar_one_or_none()
    if appt:
        logger.info(f"[WH] Match por conversation_context: phone={sender_phone}")
        if reply_jid:
            appt.whatsapp_remote_id = reply_jid
        return appt

    return None


def _build_phone_variants(phone: str) -> list[str]:
    """
    Genera variantes del número para cubrir inconsistencias de formato.
    Ej: '573134054628' → ['573134054628', '3134054628']
    """
    variants = [phone]
    # Colombia: si empieza con 57 y tiene 12 dígitos → agregar sin prefijo
    if phone.startswith("57") and len(phone) == 12:
        variants.append(phone[2:])
    # Cualquier país: si tiene más de 10 dígitos → intentar sin primeros 2
    if len(phone) > 10:
        variants.append(phone[-10:])
    return list(set(variants))
```

---

### Paso 6 — Al enviar el reminder, guarda el JID correcto

El problema también ocurre en el otro sentido: cuando envías el reminder, debes guardar en `appointments.whatsapp_remote_id` el JID exacto que usó Evolution para confirmar la entrega, no el número que tú construiste. Así el match de vuelta siempre funciona:

```python
async def send_reminder_and_save_jid(
    db: AsyncSession,
    appointment: Appointment,
    tenant: Tenant,
    client_phone: str,
):
    # Construir JID de destino
    phone_clean = re.sub(r"\D", "", client_phone)
    if not phone_clean.startswith("57"):
        phone_clean = f"57{phone_clean}"
    destination_jid = f"{phone_clean}@s.whatsapp.net"

    # Enviar via Evolution API
    response = await send_whatsapp_message(
        instance=tenant.whatsapp_instance_id,
        apikey=tenant.whatsapp_apikey,
        number=destination_jid,
        text=build_reminder_text(appointment, tenant),
    )

    # Guardar el JID confirmado por Evolution en la respuesta
    # Evolution retorna el key.remoteJid real usado para entregar
    confirmed_jid = response.get("key", {}).get("remoteJid") or destination_jid
    appointment.whatsapp_remote_id = confirmed_jid

    await db.commit()
    logger.info(
        f"[WH] Respuesta enviada desde Instancia: {tenant.whatsapp_instance_id} "
        f"hacia Cliente: {confirmed_jid}"
    )
```

---

### Paso 7 — Migration de Alembic que necesitas

Una sola columna adicional en `clients` que guarda el `@lid` conocido del cliente, para casos donde el número y el LID ya se conocen:

```python
# alembic/versions/xxxx_add_whatsapp_lid_to_clients.py

def upgrade():
    op.add_column(
        "clients",
        sa.Column("whatsapp_lid", sa.String(), nullable=True),
        schema="public"
    )
    op.create_index(
        "ix_clients_tenant_whatsapp_lid",
        "clients",
        ["tenant_id", "whatsapp_lid"],
        schema="public"
    )
```

Y cuando veas un `@lid` en el webhook que lograste resolver (via `senderPn`), guarda esa asociación:

```python
# Dentro del webhook handler, después de confirmar match:
if remote_jid_raw and remote_jid_raw.endswith("@lid"):
    client = await db.get(Client, appointment.client_id)
    if client and not client.whatsapp_lid:
        client.whatsapp_lid = remote_jid_raw
        # Próxima vez: match directo por LID sin necesitar senderPn
```

---

## Resumen de los 3 problemas y sus fixes

| Problema | Causa | Fix |
|---|---|---|
| `pending_appointment_not_found` | `remoteJid` llega como `@lid` en Android | Leer `senderPn` primero, luego `sender` como fallback |
| Match falla aunque el número es correcto | Formato inconsistente (con/sin código país) | `_build_phone_variants()` genera todas las variantes |
| Sesión guardada con JID incorrecto | Se guarda el JID construido, no el confirmado | Guardar `response.key.remoteJid` después del envío |

El orden de prioridad en `resolve_sender_phone` — `senderPn` → `sender` → `remoteJid` — cubre los tres escenarios posibles que confirman los issues de GitHub abiertos: Android con `@lid`, iPhone con JID correcto, y versiones anteriores de Evolution sin `senderPn`.
