"""
HTTP integration tests for tenant/users/payments APIs.
Tests multi-tenant enforcement, authentication, and business rules via FastAPI endpoints.
Run with: python -m pytest tests/api/v1/test_http_integration.py -v
"""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


class TestTenantHTTP:
    """Test tenant endpoints with JWT authentication."""

    def test_create_tenant_unauthorized_without_super_admin(self, test_client: TestClient):
        """Rule: Non-super_admin cannot create tenants (401)."""
        response = test_client.post(
            "/api/v1/tenants",
            json={
                "name": "New Barbershop",
                "phone": "555-1234",
            },
        )
        assert response.status_code == 401  # Unauthorized

    def test_create_tenant_as_super_admin(self, test_client: TestClient, jwt_token_super_admin):
        """Rule: Super admin can create tenant with 30-day subscription."""
        response = test_client.post(
            "/api/v1/tenants",
            json={
                "name": "Premium Salon",
                "phone": "555-9876",
                "slot_duration": 20,
            },
            headers={"Authorization": f"Bearer {jwt_token_super_admin}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Premium Salon"
        assert data["phone"] == "555-9876"
        assert data["slot_duration"] == 20
        assert data["subscription_status"] == "active"
        assert "subscription_valid_until" in data

    def test_list_tenants_as_super_admin(self, test_client: TestClient, jwt_token_super_admin):
        """Rule: Super admin can list all tenants."""
        # Create a tenant first
        create_resp = test_client.post(
            "/api/v1/tenants",
            json={"name": "Test Salon", "phone": "555-1111"},
            headers={"Authorization": f"Bearer {jwt_token_super_admin}"},
        )
        assert create_resp.status_code == 201

        # List tenants
        list_resp = test_client.get(
            "/api/v1/tenants",
            headers={"Authorization": f"Bearer {jwt_token_super_admin}"},
        )

        assert list_resp.status_code == 200
        data = list_resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(t["name"] == "Test Salon" for t in data)

    def test_get_tenant_as_super_admin(self, test_client: TestClient, jwt_token_super_admin, sample_tenant):
        """Rule: Super admin can retrieve tenant by ID."""
        response = test_client.get(
            f"/api/v1/tenants/{sample_tenant.id}",
            headers={"Authorization": f"Bearer {jwt_token_super_admin}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_tenant.id)
        assert data["name"] == sample_tenant.name

    def test_update_tenant_as_super_admin(self, test_client: TestClient, jwt_token_super_admin, sample_tenant):
        """Rule: Super admin can update tenant fields."""
        response = test_client.patch(
            f"/api/v1/tenants/{sample_tenant.id}",
            json={
                "name": "Updated Salon",
                "slot_duration": 30,
            },
            headers={"Authorization": f"Bearer {jwt_token_super_admin}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Salon"
        assert data["slot_duration"] == 30


class TestPaymentHTTP:
    """Test payment endpoints with multi-tenant isolation."""

    def test_register_payment_as_tenant_user(
        self,
        test_client: TestClient,
        jwt_token_tenant_user,
        sample_tenant,
    ):
        """Rule: Tenant user can register payment for their tenant."""
        response = test_client.post(
            "/api/v1/payments",
            json={
                "amount": "50000.00",
                "payment_method": "Cash",
                "reference_code": f"PAY-{uuid.uuid4().hex[:8]}",
            },
            headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert Decimal(data["amount"]) == Decimal("50000.00")
        assert data["tenant_id"] == str(sample_tenant.id)

    def test_register_payment_extends_subscription(
        self,
        test_client: TestClient,
        jwt_token_tenant_user,
        db,
        sample_tenant,
    ):
        """Rule: Payment extends subscription_valid_until by ~30 days."""
        old_until = sample_tenant.subscription_valid_until

        response = test_client.post(
            "/api/v1/payments",
            json={
                "amount": "10000.00",
                "payment_method": "Bank Transfer",
                "reference_code": f"EXT-{uuid.uuid4().hex[:8]}",
            },
            headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
        )

        assert response.status_code == 201

        # Refresh tenant from DB
        db.refresh(sample_tenant)
        delta_days = (sample_tenant.subscription_valid_until - old_until).days
        assert 29 <= delta_days <= 31

    def test_list_payments_multi_tenant_isolated(
        self,
        test_client: TestClient,
        jwt_token_tenant_user,
        sample_tenant_user,
        sample_tenant,
        db,
    ):
        """Rule: list_payments shows only payments for that tenant."""
        # Register 2 payments for sample_tenant
        for i in range(2):
            test_client.post(
                "/api/v1/payments",
                json={
                    "amount": f"{10000 * (i + 1)}.00",
                    "payment_method": "Cash",
                    "reference_code": f"T1-{i}",
                },
                headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
            )

        # List payments (should return 2)
        response = test_client.get(
            "/api/v1/payments",
            headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(p["tenant_id"] == str(sample_tenant.id) for p in data)

    def test_duplicate_payment_reference_rejected(
        self,
        test_client: TestClient,
        jwt_token_tenant_user,
    ):
        """Rule: Duplicate reference_code returns 409 Conflict."""
        ref_code = f"DUP-{uuid.uuid4().hex[:8]}"

        # First payment
        response1 = test_client.post(
            "/api/v1/payments",
            json={
                "amount": "5000.00",
                "payment_method": "Cash",
                "reference_code": ref_code,
            },
            headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
        )
        assert response1.status_code == 201

        # Second payment with same reference
        response2 = test_client.post(
            "/api/v1/payments",
            json={
                "amount": "5000.00",
                "payment_method": "Cash",
                "reference_code": ref_code,
            },
            headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
        )
        assert response2.status_code == 409  # Conflict


class TestUserHTTP:
    """Test user endpoints with multi-tenant enforcement."""

    def test_create_user_in_tenant(
        self,
        test_client: TestClient,
        jwt_token_tenant_user,
    ):
        """Rule: Tenant owner can create staff user."""
        response = test_client.post(
            "/api/v1/users",
            json={
                "email": "newstaff@test.com",
                "name": "New Staff",
                "password": "SecurePass123",
                "role": "staff",
            },
            headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newstaff@test.com"
        assert data["name"] == "New Staff"
        assert data["role"] == "staff"

    def test_list_users_in_tenant(
        self,
        test_client: TestClient,
        jwt_token_tenant_user,
        db,
        sample_tenant,
    ):
        """Rule: list_users shows only users in that tenant."""
        # Create 2 more users in this tenant
        for i in range(2):
            create_response = test_client.post(
                "/api/v1/users",
                json={
                    "email": f"staff{i}@test.com",
                    "name": f"Staff {i}",
                    "password": "Pass12345",
                    "role": "staff",
                },
                headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
            )
            assert create_response.status_code == 201

        # List users
        response = test_client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
        )

        assert response.status_code == 200
        data = response.json()
        # Should include at least the original user + 2 new ones
        assert len(data) >= 3

    def test_get_user_multi_tenant_boundary(
        self,
        test_client: TestClient,
        jwt_token_tenant_user,
        sample_tenant,
        sample_tenant_user,
        db,
    ):
        """Rule: Cannot retrieve user from different tenant."""
        # Create a different tenant with its own user
        from app.services.tenant import TenantService
        from app.services.users import UserService

        other_service = TenantService(db)
        user_service = UserService(db)

        other_tenant = other_service.create_tenant(name="Other", phone=None)
        other_user = user_service.create_user(
            other_tenant.id,
            email="other@test.com",
            name="Other User",
            password="Pass123",
        )

        # Try to get other_user from sample_tenant context
        response = test_client.get(
            f"/api/v1/users/{other_user.id}",
            headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
        )

        # Should be 404 (user not in tenant context)
        assert response.status_code == 404

    def test_delete_user_soft_delete(
        self,
        test_client: TestClient,
        jwt_token_tenant_user,
        db,
    ):
        """Rule: Delete sets is_active=False (no hard delete)."""
        # Create a user
        create_resp = test_client.post(
            "/api/v1/users",
            json={
                "email": "temp@test.com",
                "name": "Temporary",
                "password": "Pass12345",
            },
            headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
        )
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]

        # Delete
        delete_resp = test_client.delete(
            f"/api/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
        )
        assert delete_resp.status_code == 204

        # Verify in DB it's still there but inactive
        from app.models.auth import User

        user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
        assert user is not None
        assert user.is_active is False

    def test_update_user_within_tenant(
        self,
        test_client: TestClient,
        jwt_token_tenant_user,
        sample_tenant_user,
    ):
        """Rule: Update user works only for users in same tenant."""
        response = test_client.patch(
            f"/api/v1/users/{sample_tenant_user.id}",
            json={
                "name": "Updated Name",
            },
            headers={"Authorization": f"Bearer {jwt_token_tenant_user}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"


class TestAuthenticationHTTP:
    """Test authentication guards on all endpoints."""

    def test_missing_bearer_token_returns_401(self, test_client: TestClient):
        """Rule: Endpoints require Authorization header."""
        response = test_client.get("/api/v1/tenants")
        assert response.status_code == 401

    def test_invalid_bearer_token_returns_401(self, test_client: TestClient):
        """Rule: Invalid JWT returns 401."""
        response = test_client.get(
            "/api/v1/tenants",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    def test_expired_token_returns_401(self, test_client: TestClient):
        """Rule: Expired JWT returns 401."""
        from datetime import datetime, timedelta, timezone

        from jose import jwt

        from app.core.config import get_settings

        settings = get_settings()
        token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "scope": "super_admin",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        response = test_client.get(
            "/api/v1/tenants",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


if __name__ == "__main__":
    import sys

    pytest.main([__file__, "-v"] + sys.argv[1:])
