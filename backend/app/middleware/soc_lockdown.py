"""Durante modo SOC, só rotas de status e SOC ficam acessíveis."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..database import SessionLocal
from ..services.soc_service import SOC_BLOCK_MSG, is_soc_locked


_ALLOWED_PREFIXES = (
    "/api/status",
    "/api/auth",
    "/api/soc",
)

_PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/")


class SocLockdownMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        db = SessionLocal()
        try:
            locked = is_soc_locked(db)
        finally:
            db.close()

        if not locked:
            return await call_next(request)

        if any(path == p or path.startswith(p + "/") for p in _ALLOWED_PREFIXES):
            return await call_next(request)

        if path.startswith("/api/auth/verificar-acesso-backend"):
            return await call_next(request)

        return JSONResponse(
            status_code=423,
            content={"detail": SOC_BLOCK_MSG},
        )
