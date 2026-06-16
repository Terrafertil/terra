"""Exige chave de acesso antes de qualquer rota da API (exceto rotas públicas mínimas)."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..services.data_crypto_service import backend_access_enabled, verify_backend_access


_PUBLIC_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
)

_PUBLIC_EXACT = {
    "/",
    "/api/status",
    "/api/auth/status",
}


class BackendAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not backend_access_enabled():
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        if path in _PUBLIC_EXACT:
            return await call_next(request)
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)
        if path == "/api/auth/verificar-acesso-backend" and request.method == "POST":
            return await call_next(request)

        if not path.startswith("/api"):
            return await call_next(request)

        key = request.headers.get("X-Backend-Access-Key")
        if not verify_backend_access(key):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Acesso ao backend negado. Informe o cabeçalho X-Backend-Access-Key válido.",
                },
            )
        return await call_next(request)
