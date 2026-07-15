from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.middleware.password_change_lockdown import (
    PasswordChangeLockdownMiddleware,
    _is_public_path as password_public_path,
)
from app.middleware.soc_lockdown import (
    SocLockdownMiddleware,
    _is_public_path as soc_public_path,
)
from app.services.rate_limit_service import RateLimiter
from app.services.data_crypto_service import (
    create_backend_access_cookie_token,
    verify_backend_access,
)
from app.config import settings
from fastapi import HTTPException


def _request(path: str, *, token: str | None = None) -> Request:
    headers = []
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1),
        "scheme": "http",
    }
    return Request(scope)


async def _ok(_request: Request) -> Response:
    return Response("ok", status_code=200)


class PublicPathTests(unittest.TestCase):
    def test_root_is_public_but_api_routes_are_not(self):
        for checker in (password_public_path, soc_public_path):
            self.assertTrue(checker("/"))
            self.assertTrue(checker("/docs"))
            self.assertTrue(checker("/docs/oauth2-redirect"))
            self.assertFalse(checker("/api/clientes"))
            self.assertFalse(checker("/docs-malicioso"))


class LockdownMiddlewareTests(unittest.TestCase):
    def test_soc_blocks_non_allowed_api(self):
        middleware = SocLockdownMiddleware(app=MagicMock())
        with patch(
            "app.middleware.soc_lockdown.SessionLocal"
        ) as session_local, patch(
            "app.middleware.soc_lockdown.is_soc_locked", return_value=True
        ):
            session_local.return_value = MagicMock()
            response = asyncio.run(
                middleware.dispatch(_request("/api/clientes"), _ok)
            )

        self.assertEqual(response.status_code, 423)

    def test_soc_allows_deactivation_route(self):
        middleware = SocLockdownMiddleware(app=MagicMock())
        with patch(
            "app.middleware.soc_lockdown.SessionLocal"
        ) as session_local, patch(
            "app.middleware.soc_lockdown.is_soc_locked", return_value=True
        ):
            session_local.return_value = MagicMock()
            response = asyncio.run(
                middleware.dispatch(_request("/api/soc/desativar"), _ok)
            )

        self.assertEqual(response.status_code, 200)

    def test_password_change_blocks_authenticated_user(self):
        middleware = PasswordChangeLockdownMiddleware(app=MagicMock())
        query = MagicMock()
        query.filter.return_value.first.return_value = SimpleNamespace(
            ativo=True,
            must_change_password=True,
        )
        db = MagicMock()
        db.query.return_value = query

        with patch.object(
            __import__(
                "app.middleware.password_change_lockdown",
                fromlist=["settings"],
            ).settings,
            "auth_enabled",
            True,
        ), patch(
            "app.middleware.password_change_lockdown.SessionLocal",
            return_value=db,
        ), patch(
            "app.middleware.password_change_lockdown._decodar",
            return_value={"sub": "teste"},
        ):
            response = asyncio.run(
                middleware.dispatch(
                    _request("/api/clientes", token="token-valido"),
                    _ok,
                )
            )

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 403)


class AuthenticationHardeningTests(unittest.TestCase):
    def test_rate_limit_bloqueia_e_pode_ser_liberado(self):
        limiter = RateLimiter()
        limiter.check("ip", limit=2, window_seconds=60)
        limiter.check("ip", limit=2, window_seconds=60)
        with self.assertRaises(HTTPException) as raised:
            limiter.check("ip", limit=2, window_seconds=60)
        self.assertEqual(raised.exception.status_code, 429)
        limiter.clear("ip")
        limiter.check("ip", limit=2, window_seconds=60)

    def test_cookie_do_backend_nao_contem_chave_e_e_validado(self):
        with patch.object(settings, "backend_access_enabled", True), patch.object(
            settings, "backend_access_key", "k" * 64
        ), patch.object(settings, "secret_key", "s" * 64):
            token = create_backend_access_cookie_token()
            self.assertNotIn("k" * 64, token)
            self.assertTrue(verify_backend_access(token))


if __name__ == "__main__":
    unittest.main()
