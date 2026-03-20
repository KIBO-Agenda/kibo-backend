from typing import Annotated
from datetime import datetime, timezone
import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.auth import User, UserRole
from app.repositories.tenant import PaymentRepository, TenantRepository


def _ensure_tenant_trial_or_payment(db: Session, tenant_id: uuid.UUID) -> None:
    tenant_repo = TenantRepository(db)
    payment_repo = PaymentRepository(db)

    tenant = tenant_repo.get_by_id(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    trial_ends_at = getattr(tenant, "trial_ends_at", None)
    if not trial_ends_at:
        return

    now = datetime.now(timezone.utc)
    trial_reference = (
        trial_ends_at
        if trial_ends_at.tzinfo is not None
        else trial_ends_at.replace(tzinfo=timezone.utc)
    )
    if now < trial_reference:
        return

    if payment_repo.has_any_by_tenant(tenant_id):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Tu periodo de prueba ha terminado. Contacta a soporte o realiza un pago",
    )


def get_tenant_id_from_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> str:
    """Extract tenant_id from JWT token header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = authorization.split(" ")[1]
    try:
        payload = decode_token(token)
        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing tenant_id",
            )
        return tenant_id
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )


def get_super_admin_id_from_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> str:
    """Extract super_admin ID from JWT (scope='super_admin')."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = authorization.split(" ")[1]
    try:
        payload = decode_token(token)
        scope = payload.get("scope")
        if scope != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super admin access required",
            )
        return payload.get("sub")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )


def get_current_tenant_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    db: Session = Depends(get_db),
) -> User:
    """Resolve authenticated tenant user from bearer token and DB."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = authorization.split(" ")[1]
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    if payload.get("scope") != "tenant_user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant user access required",
        )

    sub = payload.get("sub")
    tenant_id_str = payload.get("tenant_id")
    if not sub or not tenant_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant token payload",
        )

    try:
        user_id = uuid.UUID(sub)
        tenant_id = uuid.UUID(tenant_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject or tenant_id",
        ) from exc

    user = (
        db.query(User)
        .filter(User.id == user_id, User.tenant_id == tenant_id, User.is_active.is_(True))
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    _ensure_tenant_trial_or_payment(db, tenant_id)
    return user


def check_tenant_active(
    current_user: Annotated[User, Depends(get_current_tenant_user)],
    db: Session = Depends(get_db),
) -> User:
    _ensure_tenant_trial_or_payment(db, current_user.tenant_id)
    return current_user


def require_owner(
    current_user: Annotated[User, Depends(get_current_tenant_user)],
) -> User:
    """Require owner role for privileged tenant operations."""
    if current_user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner role required",
        )
    return current_user
