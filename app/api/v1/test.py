"""
Test endpoints for manual validation of WhatsApp RemoteJID flow
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.appointments import Appointment, AppointmentStatus
from app.repositories.appointments import AppointmentRepository
from app.repositories.clients import ClientRepository
from app.repositories.tenant import TenantRepository
from app.services.whatsapp.evolution_client import EvolutionClient, EvolutionClientError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test", tags=["test"])


@router.get("/trigger-reminder/{appointment_id}")
async def trigger_manual_reminder(
    appointment_id: Annotated[uuid.UUID, Path(description="ID of the appointment to send reminder for")],
    db: Annotated[Session, Depends(get_db)],
    test_key: str = "test123",  # Simple test key for bypassing auth
):
    """
    Manual trigger for testing WhatsApp reminder and RemoteJID capture.

    This endpoint:
    1. Finds the appointment by ID
    2. Sends a test message via Evolution API
    3. Captures the remoteJid from the response
    4. Updates the appointment with the captured remoteJid
    5. Returns detailed information about the process

    Use ?test_key=test123 for testing without authentication
    """

    # Simple authentication bypass for testing
    if test_key != "test123":
        raise HTTPException(status_code=401, detail="Invalid test key")

    logger.info(f"[TEST_REMINDER] Starting manual reminder test for appointment {appointment_id}")

    try:
        # Initialize repositories
        tenant_repo = TenantRepository(db)
        appointment_repo = AppointmentRepository(db)
        client_repo = ClientRepository(db)
        evolution_client = EvolutionClient()

        # 1. Búsqueda: Find the appointment (search across all tenants for testing)
        appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()

        if not appointment:
            raise HTTPException(status_code=404, detail=f"Appointment {appointment_id} not found")

        if appointment.status != AppointmentStatus.PENDING:
            logger.warning(
                f"[TEST_REMINDER] Appointment {appointment_id} is not PENDING (status: {appointment.status})"
            )

        # 2. Carga de Datos: Get tenant and client information
        tenant = tenant_repo.get_by_id(appointment.tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        if not tenant.whatsapp_instance_id:
            raise HTTPException(status_code=400, detail="Tenant does not have WhatsApp instance configured")

        client = client_repo.get_by_id(appointment.tenant_id, appointment.client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        if not client.phone:
            raise HTTPException(status_code=400, detail="Client does not have phone number")

        # 3. Llamada a Evolution API: Send test message
        test_message = (
            f"🧪 PRUEBA KIBO: Hola {client.name}, esto es un mensaje de prueba del sistema. "
            f"Su cita para {appointment.appointment_date} {appointment.time_start} está siendo probada. "
            f"Responda '1' para confirmar esta prueba."
        )

        logger.info(
            f"[TEST_REMINDER] Sending test message to {client.phone} via instance {tenant.whatsapp_instance_id}"
        )

        # Normalize phone to 57+number format if needed
        phone = client.phone
        if not phone.startswith("57"):
            phone = f"57{phone.lstrip('0+')}"

        try:
            evolution_response = await evolution_client.send_text(
                instance_name=tenant.whatsapp_instance_id,
                phone=phone,
                text=test_message,
            )

            # Log the complete response for debugging
            logger.info(
                f"[TEST_REMINDER] Evolution API Complete Response: {evolution_response}",
                extra={
                    "appointment_id": str(appointment_id),
                    "tenant_id": str(appointment.tenant_id),
                    "response": evolution_response,
                },
            )

        except EvolutionClientError as e:
            logger.error(f"[TEST_REMINDER] Evolution API Error: {e}")
            raise HTTPException(status_code=500, detail=f"WhatsApp API Error: {str(e)}")

        # 4. Captura Crítica del JID/LID: Extract remoteJid from response
        remote_jid = _extract_remote_jid_from_response(evolution_response)

        if not remote_jid:
            logger.warning(
                "[TEST_REMINDER] Could not extract remoteJid from Evolution response",
                extra={"response": evolution_response},
            )
            return {
                "status": "partial_success",
                "message_sent": True,
                "remote_jid_captured": False,
                "evolution_response": evolution_response,
                "error": "Could not extract remoteJid from Evolution API response",
            }

        # 5. Persistencia: Update appointment with captured remoteJid
        old_remote_id = appointment.whatsapp_remote_id
        old_notification_type = appointment.last_notification_type

        try:
            appointment_repo.update(
                tenant_id=appointment.tenant_id,
                appointment_id=appointment_id,
                whatsapp_remote_id=remote_jid,
                last_notification_type="manual_test",
            )

            logger.info(
                f"[TEST_REMINDER] Successfully updated appointment {appointment_id}",
                extra={
                    "old_remote_id": old_remote_id,
                    "new_remote_id": remote_jid,
                    "old_notification_type": old_notification_type,
                    "new_notification_type": "manual_test",
                },
            )

        except Exception as e:
            logger.error(f"[TEST_REMINDER] Database update failed: {e}")
            raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")

        # Return success response
        return {
            "status": "success",
            "message_sent": True,
            "sent_to_phone": phone,
            "sent_to_jid": remote_jid,
            "db_updated": True,
            "appointment_details": {
                "id": str(appointment_id),
                "client_name": client.name,
                "client_phone": client.phone,
                "appointment_date": appointment.appointment_date.isoformat(),
                "appointment_time": str(appointment.time_start),
                "old_remote_id": old_remote_id,
                "new_remote_id": remote_jid,
                "status": appointment.status.value,
            },
            "evolution_response": evolution_response,
            "test_message": test_message,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TEST_REMINDER] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


def _extract_remote_jid_from_response(response: dict) -> str | None:
    """
    Extract remoteJid from Evolution API response.

    Handles multiple response formats:
    - response['key']['remoteJid']  <- Primary format for Evolution API v2.x
    - response['data']['key']['remoteJid']
    - response['remoteJid']
    - response['message']['key']['remoteJid']
    """
    if not isinstance(response, dict):
        return None

    # Try primary path: key.remoteJid (Evolution API v2.x format)
    key = response.get("key")
    if isinstance(key, dict):
        remote_jid = key.get("remoteJid")
        if isinstance(remote_jid, str) and remote_jid.strip():
            return remote_jid.strip()

    # Try secondary path: data.key.remoteJid
    data = response.get("data")
    if isinstance(data, dict):
        key = data.get("key")
        if isinstance(key, dict):
            remote_jid = key.get("remoteJid")
            if isinstance(remote_jid, str) and remote_jid.strip():
                return remote_jid.strip()

    # Try direct path: remoteJid
    remote_jid = response.get("remoteJid")
    if isinstance(remote_jid, str) and remote_jid.strip():
        return remote_jid.strip()

    # Try alternative path: message.key.remoteJid
    message = response.get("message")
    if isinstance(message, dict):
        key = message.get("key")
        if isinstance(key, dict):
            remote_jid = key.get("remoteJid")
            if isinstance(remote_jid, str) and remote_jid.strip():
                return remote_jid.strip()

    return None


@router.get("/appointment-info/{appointment_id}")
async def get_appointment_test_info(
    appointment_id: Annotated[uuid.UUID, Path(description="ID of the appointment to inspect")],
    db: Annotated[Session, Depends(get_db)],
    test_key: str = "test123",  # Simple test key for bypassing auth
):
    """
    Get detailed information about an appointment for testing purposes.
    Shows current remoteJid, notification status, and related data.

    Use ?test_key=test123 for testing without authentication
    """

    # Simple authentication bypass for testing
    if test_key != "test123":
        raise HTTPException(status_code=401, detail="Invalid test key")

    client_repo = ClientRepository(db)
    tenant_repo = TenantRepository(db)

    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()

    if not appointment:
        raise HTTPException(status_code=404, detail=f"Appointment {appointment_id} not found")

    client = client_repo.get_by_id(appointment.tenant_id, appointment.client_id)
    tenant = tenant_repo.get_by_id(appointment.tenant_id)

    return {
        "appointment": {
            "id": str(appointment.id),
            "status": appointment.status.value,
            "date": appointment.appointment_date.isoformat(),
            "time_start": str(appointment.time_start),
            "time_end": str(appointment.time_end),
            "whatsapp_remote_id": appointment.whatsapp_remote_id,
            "last_notification_type": appointment.last_notification_type,
            "reminder_24h_sent": appointment.reminder_24h_sent,
            "reminder_2h_sent": appointment.reminder_2h_sent,
            "notes": appointment.notes,
        },
        "client": {
            "id": str(client.id) if client else None,
            "name": client.name if client else None,
            "phone": client.phone if client else None,
            "whatsapp_opt_out": client.whatsapp_opt_out if client else None,
        },
        "tenant": {
            "id": str(tenant.id) if tenant else None,
            "name": tenant.name if tenant else None,
            "whatsapp_instance_id": tenant.whatsapp_instance_id if tenant else None,
            "timezone": tenant.timezone_identifier if tenant else None,
        },
    }
