from datetime import datetime, time, timedelta, timezone
import uuid

from sqlalchemy.orm import Session

from app.models.appointments import Appointment, AppointmentStatus
from app.models.clients import Client
from app.models.services import Service
from app.models.tenant import PlanTier, SubscriptionStatus, Tenant
from app.services.scheduler.reminder_scheduler import ReminderScheduler
from app.services.whatsapp.evolution_client import EvolutionClient


def _create_tenant(db: Session, *, instance_name: str = "instance-test") -> Tenant:
    now = datetime.now(timezone.utc)
    tenant = Tenant(
        name="Tenant WhatsApp",
        phone="3001234567",
        plan_tier=PlanTier.PRO,
        subscription_status=SubscriptionStatus.ACTIVE,
        subscription_valid_until=now + timedelta(days=30),
        trial_ends_at=now + timedelta(days=30),
        timezone_identifier="America/Bogota",
        whatsapp_instance_id=instance_name,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _create_client(db: Session, tenant_id: uuid.UUID, *, name: str, phone: str) -> Client:
    client = Client(tenant_id=tenant_id, name=name, phone=phone)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def _create_service(db: Session, tenant_id: uuid.UUID, *, name: str = "Corte", duration: int = 30) -> Service:
    service = Service(tenant_id=tenant_id, name=name, duration=duration, price=10000)
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


def _create_appointment(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    client_id: uuid.UUID,
    service_id: uuid.UUID,
    appointment_date,
    time_start: time,
    status: AppointmentStatus = AppointmentStatus.PENDING,
) -> Appointment:
    entity = Appointment(
        tenant_id=tenant_id,
        client_id=client_id,
        user_id=uuid.uuid4(),
        service_id=service_id,
        appointment_date=appointment_date,
        time_start=time_start,
        time_end=(datetime.combine(appointment_date, time_start) + timedelta(minutes=30)).time(),
        status=status,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def test_webhook_uses_sender_when_remotejid_is_lid(test_client, db: Session, monkeypatch):
    sent_messages: list[dict] = []

    async def _fake_send_text(self, *, instance_name: str, phone: str, text: str):
        sent_messages.append({"instance_name": instance_name, "phone": phone, "text": text})
        return {"key": "msg-1"}

    monkeypatch.setattr(EvolutionClient, "send_text", _fake_send_text)

    tenant = _create_tenant(db, instance_name="agenda-dev-v2413")
    client = _create_client(db, tenant.id, name="Carlangas", phone="3105977000")
    service = _create_service(db, tenant.id)
    appointment = _create_appointment(
        db,
        tenant_id=tenant.id,
        client_id=client.id,
        service_id=service.id,
        appointment_date=(datetime.now().date() + timedelta(days=1)),
        time_start=time(9, 30),
        status=AppointmentStatus.PENDING,
    )

    payload = {
        "event": "messages.upsert",
        "instance": "agenda-dev-v2413",
        "sender": "573105977000@s.whatsapp.net",
        "data": {
            "key": {
                "remoteJid": "265218693328947@lid",
                "fromMe": False,
                "id": "MSG-ABC-123",
            },
            "message": {"conversation": "1"},
        },
    }

    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] is True
    assert body["action"] == "appointment_confirmed"
    assert body["appointment_id"] == str(appointment.id)

    db.refresh(appointment)
    assert appointment.status == AppointmentStatus.CONFIRMED
    assert len(sent_messages) == 1


def test_webhook_matches_by_remote_jid_when_phone_missing(test_client, db: Session, monkeypatch):
    async def _fake_send_text(self, *, instance_name: str, phone: str, text: str):
        return {"data": {"key": {"remoteJid": "remote-confirm-1"}}}

    monkeypatch.setattr(EvolutionClient, "send_text", _fake_send_text)

    tenant = _create_tenant(db, instance_name="instance-remote-match")
    client = _create_client(db, tenant.id, name="Valeria", phone="3158892300")
    service = _create_service(db, tenant.id)
    appointment = _create_appointment(
        db,
        tenant_id=tenant.id,
        client_id=client.id,
        service_id=service.id,
        appointment_date=(datetime.now().date() + timedelta(days=1)),
        time_start=time(11, 30),
        status=AppointmentStatus.PENDING,
    )

    remote_jid = "918273645564738@lid"
    appointment.whatsapp_remote_id = remote_jid
    db.commit()

    payload = {
        "event": "messages.upsert",
        "instance": tenant.whatsapp_instance_id,
        "remoteJid": remote_jid,
        "data": {
            "key": {
                "remoteJid": remote_jid,
                "participant": remote_jid,
                "fromMe": False,
                "id": "MSG-REMOTE-1",
            },
            "message": {"conversation": "1"},
        },
    }

    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] is True
    assert body["status"] == "success"
    assert body["action"] == "appointment_confirmed"
    assert body["matched_by"] == "remote_id"
    assert body["appointment_id"] == str(appointment.id)

    db.refresh(appointment)
    assert appointment.status == AppointmentStatus.CONFIRMED
    assert appointment.whatsapp_remote_id == remote_jid


def test_webhook_is_idempotent_by_message_id(test_client, db: Session, monkeypatch):
    async def _fake_send_text(self, *, instance_name: str, phone: str, text: str):
        return {"key": "msg-2"}

    monkeypatch.setattr(EvolutionClient, "send_text", _fake_send_text)

    tenant = _create_tenant(db, instance_name="instance-dedupe")
    client = _create_client(db, tenant.id, name="Laura", phone="3162970154")
    service = _create_service(db, tenant.id)
    _create_appointment(
        db,
        tenant_id=tenant.id,
        client_id=client.id,
        service_id=service.id,
        appointment_date=(datetime.now().date() + timedelta(days=1)),
        time_start=time(10, 0),
    )

    payload = {
        "event": "messages.upsert",
        "instance": "instance-dedupe",
        "sender": "573162970154@s.whatsapp.net",
        "data": {
            "key": {
                "remoteJid": "265218693328947@lid",
                "fromMe": False,
                "id": "MSG-DEDUPE-1",
            },
            "message": {"conversation": "1"},
        },
    }

    first = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert first.status_code == 200
    assert first.json()["processed"] is True

    second = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert second.status_code == 200
    assert second.json()["processed"] is False
    assert second.json()["reason"] == "duplicate_message"


def test_webhook_sends_welcome_on_new_conversation_without_pending_24h(test_client, db: Session, monkeypatch):
    sent_messages: list[dict] = []

    async def _fake_send_text(self, *, instance_name: str, phone: str, text: str):
        sent_messages.append({"instance_name": instance_name, "phone": phone, "text": text})
        return {"key": "msg-3"}

    monkeypatch.setattr(EvolutionClient, "send_text", _fake_send_text)

    _create_tenant(db, instance_name="instance-welcome")

    payload = {
        "event": "messages.upsert",
        "instance": "instance-welcome",
        "sender": "573001112233@s.whatsapp.net",
        "data": {
            "key": {
                "remoteJid": "265218693328947@lid",
                "fromMe": False,
                "id": "MSG-WELCOME-1",
            },
            "message": {"conversation": "hola"},
        },
    }

    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] is True
    assert body["action"] == "welcome_sent"
    assert len(sent_messages) == 1


def test_scheduler_updates_last_notification_type_for_24h_and_2h(db: Session, monkeypatch):
    calls: list[str] = []

    async def _fake_send_text(self, *, instance_name: str, phone: str, text: str):
        calls.append(text)
        return {"key": f"msg-{len(calls)}"}

    monkeypatch.setattr(EvolutionClient, "send_text", _fake_send_text)

    fixed_now = datetime(2026, 3, 26, 10, 0, tzinfo=timezone(timedelta(hours=-5)))

    from app.services.scheduler import reminder_scheduler as reminder_module

    monkeypatch.setattr(reminder_module, "now_for_timezone", lambda tz: fixed_now)

    tenant = _create_tenant(db, instance_name="instance-scheduler")
    client = _create_client(db, tenant.id, name="Mauricio", phone="3008862735")
    service = _create_service(db, tenant.id)

    appt_24h = _create_appointment(
        db,
        tenant_id=tenant.id,
        client_id=client.id,
        service_id=service.id,
        appointment_date=(fixed_now.date() + timedelta(days=1)),
        time_start=time(14, 0),
    )

    # 16:00 UTC -> 11:00 (-05), so this is within the next 2 hours from 10:00 local
    appt_2h = _create_appointment(
        db,
        tenant_id=tenant.id,
        client_id=client.id,
        service_id=service.id,
        appointment_date=fixed_now.date(),
        time_start=time(16, 0),
    )

    scheduler = ReminderScheduler(lambda: db)

    import asyncio

    asyncio.run(scheduler._send_24h_reminders(db))
    asyncio.run(scheduler._send_2h_reminders(db))

    db.refresh(appt_24h)
    db.refresh(appt_2h)
    assert appt_24h.last_notification_type == "reminder_24h"
    assert appt_24h.reminder_24h_sent is True
    assert appt_2h.last_notification_type == "reminder_2h"
    assert appt_2h.reminder_2h_sent is True
    assert len(calls) >= 2


def test_webhook_ignores_group_messages(test_client):
    """Test that webhook ignores messages from WhatsApp groups (remoteJid contains @g.us)"""
    payload = {
        "event": "messages.upsert",
        "instance": "test-instance",
        "data": {
            "key": {
                "remoteJid": "120363123456789@g.us",  # Group message
                "fromMe": False,
                "id": "MSG-GROUP-123",
            },
            "message": {"conversation": "1"},
        },
    }

    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] is False
    assert body["reason"] == "group_message"
    assert body["event"] == "messages.upsert"


def test_webhook_ignores_own_messages(test_client):
    """Test that webhook ignores messages sent by me (fromMe=true)"""
    payload = {
        "event": "messages.upsert",
        "instance": "test-instance",
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": True,  # Message sent by me
                "id": "MSG-OUTGOING-123",
            },
            "message": {"conversation": "1"},
        },
    }

    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] is False
    assert body["reason"] == "sent_by_me"
    assert body["event"] == "messages.upsert"


def test_webhook_ignores_audio_messages(test_client):
    """Test that webhook ignores audio messages"""
    payload = {
        "event": "messages.upsert",
        "instance": "test-instance",
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG-AUDIO-123",
            },
            "message": {
                "audioMessage": {
                    "url": "https://example.com/audio.mp3",
                    "mimetype": "audio/mp4",
                }
            },
        },
    }

    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] is False
    assert body["reason"] == "unsupported_message_type"
    assert body["event"] == "messages.upsert"


def test_webhook_ignores_image_messages(test_client):
    """Test that webhook ignores image messages"""
    payload = {
        "event": "messages.upsert",
        "instance": "test-instance",
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG-IMAGE-123",
            },
            "message": {
                "imageMessage": {
                    "url": "https://example.com/image.jpg",
                    "mimetype": "image/jpeg",
                }
            },
        },
    }

    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] is False
    assert body["reason"] == "unsupported_message_type"
    assert body["event"] == "messages.upsert"


def test_webhook_ignores_video_messages(test_client):
    """Test that webhook ignores video messages"""
    payload = {
        "event": "messages.upsert",
        "instance": "test-instance",
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG-VIDEO-123",
            },
            "message": {
                "videoMessage": {
                    "url": "https://example.com/video.mp4",
                    "mimetype": "video/mp4",
                }
            },
        },
    }

    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] is False
    assert body["reason"] == "unsupported_message_type"
    assert body["event"] == "messages.upsert"


def test_webhook_processes_conversation_messages(test_client):
    """Test that webhook processes conversation messages (should pass filters)"""
    payload = {
        "event": "messages.upsert",
        "instance": "test-instance",
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG-CONVERSATION-123",
            },
            "message": {"conversation": "1"},  # Valid conversation message
        },
    }

    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    # Should pass filters but may fail at business logic level (tenant not found, etc)
    # The important thing is it doesn't get filtered out by the new filters
    assert body["reason"] not in ["group_message", "sent_by_me", "unsupported_message_type"]


def test_webhook_processes_extended_text_messages(test_client):
    """Test that webhook processes extendedTextMessage (should pass filters)"""
    payload = {
        "event": "messages.upsert",
        "instance": "test-instance",
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG-EXTENDED-123",
            },
            "message": {
                "extendedTextMessage": {
                    "text": "1",
                    "contextInfo": {}
                }
            },
        },
    }

    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    # Should pass filters but may fail at business logic level
    assert body["reason"] not in ["group_message", "sent_by_me", "unsupported_message_type"]


def test_scheduler_captures_remote_jid_on_24h_reminder(test_client, db: Session, monkeypatch):
    """Test that scheduler captures and saves remoteJid from Evolution API response during 24h reminder"""
    
    # Mock Evolution API to return a response with remoteJid
    async def mock_send_text(self, *, instance_name: str, phone: str, text: str):
        return {
            "data": {
                "key": {
                    "remoteJid": "573001234567@s.whatsapp.net",
                    "id": "MSG-REMINDER-123"
                }
            }
        }
    
    monkeypatch.setattr(EvolutionClient, "send_text", mock_send_text)
    
    # Create test data
    tenant = _create_tenant(db, instance_name="test-jid-capture")
    client = _create_client(db, tenant.id, name="Juan", phone="3001234567")
    service = _create_service(db, tenant.id)
    
    # Create appointment for tomorrow (24h reminder window)
    tomorrow = (datetime.now().date() + timedelta(days=1))
    appointment = _create_appointment(
        db,
        tenant_id=tenant.id,
        client_id=client.id,
        service_id=service.id,
        appointment_date=tomorrow,
        time_start=time(14, 0),
        status=AppointmentStatus.PENDING,
    )
    
    # Verify remoteJid is initially None
    assert appointment.whatsapp_remote_id is None
    
    # Run 24h reminder scheduler
    from app.services.scheduler.reminder_scheduler import ReminderScheduler
    scheduler = ReminderScheduler(lambda: db)
    
    import asyncio
    asyncio.run(scheduler._send_24h_reminders(db))
    
    # Refresh appointment and verify remoteJid was captured
    db.refresh(appointment)
    assert appointment.whatsapp_remote_id == "573001234567@s.whatsapp.net"
    assert appointment.reminder_24h_sent is True
    assert appointment.last_notification_type == "reminder_24h"


def test_scheduler_captures_remote_jid_on_2h_reminder(test_client, db: Session, monkeypatch):
    """Test that scheduler captures and saves remoteJid from Evolution API response during 2h reminder"""
    
    # Mock Evolution API with different remoteJid format (@lid)
    async def mock_send_text(self, *, instance_name: str, phone: str, text: str):
        return {
            "data": {
                "key": {
                    "remoteJid": "265218693328947@lid",
                    "id": "MSG-2H-REMINDER-456"
                }
            }
        }
    
    monkeypatch.setattr(EvolutionClient, "send_text", mock_send_text)
    
    # Create test data
    tenant = _create_tenant(db, instance_name="test-2h-jid-capture")
    client = _create_client(db, tenant.id, name="Maria", phone="3109876543")
    service = _create_service(db, tenant.id)
    
    # Create appointment for today in 1.5 hours (2h reminder window)
    now = datetime.now()
    appointment_time = (now + timedelta(hours=1, minutes=30)).time()
    
    appointment = _create_appointment(
        db,
        tenant_id=tenant.id,
        client_id=client.id,
        service_id=service.id,
        appointment_date=now.date(),
        time_start=appointment_time,
        status=AppointmentStatus.PENDING,
    )
    
    # Run 2h reminder scheduler
    from app.services.scheduler.reminder_scheduler import ReminderScheduler
    scheduler = ReminderScheduler(lambda: db)
    
    import asyncio
    asyncio.run(scheduler._send_2h_reminders(db))
    
    # Refresh and verify remoteJid was captured
    db.refresh(appointment)
    assert appointment.whatsapp_remote_id == "265218693328947@lid"
    assert appointment.reminder_2h_sent is True
    assert appointment.last_notification_type == "reminder_2h"


def test_webhook_matches_appointment_by_remote_jid_priority(test_client, db: Session, monkeypatch):
    """Test that webhook prioritizes remote_jid matching over phone number matching"""
    
    async def mock_send_text(self, *, instance_name: str, phone: str, text: str):
        return {"data": {"key": {"remoteJid": "response-confirm-jid"}}}
    
    monkeypatch.setattr(EvolutionClient, "send_text", mock_send_text)
    
    # Create tenant and client
    tenant = _create_tenant(db, instance_name="test-priority-matching")
    client = _create_client(db, tenant.id, name="Carlos", phone="3158765432")
    service = _create_service(db, tenant.id)
    
    # Create two appointments for the same client
    tomorrow = (datetime.now().date() + timedelta(days=1))
    
    # Appointment 1: has remoteJid (should be matched)
    appointment_with_jid = _create_appointment(
        db,
        tenant_id=tenant.id,
        client_id=client.id,
        service_id=service.id,
        appointment_date=tomorrow,
        time_start=time(10, 0),
        status=AppointmentStatus.PENDING,
    )
    appointment_with_jid.whatsapp_remote_id = "265218693328947@lid"
    db.commit()
    
    # Appointment 2: same client but no remoteJid (should NOT be matched)
    appointment_without_jid = _create_appointment(
        db,
        tenant_id=tenant.id,
        client_id=client.id,
        service_id=service.id,
        appointment_date=tomorrow,
        time_start=time(11, 0),
        status=AppointmentStatus.PENDING,
    )
    
    # Send confirmation webhook with the remoteJid
    payload = {
        "event": "messages.upsert",
        "instance": tenant.whatsapp_instance_id,
        "data": {
            "key": {
                "remoteJid": "265218693328947@lid",  # Matches first appointment
                "fromMe": False,
                "id": "MSG-CONFIRM-JID-123",
            },
            "message": {"conversation": "1"},  # Confirmation
        },
    }
    
    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    
    # Should match the appointment with remoteJid
    assert body["processed"] is True
    assert body["action"] == "appointment_confirmed"
    assert body["appointment_id"] == str(appointment_with_jid.id)
    assert body["matched_by"] == "remote_id"
    
    # Verify correct appointment was updated
    db.refresh(appointment_with_jid)
    db.refresh(appointment_without_jid)
    
    assert appointment_with_jid.status == AppointmentStatus.CONFIRMED
    assert appointment_without_jid.status == AppointmentStatus.PENDING  # Unchanged


def test_webhook_handles_no_pending_appointments_gracefully(test_client):
    """Test that webhook handles commands (1,2,3) when no appointments exist without errors"""
    
    payload = {
        "event": "messages.upsert",
        "instance": "non-existent-instance",
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG-NO-APPT-123",
            },
            "message": {"conversation": "1"},  # Confirmation command
        },
    }
    
    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    
    # Should handle gracefully, not return internal error
    assert body["processed"] is False
    assert body["reason"] in ["tenant_not_found", "no_pending_appointments"]


def test_webhook_ignores_non_command_messages_gracefully(test_client):
    """Test that webhook ignores non-command messages without errors"""
    
    payload = {
        "event": "messages.upsert", 
        "instance": "test-instance",
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG-RANDOM-456",
            },
            "message": {"conversation": "Hola, como estas?"},  # Random message
        },
    }
    
    response = test_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    body = response.json()
    
    # Should ignore gracefully
    assert body["processed"] is False
    assert body["reason"] == "event_ignored"
