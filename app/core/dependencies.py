import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.auth import User, UserRole
from app.models.tenant import PlanTier
from app.repositories.tenant import PaymentRepository, TenantRepository

PLAN_RANK: dict[PlanTier, int] = {
    PlanTier.STARTER: 1,
    PlanTier.PRO: 2,
    PlanTier.BUSINESS: 3,
}


def has_min_plan_tier(current_tier: PlanTier, required_tier: PlanTier) -> bool:
    return PLAN_RANK[current_tier] >= PLAN_RANK[required_tier]


def _ensure_tenant_trial_or_payment(db: Session, tenant_id: uuid.UUID) -> bool:
    """Check if tenant is within trial or has an active payment.

    Returns:
        True if tenant can access (trial active or payment exists)
        False if tenant trial expired and no payment exists
    """
    tenant_repo = TenantRepository(db)
    payment_repo = PaymentRepository(db)

    tenant = tenant_repo.get_by_id(tenant_id)
    if not tenant:
        return False

    trial_ends_at = getattr(tenant, "trial_ends_at", None)
    if not trial_ends_at:
        return True

    now = datetime.now(timezone.utc)
    trial_reference = trial_ends_at if trial_ends_at.tzinfo is not None else trial_ends_at.replace(tzinfo=timezone.utc)
    if now < trial_reference:
        return True

    if payment_repo.has_any_by_tenant(tenant_id):
        return True

    return False


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

    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Check trial/payment status and require plan selection if trial expired
    if not _ensure_tenant_trial_or_payment(db, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TRIAL_EXPIRED_PLAN_REQUIRED",
        )
    return user


def check_tenant_active(
    current_user: Annotated[User, Depends(get_current_tenant_user)],
    db: Session = Depends(get_db),
) -> User:
    # Trial check is already done in get_current_tenant_user dependency
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


def check_plan_permission(required_tier: PlanTier):
    def _dependency(
        current_user: Annotated[User, Depends(get_current_tenant_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> User:
        tenant_repo = TenantRepository(db)
        tenant = tenant_repo.get_by_id(current_user.tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )

        if has_min_plan_tier(tenant.plan_tier, required_tier):
            return current_user

        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(f"This feature is available in the {required_tier.value} plan. " "Please upgrade to continue."),
        )

    return _dependency


def ensure_multi_location_permission(plan_tier: PlanTier, requested_locations: int) -> None:
    if requested_locations <= 1:
        return
    if has_min_plan_tier(plan_tier, PlanTier.BUSINESS):
        return

    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail="This feature is available in the business plan. Please upgrade to continue.",
    )
