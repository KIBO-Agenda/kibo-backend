"""
Shared pytest configuration and fixtures for all tests.
Uses in-memory SQLite to avoid PostgreSQL dependency.
"""

import importlib
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base

# CRITICAL: Import app AFTER configuring test database
# Create test engine FIRST before importing models
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

    def sqlite_regexp_replace(value, pattern, replacement, flags=None):
        del flags
        if value is None:
            return ""
        return re.sub(pattern, replacement, str(value))

    dbapi_conn.create_function("regexp_replace", 4, sqlite_regexp_replace)


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(_type, _compiler, **_kwargs) -> str:
    return "TEXT"


# Import all model modules so Base metadata includes every table.
os.environ.setdefault("WHATSAPP_DB_SCHEMA", "")
importlib.import_module("app.models")

for table in Base.metadata.tables.values():
    for column in table.columns:
        server_default = column.server_default
        default_text = getattr(getattr(server_default, "arg", None), "text", "")
        if isinstance(default_text, str) and "::jsonb" in default_text:
            column.server_default = text("'{}'")

Base.metadata.create_all(test_engine)

TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, class_=Session)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Provide clean SQLite session for tests."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def test_app(db):
    """FastAPI test app with mocked database."""
    from app.db.session import get_db
    from app.main import app

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def test_client(test_app):
    """FastAPI test client."""
    from fastapi.testclient import TestClient

    return TestClient(test_app)


@pytest.fixture
def sample_tenant(db: Session):
    """Create a sample tenant for testing."""
    from app.models.tenant import SubscriptionStatus, Tenant

    tenant = Tenant(
        name="Test Barbershop",
        phone="555-1234",
        subscription_status=SubscriptionStatus.ACTIVE,
        subscription_valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@pytest.fixture
def sample_super_admin():
    """Return synthetic super admin identity for token payloads."""
    return {"id": str(uuid.uuid4())}


@pytest.fixture
def sample_tenant_user(db: Session, sample_tenant):
    """Create a sample tenant owner for testing owner-protected endpoints."""
    from app.core.security import get_password_hash
    from app.models.auth import User, UserRole

    user = User(
        tenant_id=sample_tenant.id,
        email="user@example.com",
        password_hash=get_password_hash("UserPass123"),
        name="Test User",
        role=UserRole.OWNER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def jwt_token_super_admin(sample_super_admin):
    """Generate JWT token for super admin."""
    from app.core.security import create_access_token

    return create_access_token(
        subject={
            "sub": sample_super_admin["id"],
            "scope": "super_admin",
        }
    )


@pytest.fixture
def jwt_token_tenant_user(sample_tenant_user):
    """Generate JWT token for tenant user."""
    from app.core.security import create_access_token

    return create_access_token(
        subject={
            "sub": str(sample_tenant_user.id),
            "scope": "tenant_user",
            "tenant_id": str(sample_tenant_user.tenant_id),
        }
    )
