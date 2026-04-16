"""
Test suite for tenant + users + payments CRUD with SOLID principles.
Validates business rules: multi-tenant isolation, subscription logic, role-based access.
Run with: python -m pytest tests/services/tenant/test_tenant_module.py -v
"""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.auth import UserRole
from app.models.tenant import SubscriptionStatus
from app.services.tenant import PaymentService, TenantService
from app.services.users import UserService


class TestTenantService:
    """Test tenant creation and management."""

    def test_create_tenant_has_30_day_subscription(self, db: Session):
        """Rule: New tenant gets 30-day subscription."""
        service = TenantService(db)
        now = datetime.now()

        tenant = service.create_tenant(
            name="Test Barbershop",
            phone="555-1234",
            slot_duration=15,
        )

        assert tenant.name == "Test Barbershop"
        assert tenant.subscription_status == SubscriptionStatus.ACTIVE
        # Subscription should be ~30 days in future
        delta_days = (tenant.subscription_valid_until - now).days
        assert 29 <= delta_days <= 31
        assert tenant.slot_duration == 15

    def test_get_tenant(self, db: Session):
        """Rule: Can retrieve tenant by ID."""
        service = TenantService(db)
        tenant = service.create_tenant(name="Test", phone=None)

        retrieved = service.get_tenant(tenant.id)
        assert retrieved.id == tenant.id
        assert retrieved.name == "Test"

    def test_update_tenant(self, db: Session):
        """Rule: Can update tenant fields."""
        service = TenantService(db)
        tenant = service.create_tenant(name="Original", phone="123")

        updated = service.update_tenant(
            tenant.id,
            name="Updated",
            slot_duration=30,
        )

        assert updated.name == "Updated"
        assert updated.slot_duration == 30
        assert updated.phone == "123"  # unchanged


class TestPaymentService:
    """Test payment registration and subscription extension."""

    def test_register_payment_extends_subscription(self, db: Session):
        """Rule: Payment auto-extends subscription by 30 days."""
        tenant_service = TenantService(db)
        payment_service = PaymentService(db)

        tenant = tenant_service.create_tenant(name="Test", phone=None)
        original_until = tenant.subscription_valid_until

        payment_service.register_payment(
            tenant.id,
            amount=Decimal("50000.00"),
            payment_method="Cash",
        )

        # Retrieve updated tenant
        updated_tenant = tenant_service.get_tenant(tenant.id)
        delta_days = (updated_tenant.subscription_valid_until - original_until).days
        assert 29 <= delta_days <= 31, f"Expected ~30 days extension, got {delta_days}"

    def test_prevent_duplicate_payments(self, db: Session):
        """Rule: Same reference_code cannot be used twice."""
        payment_service = PaymentService(db)
        tenant_service = TenantService(db)

        tenant = tenant_service.create_tenant(name="Test", phone=None)

        # First payment
        payment_service.register_payment(
            tenant.id,
            amount=Decimal("100.00"),
            reference_code="REF-001",
        )

        # Second payment with same reference should fail
        with pytest.raises(Exception):
            payment_service.register_payment(
                tenant.id,
                amount=Decimal("100.00"),
                reference_code="REF-001",
            )

    def test_list_tenant_payments_multi_tenant_filtered(self, db: Session):
        """Rule: Payments are filtered by tenant_id."""
        tenant_service = TenantService(db)
        payment_service = PaymentService(db)

        tenant1 = tenant_service.create_tenant(name="Tenant1", phone=None)
        tenant2 = tenant_service.create_tenant(name="Tenant2", phone=None)

        # Add payments to both
        payment_service.register_payment(tenant1.id, amount=Decimal("100.00"), reference_code="T1-001")
        payment_service.register_payment(tenant1.id, amount=Decimal("200.00"), reference_code="T1-002")
        payment_service.register_payment(tenant2.id, amount=Decimal("300.00"), reference_code="T2-001")

        payments_t1 = payment_service.list_tenant_payments(tenant1.id)
        payments_t2 = payment_service.list_tenant_payments(tenant2.id)

        assert len(payments_t1) == 2
        assert len(payments_t2) == 1


class TestUserService:
    """Test user CRUD with multi-tenant enforcement."""

    def test_create_user_in_tenant(self, db: Session):
        """Rule: User is created within a tenant."""
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant = tenant_service.create_tenant(name="Test", phone=None)
        user = user_service.create_user(
            tenant.id,
            email="barber@test.com",
            name="John Barber",
            password="SecurePass123",
            role=UserRole.STAFF,
        )

        assert user.tenant_id == tenant.id
        assert user.email == "barber@test.com"
        assert user.role == UserRole.STAFF
        assert verify_password("SecurePass123", user.password_hash)

    def test_email_normalized_on_create(self, db: Session):
        """Rule: Email is normalized (lowercase, trimmed) at creation."""
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant = tenant_service.create_tenant(name="Test", phone=None)
        user = user_service.create_user(
            tenant.id,
            email=" OWNER@EXAMPLE.COM ",
            name="Owner",
            password="Pass123",
            role=UserRole.OWNER,
        )

        assert user.email == "owner@example.com"

    def test_prevent_duplicate_email_in_platform(self, db: Session):
        """Rule: Email must be unique platform-wide."""
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant = tenant_service.create_tenant(name="Test", phone=None)

        # Create first user
        user_service.create_user(
            tenant.id,
            email="john@test.com",
            name="John",
            password="Pass123",
        )

        # Try to create another with same email
        with pytest.raises(Exception):
            user_service.create_user(
                tenant.id,
                email="john@test.com",
                name="John2",
                password="Pass456",
            )

    def test_get_user_with_multi_tenant_filter(self, db: Session):
        """Rule: Get user enforces tenant_id boundary."""
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant1 = tenant_service.create_tenant(name="Tenant1", phone=None)
        tenant2 = tenant_service.create_tenant(name="Tenant2", phone=None)

        user1 = user_service.create_user(
            tenant1.id,
            email="user@tenant1.com",
            name="User1",
            password="Pass123",
        )

        # User from tenant1 should be accessible in tenant1 context
        retrieved = user_service.get_user(tenant1.id, user1.id)
        assert retrieved.id == user1.id

        # User should NOT be accessible from different tenant context
        with pytest.raises(Exception):
            user_service.get_user(tenant2.id, user1.id)

    def test_list_users_only_in_tenant(self, db: Session):
        """Rule: List users shows only users in that tenant."""
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant1 = tenant_service.create_tenant(name="Tenant1", phone=None)
        tenant2 = tenant_service.create_tenant(name="Tenant2", phone=None)

        # Add 2 users to tenant1, 1 to tenant2
        for i in range(2):
            user_service.create_user(
                tenant1.id,
                email=f"user{i}@tenant1.com",
                name=f"User{i}",
                password="Pass123",
            )

        user_service.create_user(
            tenant2.id,
            email="user@tenant2.com",
            name="User",
            password="Pass123",
        )

        users_t1 = user_service.list_users(tenant1.id)
        users_t2 = user_service.list_users(tenant2.id)

        assert len(users_t1) == 2
        assert len(users_t2) == 1

    def test_soft_delete_user(self, db: Session):
        """Rule: Delete sets is_active=False (soft delete)."""
        tenant_service = TenantService(db)
        user_service = UserService(db)

        tenant = tenant_service.create_tenant(name="Test", phone=None)
        user = user_service.create_user(
            tenant.id,
            email="temp@test.com",
            name="Temporary",
            password="Pass123",
        )

        user_service.delete_user(tenant.id, user.id)

        # Verify in DB that user is still there but inactive
        db.refresh(user)
        assert user.is_active is False


# CLI runner for manual testing
if __name__ == "__main__":
    import sys

    pytest.main([__file__, "-v"] + sys.argv[1:])
