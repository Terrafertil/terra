"""Exige chave de acesso antes de qualquer rota da API (exceto rotas públicas mínimas)."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import settings
from ..services.data_crypto_service import backend_access_enabled, verify_backend_access


_PUBLIC_PREFIXES = (
    "/docs",
    "/redoc",
    "/api/auth",
)

_PUBLIC_EXACT = {
    "/",
    "/api/health",
    "/api/webhooks/brevo",
    "/api/auth/status",
    "/openapi.json",
}


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_EXACT or any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in _PUBLIC_PREFIXES
    )


class BackendAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not backend_access_enabled():
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        if _is_public_path(path):
            return await call_next(request)
        if path == "/api/auth/verificar-acesso-backend" and request.method == "POST":
            return await call_next(request)

        if not path.startswith("/api"):
            return await call_next(request)

        key = request.headers.get("X-Backend-Access-Key") or request.cookies.get(
            settings.backend_access_cookie_name
        )
        if not verify_backend_access(key):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Acesso ao backend negado. Informe o cabeçalho X-Backend-Access-Key válido.",
                },
            )
        return await call_next(request)
