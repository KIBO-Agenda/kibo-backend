from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.appointments import Appointment, AppointmentStatus
from app.models.auth import User, UserRole
from app.models.clients import Client
from app.models.services import Service
from app.services.tenant import TenantService
from app.services.users import UserService


def _owner_token(user: User) -> str:
    return create_access_token(
        subject={
            "sub": str(user.id),
            "scope": "tenant_user",
            "tenant_id": str(user.tenant_id),
        }
    )


def _next_monday() -> date:
    today = date.today()
    delta = (0 - today.weekday()) % 7
    return today + timedelta(days=delta)


class TestMaxUsersRules:
    def test_create_staff_counts_only_active_staff(self, db):
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant = tenant_service.create_tenant(name="Plan Test", phone=None, max_users=1)

        # Owner should not consume specialist quota.
        user_service.create_user(
            tenant.id,
            email="owner-plan@test.com",
            name="Owner",
            password="SecurePass123",
            role=UserRole.OWNER,
        )

        user_service.create_staff_user(
            tenant.id,
            email="staff-1@test.com",
            name="Staff 1",
            password="SecurePass123",
        )

        with pytest.raises(Exception) as exc_info:
            user_service.create_staff_user(
                tenant.id,
                email="staff-2@test.com",
                name="Staff 2",
                password="SecurePass123",
            )

        assert "Limite de especialistas alcanzado" in str(exc_info.value)

    def test_activate_staff_reuses_same_plan_rule(self, db):
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant = tenant_service.create_tenant(name="Activation Plan", phone=None, max_users=1)

        user_service.create_user(
            tenant.id,
            email="owner-activation@test.com",
            name="Owner",
            password="SecurePass123",
            role=UserRole.OWNER,
        )
        active_staff = user_service.create_user(
            tenant.id,
            email="active-staff@test.com",
            name="Active Staff",
            password="SecurePass123",
            role=UserRole.STAFF,
        )
        inactive_staff = user_service.create_user(
            tenant.id,
            email="inactive-staff@test.com",
            name="Inactive Staff",
            password="SecurePass123",
            role=UserRole.STAFF,
        )
        user_service.update_user(tenant.id, inactive_staff.id, is_active=False)

        assert active_staff.is_active is True

        with pytest.raises(Exception) as exc_info:
            user_service.activate_staff_user(tenant.id, inactive_staff.id)

        assert "Limite de especialistas alcanzado" in str(exc_info.value)


class TestActivationAndAgendaIntegration:
    def test_get_tenant_settings_returns_stable_contract(self, test_client: TestClient, db):
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant = tenant_service.create_tenant(name="Tenant Settings", phone="5551002000", max_users=7)
        owner = user_service.create_user(
            tenant.id,
            email="owner-settings@test.com",
            name="Owner Settings",
            password="SecurePass123",
            role=UserRole.OWNER,
        )

        response = test_client.get(
            "/api/v1/tenants/settings",
            headers={"Authorization": f"Bearer {_owner_token(owner)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(tenant.id)
        assert data["name"] == "Tenant Settings"
        assert data["phone"] == "5551002000"
        assert data["slot_duration"] == 15
        assert data["max_users"] == 7
        assert data["subscription_status"] in {"active", "past_due", "suspended"}
        assert set(data["business_hours"].keys()) == {
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }

    def test_activate_staff_endpoint_success(self, test_client: TestClient, db):
        tenant_service = TenantService(db)
        user_service = UserService(db)
        tenant = tenant_service.create_tenant(name="Tenant A", phone=None, max_users=2)

        owner = user_service.create_user(
            tenant.id,
            email="owner-a@test.com",
            name="Owner A",
            password="SecurePass123",
            role=UserRole.OWNER,
        )
        inactive_staff = user_service.create_user(
            tenant.id,
            email="staff-a@test.com",
            name="Staff A",
            password="SecurePass123",
            role=UserRole.STAFF,
        )
        user_service.update_user(tenant.id, inactive_staff.id, is_active=False)

        response = test_client.patch(
            f"/api/v1/users/{inactive_staff.id}/activate",
            headers={"Authorization": f"Bearer {_owner_token(owner)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(inactive_staff.id)
        assert data["name"] == "Staff A"
        assert data["email"] == "staff-a@test.com"
        assert data["role"] == "staff"
        assert data["is_active"] is True

    def test_activate_staff_endpoint_rejects_when_plan_exceeded(self, test_client: TestClient, db):
        tenant_service = TenantService(db)
        user_service = UserService(db)
        tenant = tenant_service.create_tenant(name="Tenant B", phone=None, max_users=1)

        owner = user_service.create_user(
            tenant.id,
            email="owner-b@test.com",
            name="Owner B",
            password="SecurePass123",
            role=UserRole.OWNER,
        )
        user_service.create_user(
            tenant.id,
            email="staff-b-active@test.com",
            name="Staff B Active",
            password="SecurePass123",
            role=UserRole.STAFF,
        )
        inactive_staff = user_service.create_user(
            tenant.id,
            email="staff-b-inactive@test.com",
            name="Staff B Inactive",
            password="SecurePass123",
            role=UserRole.STAFF,
        )
        user_service.update_user(tenant.id, inactive_staff.id, is_active=False)

        response = test_client.patch(
            f"/api/v1/users/{inactive_staff.id}/activate",
            headers={"Authorization": f"Bearer {_owner_token(owner)}"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Limite de especialistas alcanzado"

    def test_agenda_weekly_hide_inactive_staff_appointments(self, test_client: TestClient, db):
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant = tenant_service.create_tenant(name="Tenant C", phone=None, max_users=5)
        owner = user_service.create_user(
            tenant.id,
            email="owner-c@test.com",
            name="Owner C",
            password="SecurePass123",
            role=UserRole.OWNER,
        )
        active_staff = user_service.create_user(
            tenant.id,
            email="staff-c-active@test.com",
            name="Active Staff C",
            password="SecurePass123",
            role=UserRole.STAFF,
        )
        inactive_staff = user_service.create_user(
            tenant.id,
            email="staff-c-inactive@test.com",
            name="Inactive Staff C",
            password="SecurePass123",
            role=UserRole.STAFF,
        )
        user_service.update_user(tenant.id, inactive_staff.id, is_active=False)

        service = Service(
            tenant_id=tenant.id,
            name="Haircut",
            duration=30,
            price=Decimal("35.00"),
            is_active=True,
        )
        client = Client(
            tenant_id=tenant.id,
            name="Client C",
            phone="5551112233",
        )
        db.add_all([service, client])
        db.commit()
        db.refresh(service)
        db.refresh(client)

        appointment_date = _next_monday()
        db.add_all(
            [
                Appointment(
                    tenant_id=tenant.id,
                    client_id=client.id,
                    user_id=active_staff.id,
                    service_id=service.id,
                    appointment_date=appointment_date,
                    time_start=time(9, 0),
                    time_end=time(9, 30),
                    status=AppointmentStatus.PENDING,
                ),
                Appointment(
                    tenant_id=tenant.id,
                    client_id=client.id,
                    user_id=inactive_staff.id,
                    service_id=service.id,
                    appointment_date=appointment_date,
                    time_start=time(10, 0),
                    time_end=time(10, 30),
                    status=AppointmentStatus.PENDING,
                ),
            ]
        )
        db.commit()

        token = _owner_token(owner)
        agenda_response = test_client.get(
            f"/api/v1/appointments/agenda?start_date={appointment_date.isoformat()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert agenda_response.status_code == 200
        agenda_data = agenda_response.json()
        assert agenda_data["summary"]["total"] == 1
        assert len(agenda_data["appointments"]) == 1
        assert agenda_data["appointments"][0]["staff_name"] == "Active Staff C"

        start_of_week = appointment_date - timedelta(days=appointment_date.weekday())
        weekly_response = test_client.get(
            f"/api/v1/appointments/weekly?start_date={start_of_week.isoformat()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert weekly_response.status_code == 200
        weekly_data = weekly_response.json()
        assert weekly_data["weekly_summary"]["total"] == 1
        total_weekly_items = sum(len(day["appointments"]) for day in weekly_data["days"])
        assert total_weekly_items == 1

    def test_availability_and_create_reject_inactive_staff(self, test_client: TestClient, db):
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant = tenant_service.create_tenant(name="Tenant D", phone=None, max_users=5)
        owner = user_service.create_user(
            tenant.id,
            email="owner-d@test.com",
            name="Owner D",
            password="SecurePass123",
            role=UserRole.OWNER,
        )
        inactive_staff = user_service.create_user(
            tenant.id,
            email="staff-d-inactive@test.com",
            name="Inactive Staff D",
            password="SecurePass123",
            role=UserRole.STAFF,
        )
        user_service.update_user(tenant.id, inactive_staff.id, is_active=False)

        service = Service(
            tenant_id=tenant.id,
            name="Shave",
            duration=20,
            price=Decimal("25.00"),
            is_active=True,
        )
        db.add(service)
        db.commit()
        db.refresh(service)

        appointment_date = _next_monday()
        token = _owner_token(owner)

        availability_response = test_client.get(
            f"/api/v1/appointments/availability?date={appointment_date.isoformat()}&staff_id={inactive_staff.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert availability_response.status_code == 400
        assert availability_response.json()["detail"] == "Staff user is inactive"

        create_response = test_client.post(
            "/api/v1/appointments",
            json={
                "client_name": "Client D",
                "client_phone": "5559990001",
                "user_id": str(inactive_staff.id),
                "service_id": str(service.id),
                "appointment_date": appointment_date.isoformat(),
                "time_start": "09:00",
                "notes": "inactive staff should fail",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_response.status_code == 400
        assert create_response.json()["detail"] == "Assigned user is inactive"

    def test_services_list_returns_price(self, test_client: TestClient, db):
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant = tenant_service.create_tenant(name="Tenant E", phone=None, max_users=5)
        owner = user_service.create_user(
            tenant.id,
            email="owner-e@test.com",
            name="Owner E",
            password="SecurePass123",
            role=UserRole.OWNER,
        )

        create_response = test_client.post(
            "/api/v1/services",
            json={"name": "Premium Cut", "duration": 45, "price": "49.90"},
            headers={"Authorization": f"Bearer {_owner_token(owner)}"},
        )
        assert create_response.status_code == 201

        list_response = test_client.get(
            "/api/v1/services",
            headers={"Authorization": f"Bearer {_owner_token(owner)}"},
        )
        assert list_response.status_code == 200
        data = list_response.json()
        assert len(data) == 1
        assert "price" in data[0]
        assert str(data[0]["price"]) in {"49.9", "49.90"}
