from app.api.v1.tenant.router import router
from app.api.v1.tenant.payments_router import router as payments_router

__all__ = ["router", "payments_router"]
