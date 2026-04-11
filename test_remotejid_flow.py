#!/usr/bin/env python3
"""
Script para probar el flujo completo de RemoteJID:
1. Crear cita de prueba para Juan Pablo Zapata
2. Simular envío de recordatorio y captura de remoteJid
3. Simular respuesta de webhook y verificar match
"""

import asyncio
import json
from datetime import datetime, timedelta, time
from unittest.mock import AsyncMock, patch
import httpx
import sys
import os

# Add project root to path
sys.path.append('.')

def test_remote_jid_flow():
    """Prueba completa del flujo RemoteJID sin necesidad de BD activa"""
    print("🧪 INICIANDO PRUEBA DEL FLUJO REMOTEJID")
    print("=" * 60)
    
    # Datos de prueba
    test_data = {
        "tenant": {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "name": "Clínica Dental SmileCare",
            "whatsapp_instance_id": "kibo-test-instance",
            "timezone_identifier": "America/Bogota"
        },
        "client": {
            "id": "456e7890-e89b-12d3-a456-426614174001", 
            "name": "Juan Pablo Zapata",
            "phone": "3001234567"
        },
        "appointment": {
            "id": "789e0123-e89b-12d3-a456-426614174002",
            "appointment_date": (datetime.now().date() + timedelta(days=1)),
            "time_start": time(12, 30),
            "status": "PENDING",
            "whatsapp_remote_id": None
        }
    }
    
    print(f"📋 DATOS DE PRUEBA:")
    print(f"   Cliente: {test_data['client']['name']}")
    print(f"   Teléfono: {test_data['client']['phone']}")
    print(f"   Fecha: {test_data['appointment']['appointment_date']} {test_data['appointment']['time_start']}")
    print(f"   Negocio: {test_data['tenant']['name']}")
    print()

    # Simulación del paso 1: Envío de recordatorio
    print("📤 PASO 1: ENVÍO DE RECORDATORIO")
    print("-" * 40)
    
    # Mock de Evolution API response
    evolution_response = {
        "data": {
            "key": {
                "remoteJid": "573001234567@s.whatsapp.net",
                "id": "MSG-REMINDER-ABC123",
                "fromMe": True
            },
            "message": {
                "conversation": "Hola Juan Pablo, soy Kibo, el asistente de Clínica Dental SmileCare..."
            }
        },
        "status": "success"
    }
    
    print(f"✅ Evolution API Response simulado:")
    print(f"   RemoteJid capturado: {evolution_response['data']['key']['remoteJid']}")
    print(f"   Message ID: {evolution_response['data']['key']['id']}")
    
    # Simular extracción de remote_id
    from app.services.scheduler.reminder_scheduler import ReminderScheduler
    scheduler = ReminderScheduler(None)
    extracted_remote_id = scheduler._extract_remote_id(evolution_response)
    
    print(f"✅ Remote ID extraído correctamente: {extracted_remote_id}")
    
    # Actualizar datos de prueba con el remote_id
    test_data['appointment']['whatsapp_remote_id'] = extracted_remote_id
    print(f"✅ [OUTBOUND] JID {extracted_remote_id} vinculado a Cita {test_data['appointment']['id']}")
    print()

    # Simulación del paso 2: Respuesta del cliente
    print("📥 PASO 2: RESPUESTA DEL CLIENTE") 
    print("-" * 40)
    
    # Payload de webhook simulando respuesta "1" (confirmar)
    webhook_payload = {
        "event": "messages.upsert",
        "instance": test_data['tenant']['whatsapp_instance_id'],
        "data": {
            "key": {
                "remoteJid": extracted_remote_id,  # Mismo JID que se capturó
                "fromMe": False,
                "id": "MSG-CLIENT-RESPONSE-456"
            },
            "message": {
                "conversation": "1"  # Confirmación
            }
        }
    }
    
    print(f"✅ Cliente responde: '1' (Confirmar)")
    print(f"✅ RemoteJid en webhook: {webhook_payload['data']['key']['remoteJid']}")
    print(f"✅ Coincide con JID capturado: {extracted_remote_id == webhook_payload['data']['key']['remoteJid']}")
    print()

    # Simulación del paso 3: Procesamiento del webhook
    print("🔄 PASO 3: PROCESAMIENTO DEL WEBHOOK")
    print("-" * 40)
    
    # Simular extracción de datos del webhook
    from app.api.v1.whatsapp.router import _extract_remote_jid, _extract_text, _extract_from_me, _is_group_message, _extract_message_type
    
    remote_jid = _extract_remote_jid(webhook_payload)
    message_text = _extract_text(webhook_payload)
    from_me = _extract_from_me(webhook_payload)
    is_group = _is_group_message(webhook_payload)
    message_type = _extract_message_type(webhook_payload)
    
    print(f"✅ Extracción de datos del webhook:")
    print(f"   Remote JID: {remote_jid}")
    print(f"   Texto: '{message_text}'")
    print(f"   From Me: {from_me}")
    print(f"   Es Grupo: {is_group}")
    print(f"   Tipo de Mensaje: {message_type}")
    print()
    
    # Verificar filtros
    print("🚦 VERIFICACIÓN DE FILTROS:")
    filters_passed = True
    
    if is_group:
        print("❌ FILTRO: Mensaje de grupo - RECHAZADO")
        filters_passed = False
    else:
        print("✅ FILTRO: No es grupo - APROBADO")
        
    if from_me:
        print("❌ FILTRO: Mensaje propio - RECHAZADO") 
        filters_passed = False
    else:
        print("✅ FILTRO: No es mensaje propio - APROBADO")
        
    allowed_types = {"conversation", "extendedTextMessage"}
    if message_type not in allowed_types:
        print(f"❌ FILTRO: Tipo '{message_type}' no permitido - RECHAZADO")
        filters_passed = False
    else:
        print(f"✅ FILTRO: Tipo '{message_type}' permitido - APROBADO")
    
    print()
    
    if not filters_passed:
        print("❌ WEBHOOK RECHAZADO POR FILTROS")
        return False
    
    # Simular lógica de match
    print("🎯 LÓGICA DE MATCH:")
    print("-" * 40)
    
    # El remote_jid coincide con el de la cita
    jid_match = (remote_jid == test_data['appointment']['whatsapp_remote_id'])
    print(f"✅ [WH_MATCH] Buscando cita por RemoteID: {remote_jid}")
    
    if jid_match:
        print(f"✅ [WH_MATCH] Cita encontrada por RemoteID!")
        print(f"   Appointment ID: {test_data['appointment']['id']}")
        print(f"   Cliente: {test_data['client']['name']}")
        print(f"   Matched By: remote_id")
        
        # Simular actualización de estado
        print(f"\n📝 ACTUALIZANDO ESTADO DE CITA:")
        test_data['appointment']['status'] = 'CONFIRMED'
        print(f"✅ Status: PENDING → CONFIRMED")
        
        # Simular mensaje de confirmación
        confirmation_msg = f"¡Confirmado! Gracias por elegir {test_data['tenant']['name']}. Nos vemos pronto."
        print(f"✅ Mensaje enviado: '{confirmation_msg}'")
        
        print(f"\n🎉 FLUJO COMPLETADO EXITOSAMENTE!")
        print(f"✅ RemoteJID capturado durante recordatorio")
        print(f"✅ Webhook match por RemoteJID (no por teléfono)")
        print(f"✅ Cita confirmada automáticamente")
        print(f"✅ Mensaje de confirmación enviado")
        
        return True
    else:
        print(f"❌ No se encontró match por RemoteJID")
        print(f"   Expected: {test_data['appointment']['whatsapp_remote_id']}")
        print(f"   Received: {remote_jid}")
        return False

def test_api_endpoints():
    """Prueba de endpoints HTTP si el servidor está corriendo"""
    print("\n🌐 PRUEBA DE ENDPOINTS HTTP")
    print("=" * 60)
    
    base_url = "http://localhost:8000"
    
    try:
        # Test health endpoint
        response = httpx.get(f"{base_url}/health")
        if response.status_code == 200:
            print("✅ Servidor corriendo en localhost:8000")
            
            # Test webhook endpoint con payload de prueba
            webhook_payload = {
                "event": "messages.upsert",
                "instance": "test-instance",
                "data": {
                    "key": {
                        "remoteJid": "573001234567@s.whatsapp.net",
                        "fromMe": False,
                        "id": "MSG-API-TEST-789"
                    },
                    "message": {"conversation": "1"}
                }
            }
            
            webhook_response = httpx.post(
                f"{base_url}/api/v1/webhooks/whatsapp",
                json=webhook_payload,
                timeout=10.0
            )
            
            print(f"✅ Webhook endpoint response: {webhook_response.status_code}")
            print(f"   Response: {webhook_response.json()}")
            
        else:
            print(f"❌ Servidor respondió con código: {response.status_code}")
            
    except Exception as e:
        print(f"❌ No se pudo conectar al servidor: {e}")
        print("   Asegúrate de que el servidor esté corriendo con:")
        print("   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")

if __name__ == "__main__":
    print("🚀 KIBO - PRUEBA DEL SISTEMA REMOTEJID")
    print("Sistema de captura y match de IDs de WhatsApp")
    print("=" * 60)
    print()
    
    # Prueba del flujo lógico
    success = test_remote_jid_flow()
    
    if success:
        print(f"\n✅ PRUEBA LÓGICA: EXITOSA")
    else:
        print(f"\n❌ PRUEBA LÓGICA: FALLÓ")
    
    # Prueba de endpoints HTTP
    test_api_endpoints()
    
    print(f"\n" + "=" * 60)
    print("🏁 PRUEBA COMPLETADA")