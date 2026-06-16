"""FastAPI entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db, SessionLocal
from .auth import seed_admin
from .services.diretor_service import seed_diretor
from .middleware.backend_access import BackendAccessMiddleware
from .middleware.soc_lockdown import SocLockdownMiddleware
from .middleware.password_change_lockdown import PasswordChangeLockdownMiddleware
from .services.data_crypto_service import validate_security_config
from .routers import (
    clientes,
    envios,
    auth as auth_router,
    usuarios,
    status as status_router,
    autos,
    tipos_envio,
    corpos_email,
    assinaturas,
    capa,
    backup,
    notificacoes,
    soc,
)
from .services.full_watcher import watcher_global


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    validate_security_config()
    init_db()
    db = SessionLocal()
    try:
        seed_admin(db)
        seed_diretor(db)
    finally:
        db.close()
    watcher_global.start()
    log.info("Backend pronto. auth_enabled=%s full_enabled=%s",
             settings.auth_enabled, settings.full_enabled)
    try:
        yield
    finally:
        watcher_global.stop()


app = FastAPI(
    title="Sistema de Envio de Apolices",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
app.add_middleware(PasswordChangeLockdownMiddleware)
app.add_middleware(SocLockdownMiddleware)
app.add_middleware(BackendAccessMiddleware)

app.include_router(status_router.router)
app.include_router(auth_router.router)
app.include_router(usuarios.router)
app.include_router(clientes.router)
app.include_router(autos.router)
app.include_router(tipos_envio.router)
app.include_router(corpos_email.router)
app.include_router(assinaturas.router)
app.include_router(capa.router)
app.include_router(backup.router)
app.include_router(notificacoes.router)
app.include_router(envios.router)
app.include_router(soc.router)


@app.get("/", include_in_schema=False)
def root():
    return {
        "app": "Sistema de Envio de Apolices",
        "versao": "1.1.0",
        "docs": "/docs",
    }
