"""Create deterministic test users for frontend QA.

Run:
    /venv/bin/python app/seeds/create_frontend_test_users.py
"""

from pathlib import Path
import sys

# Ensure project root is importable when running this file directly.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime, timezone
from datetime import timedelta

from sqlalchemy import func

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.auth import User, UserRole
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant, SubscriptionStatus


def ensure_super_admin(db):
    email = "qa.superadmin@example.com"
    password = "Admin1234!"

    entity = db.query(SuperAdmin).filter(func.lower(SuperAdmin.email) == email).first()
    if not entity:
        entity = SuperAdmin(
            name="QA Super Admin",
            email=email,
            password_hash=get_password_hash(password),
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)

    return {
        "email": email,
        "password": password,
    }


def ensure_tenant(db, name: str, phone: str):
    entity = db.query(Tenant).filter(Tenant.name == name).first()
    if not entity:
        now = datetime.now(timezone.utc)
        entity = Tenant(
            name=name,
            phone=phone,
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_valid_until=now + timedelta(days=30),
            trial_ends_at=now + timedelta(days=15),
            slot_duration=15,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
    return entity


def ensure_user(db, tenant_id, *, name: str, email: str, password: str, role: UserRole):
    entity = db.query(User).filter(func.lower(User.email) == email.lower()).first()
    if not entity:
        entity = User(
            tenant_id=tenant_id,
            name=name,
            email=email.lower(),
            password_hash=get_password_hash(password),
            role=role,
            is_active=True,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
    return {
        "email": email.lower(),
        "password": password,
        "role": role.value,
    }


def main() -> None:
    db = SessionLocal()
    try:
        super_admin = ensure_super_admin(db)

        tenant_1 = ensure_tenant(db, "Barberia Centro", "3000000001")
        tenant_2 = ensure_tenant(db, "Salon Norte", "3000000002")

        users = {
            "tenant_1": {
                "tenant_name": tenant_1.name,
                "owner": ensure_user(
                    db,
                    tenant_1.id,
                    name="Owner Centro",
                    email="owner.centro@example.com",
                    password="Owner1234!",
                    role=UserRole.OWNER,
                ),
                "staff_1": ensure_user(
                    db,
                    tenant_1.id,
                    name="Staff Centro 1",
                    email="staff1.centro@example.com",
                    password="Staff1234!",
                    role=UserRole.STAFF,
                ),
                "staff_2": ensure_user(
                    db,
                    tenant_1.id,
                    name="Staff Centro 2",
                    email="staff2.centro@example.com",
                    password="Staff1234!",
                    role=UserRole.STAFF,
                ),
            },
            "tenant_2": {
                "tenant_name": tenant_2.name,
                "owner": ensure_user(
                    db,
                    tenant_2.id,
                    name="Owner Norte",
                    email="owner.norte@example.com",
                    password="Owner1234!",
                    role=UserRole.OWNER,
                ),
                "staff_1": ensure_user(
                    db,
                    tenant_2.id,
                    name="Staff Norte 1",
                    email="staff1.norte@example.com",
                    password="Staff1234!",
                    role=UserRole.STAFF,
                ),
            },
        }

        print("FRONTEND_TEST_USERS_READY")
        print("super_admin:", super_admin)
        print("tenant_1_id:", str(tenant_1.id))
        print("tenant_1:", users["tenant_1"])
        print("tenant_2_id:", str(tenant_2.id))
        print("tenant_2:", users["tenant_2"])
    finally:
        db.close()


if __name__ == "__main__":
    main()
