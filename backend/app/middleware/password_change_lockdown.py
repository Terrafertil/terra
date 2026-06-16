"""Bloqueia a API até o utilizador definir uma senha forte (primeiro acesso)."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import settings
from ..database import SessionLocal
from ..auth import _decodar
from .. import models

PASSWORD_CHANGE_CODE = "password_change_required"
PASSWORD_CHANGE_MSG = (
    "É obrigatório alterar a senha antes de continuar. "
    "Use o ecrã de troca de senha com a senha atual."
)

_ALLOWED_PREFIXES = (
    "/api/auth/login",
    "/api/auth/status",
    "/api/auth/me",
    "/api/auth/trocar-senha",
    "/api/auth/recuperar-diretor",
    "/api/auth/verificar-acesso-backend",
)

_PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/")


class PasswordChangeLockdownMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.auth_enabled:
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)
        if any(path == p or path.startswith(p + "/") for p in _ALLOWED_PREFIXES):
            return await call_next(request)
        if not path.startswith("/api"):
            return await call_next(request)

        auth = request.headers.get("Authorization") or ""
        if not auth.lower().startswith("bearer "):
            return await call_next(request)

        token = auth.split(" ", 1)[1].strip()
        if not token:
            return await call_next(request)

        from fastapi import HTTPException

        try:
            data = _decodar(token)
        except HTTPException:
            return await call_next(request)

        username = data.get("sub")
        if not username:
            return await call_next(request)

        db = SessionLocal()
        try:
            user = (
                db.query(models.Usuario)
                .filter(models.Usuario.username == username)
                .first()
            )
            if user and user.ativo and user.must_change_password:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": PASSWORD_CHANGE_MSG,
                        "code": PASSWORD_CHANGE_CODE,
                    },
                )
        finally:
            db.close()

        return await call_next(request)
