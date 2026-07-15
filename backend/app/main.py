"""FastAPI entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse

from .config import settings
from . import APP_VERSION
from .database import init_db, SessionLocal
from .auth import seed_admin
from .services.diretor_service import seed_diretor
from .middleware.backend_access import BackendAccessMiddleware
from .middleware.soc_lockdown import SocLockdownMiddleware
from .middleware.password_change_lockdown import PasswordChangeLockdownMiddleware
from .middleware.security_headers import SecurityHeadersMiddleware
from .spa_static import SPAStaticFiles
from .config import BASE_DIR
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
    webhooks,
)
from .services.full_watcher import watcher_global
from .services.backup_service import aplicar_retencao_automatica


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
    aplicar_retencao_automatica()
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
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=settings.cors_list != ["*"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Backend-Access-Key"],
)
app.add_middleware(PasswordChangeLockdownMiddleware)
app.add_middleware(SocLockdownMiddleware)
app.add_middleware(BackendAccessMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

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
app.include_router(webhooks.router)


@app.get("/", include_in_schema=False)
def root():
    index = BASE_DIR.parent / "frontend" / "dist" / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {
        "app": "Sistema de Envio de Apolices",
        "versao": APP_VERSION,
    }


@app.api_route(
    "/api/{unknown_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
def unknown_api_route(unknown_path: str):
    del unknown_path
    raise HTTPException(status_code=404, detail="Not Found")


frontend_dist = BASE_DIR.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", SPAStaticFiles(directory=str(frontend_dist), html=True), name="frontend")
