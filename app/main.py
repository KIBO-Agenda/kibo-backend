import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth.router import router as auth_router
from app.api.v1.super_admin.router import router as super_admin_router
from app.api.v1.tenant.router import router as tenant_router
from app.api.v1.tenant.payments_router import router as payments_router
from app.api.v1.users.router import router as users_router
from app.api.v1.clients.router import router as clients_router
from app.api.v1.services.router import router as services_router
from app.api.v1.appointments.router import router as appointments_router
from app.api.v1.waitlists.router import router as waitlists_router
from app.api.v1.whatsapp.router import router as whatsapp_router
from app.core.config import get_settings
from app.services.whatsapp.worker import run_outbox_worker

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker_stop_event: asyncio.Event | None = None
    worker_task: asyncio.Task | None = None

    if settings.WHATSAPP_WORKER_ENABLED:
        worker_stop_event = asyncio.Event()
        worker_task = asyncio.create_task(run_outbox_worker(worker_stop_event))

    yield

    if worker_task and worker_stop_event:
        worker_stop_event.set()
        await worker_task


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=settings.BACKEND_CORS_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(super_admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(tenant_router, prefix=settings.API_V1_PREFIX)
app.include_router(payments_router, prefix=settings.API_V1_PREFIX)
app.include_router(users_router, prefix=settings.API_V1_PREFIX)
app.include_router(clients_router, prefix=settings.API_V1_PREFIX)
app.include_router(services_router, prefix=settings.API_V1_PREFIX)
app.include_router(appointments_router, prefix=settings.API_V1_PREFIX)
app.include_router(waitlists_router, prefix=settings.API_V1_PREFIX)
app.include_router(whatsapp_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
