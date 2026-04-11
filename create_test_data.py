#!/usr/bin/env python3
"""
Script para crear datos de prueba para Juan Pablo Zapata
"""

import sys
sys.path.append('.')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
from app.models.tenant import Tenant, PlanTier, SubscriptionStatus
from app.models.clients import Client
from app.models.services import Service
from app.models.appointments import Appointment, AppointmentStatus
from app.models.auth import User
from datetime import datetime, timedelta, time, timezone
import uuid

def create_test_data():
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        print("🏗️  CREANDO DATOS DE PRUEBA")
        print("=" * 50)
        
        # 1. Crear o encontrar tenant
        tenant = db.query(Tenant).filter(Tenant.name.ilike('%kibo%test%')).first()
        if not tenant:
            now = datetime.now(timezone.utc)
            tenant = Tenant(
                name="KIBO Test Clinic",
                phone="3001234567",
                plan_tier=PlanTier.PRO,
                subscription_status=SubscriptionStatus.ACTIVE,
                subscription_valid_until=now + timedelta(days=30),
                trial_ends_at=now + timedelta(days=30),
                timezone_identifier="America/Bogota",
                whatsapp_instance_id="kibo-test-instance",
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            print(f"✅ Tenant creado: {tenant.name} (ID: {tenant.id})")
        else:
            print(f"✅ Tenant encontrado: {tenant.name} (ID: {tenant.id})")
        
        # 2. Crear usuario admin para el tenant
        admin_user = db.query(User).filter(User.tenant_id == tenant.id).first()
        if not admin_user:
            admin_user = User(
                email="admin@kibotest.com",
                name="Admin Test",
                tenant_id=tenant.id,
                role="owner",
                is_active=True,
                password_hash="$2b$12$dummy.hash.for.testing"
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print(f"✅ Usuario admin creado: {admin_user.name}")
        else:
            print(f"✅ Usuario admin encontrado: {admin_user.name}")
        
        # 3. Crear o encontrar cliente Juan Pablo Zapata
        client = db.query(Client).filter(
            Client.tenant_id == tenant.id,
            Client.name.ilike('%juan%pablo%zapata%')
        ).first()
        
        if not client:
            client = Client(
                tenant_id=tenant.id,
                name="Juan Pablo Zapata",
                phone="3001234567",
                whatsapp_opt_out=False,
            )
            db.add(client)
            db.commit()
            db.refresh(client)
            print(f"✅ Cliente creado: {client.name} (ID: {client.id})")
        else:
            print(f"✅ Cliente encontrado: {client.name} (ID: {client.id})")
        
        # 4. Crear o encontrar servicio
        service = db.query(Service).filter(Service.tenant_id == tenant.id).first()
        if not service:
            service = Service(
                tenant_id=tenant.id,
                name="Limpieza Dental",
                duration=60,
                price=150000,
                is_active=True,
            )
            db.add(service)
            db.commit()
            db.refresh(service)
            print(f"✅ Servicio creado: {service.name} (ID: {service.id})")
        else:
            print(f"✅ Servicio encontrado: {service.name} (ID: {service.id})")
        
        # 5. Verificar si ya existe cita para mañana a las 12:30
        tomorrow = (datetime.now().date() + timedelta(days=1))
        target_time = time(12, 30)
        
        existing_appointment = db.query(Appointment).filter(
            Appointment.tenant_id == tenant.id,
            Appointment.client_id == client.id,
            Appointment.appointment_date == tomorrow,
            Appointment.time_start == target_time
        ).first()
        
        if existing_appointment:
            print(f"✅ Cita ya existe: {existing_appointment.id}")
            print(f"   Fecha: {existing_appointment.appointment_date}")
            print(f"   Hora: {existing_appointment.time_start}")
            print(f"   Estado: {existing_appointment.status}")
            print(f"   WhatsApp Remote ID: {existing_appointment.whatsapp_remote_id}")
            appointment = existing_appointment
        else:
            # Crear nueva cita
            appointment = Appointment(
                tenant_id=tenant.id,
                client_id=client.id,
                service_id=service.id,
                user_id=admin_user.id,
                appointment_date=tomorrow,
                time_start=target_time,
                time_end=time(13, 30),  # 1 hora después
                status=AppointmentStatus.PENDING,
                notes="Cita de prueba para testing RemoteJID",
                whatsapp_remote_id=None,  # Se capturará durante el recordatorio
                last_notification_type=None,
                reminder_24h_sent=False,
                reminder_2h_sent=False,
            )
            db.add(appointment)
            db.commit()
            db.refresh(appointment)
            print(f"✅ Cita creada: {appointment.id}")
            print(f"   Cliente: {client.name}")
            print(f"   Fecha: {appointment.appointment_date}")
            print(f"   Hora: {appointment.time_start}")
            print(f"   Servicio: {service.name}")
        
        print(f"\n📋 RESUMEN DE DATOS CREADOS:")
        print(f"   🏢 Tenant: {tenant.name}")
        print(f"      Instance ID: {tenant.whatsapp_instance_id}")
        print(f"   👤 Cliente: {client.name}")
        print(f"      Teléfono: {client.phone}")
        print(f"   📅 Cita: {appointment.appointment_date} {appointment.time_start}")
        print(f"      ID: {appointment.id}")
        print(f"      Estado: {appointment.status}")
        print(f"      Remote ID: {appointment.whatsapp_remote_id}")
        
        return {
            'tenant': tenant,
            'client': client, 
            'service': service,
            'appointment': appointment,
            'admin_user': admin_user
        }
        
    finally:
        db.close()

if __name__ == "__main__":
    data = create_test_data()
    
    print(f"\n🎯 DATOS LISTOS PARA PRUEBA")
    print(f"   Para probar el recordatorio 24h, ejecuta:")
    print(f"   python -c \"\"\"")
    print(f"import asyncio")
    print(f"from app.services.scheduler.reminder_scheduler import ReminderScheduler")
    print(f"from app.db.session import get_db")
    print(f"")
    print(f"db = next(get_db())")
    print(f"scheduler = ReminderScheduler(lambda: db)")
    print(f"asyncio.run(scheduler._send_24h_reminders(db))") 
    print(f"\"\"\"")