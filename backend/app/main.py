import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import services as svc
from .alerts import evaluate_alerts
from .config import get_settings
from .db import SessionLocal
from .routers import admin, auth, machine, webhooks

log = logging.getLogger("rvm.backend")
settings = get_settings()


async def reconciler_loop() -> None:
    while True:
        await asyncio.sleep(settings.reconcile_interval_s)
        try:
            async with SessionLocal() as db:
                n = await svc.reconcile_once(db)
                await evaluate_alerts(db)
            if n:
                log.info("Reconciler updated %s rows", n)
        except Exception:
            log.exception("Reconciler failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(reconciler_loop())
    yield
    task.cancel()


app = FastAPI(title="TASMAC RVM Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(machine.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(webhooks.router)


@app.exception_handler(svc.DomainError)
async def domain_error(request: Request, exc: svc.DomainError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.code})


@app.get("/health")
async def health():
    return {"status": "ok"}
