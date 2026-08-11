from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app import models
from app.database import Base
from app.routers import webhooks
from app.services import envio_service


TOKEN = "token-de-webhook-brevo-com-mais-de-32-caracteres"


def _epoch(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp())


def _request(
    payload: object | None = None,
    *,
    token: str | None = TOKEN,
    authorization_scheme: str = "Bearer",
    raw: bytes | None = None,
    content_length: str | None = None,
) -> Request:
    body = (
        raw
        if raw is not None
        else json.dumps({} if payload is None else payload).encode("utf-8")
    )
    headers: list[tuple[bytes, bytes]] = []
    if token is not None:
        headers.append(
            (
                b"authorization",
                f"{authorization_scheme} {token}".encode("ascii"),
            )
        )
    if content_length is None:
        content_length = str(len(body))
    headers.append((b"content-length", content_length.encode("ascii")))

    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/webhooks/brevo",
        "raw_path": b"/api/webhooks/brevo",
        "query_string": b"",
        "headers": headers,
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
    }
    return Request(scope, receive)


class BrevoWebhookTests(unittest.TestCase):
    """Cada teste usa um SQLite em memória; o banco configurado nunca é aberto."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(models.Cliente(id=1, nome="Cliente", email="cliente@example.com"))
        self.db.commit()
        self.token_patch = patch.object(webhooks.settings, "brevo_webhook_token", TOKEN)
        self.limit_patch = patch.object(webhooks.limiter, "check")
        self.token_patch.start()
        self.limit_patch.start()

    def tearDown(self):
        self.limit_patch.stop()
        self.token_patch.stop()
        self.db.close()
        self.engine.dispose()

    def _envio(
        self,
        envio_id: int,
        *,
        provider_message_id: str | None = None,
        status: str = "enviado",
        delivery_status: str | None = "accepted",
        delivery_updated_at: datetime | None = None,
        erro_msg: str | None = None,
    ) -> models.Envio:
        envio = models.Envio(
            id=envio_id,
            cliente_id=1,
            tipo_envio="MANUAL",
            status=status,
            provider_message_id=provider_message_id,
            delivery_status=delivery_status,
            delivery_updated_at=delivery_updated_at,
            erro_msg=erro_msg,
            caminho_backup=f"backup/{envio_id}.pdf",
        )
        self.db.add(envio)
        self.db.commit()
        return envio

    def _call(self, payload: object, **request_kwargs):
        return asyncio.run(
            webhooks.webhook_brevo(
                _request(payload, **request_kwargs),
                self.db,
            )
        )

    def test_requires_a_configured_secret(self):
        with patch.object(webhooks.settings, "brevo_webhook_token", "curto"):
            with self.assertRaises(HTTPException) as raised:
                self._call({"event": "delivered"})

        self.assertEqual(raised.exception.status_code, 503)

    def test_rejects_missing_wrong_or_non_bearer_credentials(self):
        requests = (
            _request({}, token=None),
            _request({}, token="token-incorreto"),
            _request({}, token=TOKEN, authorization_scheme="Basic"),
        )
        for request in requests:
            with self.subTest(authorization=request.headers.get("Authorization")):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(webhooks.webhook_brevo(request, self.db))
                self.assertEqual(raised.exception.status_code, 401)

    def test_accepts_bearer_token_and_returns_unmatched_safely(self):
        result = self._call({"event": "delivered", "message-id": "desconhecido"})

        self.assertEqual(result, {"ok": True, "matched": False})

    def test_rejects_invalid_json_non_object_and_oversized_payloads(self):
        cases = (
            (_request(raw=b"{"), 400),
            (_request([]), 400),
            (_request({}, content_length=str(64 * 1024 + 1)), 413),
            (_request(raw=b"x" * (64 * 1024 + 1), content_length="0"), 413),
        )
        for request, expected_status in cases:
            with self.subTest(expected_status=expected_status, size=len(request.scope["headers"])):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(webhooks.webhook_brevo(request, self.db))
                self.assertEqual(raised.exception.status_code, expected_status)

    def test_matches_case_insensitive_custom_tracking(self):
        envio = self._envio(11, provider_message_id="<local@id>")

        result = self._call(
            {
                "event": "delivered",
                "x-mailin-CUSTOM": "origem=full; ENVIO_ID = 11",
                "message-id": "<id-interno-brevo>",
                "ts_event": _epoch(2026, 8, 11),
            }
        )

        self.assertTrue(result["matched"])
        self.assertEqual(envio.delivery_status, "delivered")
        # O webhook não pode trocar o ID da tentativa atual por um ID atrasado.
        self.assertEqual(envio.provider_message_id, "<local@id>")

    def test_falls_back_to_message_id_with_or_without_angle_brackets(self):
        envio = self._envio(12, provider_message_id="<provider@example.com>")

        result = self._call(
            {
                "event": "delivered",
                "X-Mailin-custom": "envio_id:99999",
                "message-id": "provider@example.com",
                "ts_event": _epoch(2026, 8, 11),
            }
        )

        self.assertEqual(result["envio_id"], 12)
        self.assertEqual(envio.delivery_status, "delivered")

    def test_refuses_conflicting_tracking_and_message_identifiers(self):
        first = self._envio(13, provider_message_id="<first@example.com>")
        second = self._envio(14, provider_message_id="<second@example.com>")

        result = self._call(
            {
                "event": "delivered",
                "X-Mailin-custom": "envio_id:13",
                "message-id": "second@example.com",
                "ts_event": _epoch(2026, 8, 11),
            }
        )

        self.assertEqual(result, {"ok": True, "matched": False})
        self.assertEqual(first.delivery_status, "accepted")
        self.assertEqual(second.delivery_status, "accepted")

    def test_unknown_event_does_not_mutate_a_matched_record(self):
        envio = self._envio(17, provider_message_id=None)

        result = self._call(
            {
                "event": "future_event_not_supported",
                "X-Mailin-custom": "envio_id:17",
                "message-id": "must-not-be-bound@example.com",
                "ts_event": _epoch(2026, 8, 11),
            }
        )

        self.assertTrue(result["matched"])
        self.assertEqual(envio.status, "enviado")
        self.assertEqual(envio.delivery_status, "accepted")
        self.assertIsNone(envio.provider_message_id)
        self.assertIsNone(envio.delivery_updated_at)

    def test_delayed_event_from_old_attempt_never_changes_new_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "apolice.pdf"
            pdf.write_bytes(b"%PDF-1.4\nconteudo")
            old_attempt = self._envio(
                15,
                provider_message_id="<old-attempt@example.com>",
                status="erro",
                delivery_status="soft_bounce",
                delivery_updated_at=datetime(2026, 8, 11, 10),
                erro_msg="falha da tentativa original",
            )
            old_attempt.caminho_backup = str(pdf)
            self.db.commit()

            with (
                patch.object(
                    envio_service.soc_service, "is_soc_locked", return_value=False
                ),
                patch.object(envio_service, "_resolver_corpo_email", return_value=None),
                patch.object(envio_service, "_resolver_assinatura", return_value=None),
                patch.object(
                    envio_service.email_service,
                    "formatar_assunto",
                    return_value="Assunto",
                ),
                patch.object(
                    envio_service.email_service,
                    "renderizar_template",
                    return_value="<p>Mensagem</p>",
                ),
                patch.object(
                    envio_service.email_service,
                    "enviar_email",
                    return_value="<new-attempt@example.com>",
                ),
            ):
                new_attempt = envio_service.reenviar_envio(self.db, old_attempt.id)

        self.assertNotEqual(new_attempt.id, old_attempt.id)
        self.assertEqual(new_attempt.reenvio_de_id, old_attempt.id)
        self.assertEqual(new_attempt.delivery_status, "accepted")

        result = self._call(
            {
                "event": "blocked",
                "X-Mailin-custom": "envio_id:15",
                "message-id": "old-attempt@example.com",
                "reason": "evento atrasado da primeira tentativa",
            }
        )

        self.assertEqual(result["envio_id"], old_attempt.id)
        self.assertEqual(old_attempt.delivery_status, "blocked")
        self.assertEqual(new_attempt.status, "enviado")
        self.assertEqual(new_attempt.delivery_status, "accepted")
        self.assertEqual(
            new_attempt.provider_message_id,
            "<new-attempt@example.com>",
        )

    def test_delivered_consolidates_success_and_clears_previous_error(self):
        previous = datetime(2026, 8, 11, 10)
        envio = self._envio(
            20,
            status="erro",
            delivery_status="soft_bounce",
            delivery_updated_at=previous,
            erro_msg="falha anterior",
        )

        self._call(
            {
                "event": "delivered",
                "X-Mailin-custom": "envio_id:20",
                "ts_event": _epoch(2026, 8, 11, 12),
            }
        )

        self.assertEqual(envio.status, "enviado")
        self.assertEqual(envio.delivery_status, "delivered")
        self.assertIsNone(envio.erro_msg)
        self.assertEqual(envio.delivery_updated_at, datetime(2026, 8, 11, 12))

    def test_delivered_wins_over_conflicting_failure_in_the_same_second(self):
        instant = datetime(2026, 8, 11, 12)
        envio = self._envio(
            21,
            status="erro",
            delivery_status="hard_bounce",
            delivery_updated_at=instant,
            erro_msg="falha anterior",
        )

        self._call(
            {
                "event": "delivered",
                "X-Mailin-custom": "envio_id:21",
                "ts_event": _epoch(2026, 8, 11, 12),
            }
        )

        self.assertEqual(envio.status, "enviado")
        self.assertEqual(envio.delivery_status, "delivered")
        self.assertIsNone(envio.erro_msg)

    def test_all_delivery_failures_become_errors_with_clear_reason(self):
        cases = {
            "soft_bounce": ("soft_bounce", "falha temporária"),
            "hard_bounce": ("hard_bounce", "falha permanente"),
            "blocked": ("blocked", "entrega bloqueada"),
            "invalid_email": ("invalid_email", "e-mail inválido"),
            "error": ("error", "erro de entrega"),
            "spam": ("spam", "denunciada como spam"),
        }
        for offset, (incoming, (canonical, expected_text)) in enumerate(
            cases.items(), start=30
        ):
            with self.subTest(event=incoming):
                envio = self._envio(offset)
                self._call(
                    {
                        "event": incoming,
                        "X-Mailin-custom": f"envio_id:{offset}",
                        "ts_event": _epoch(2026, 8, 11),
                        "reason": "Caixa do destinatário recusou a mensagem",
                    }
                )

                self.assertEqual(envio.status, "erro")
                self.assertEqual(envio.delivery_status, canonical)
                self.assertIn(expected_text, envio.erro_msg or "")
                self.assertIn("Caixa do destinatário recusou", envio.erro_msg or "")
                if incoming == "spam":
                    self.assertIn("reenvio está bloqueado", envio.erro_msg or "")
                    self.assertNotIn("tente reenviar", envio.erro_msg or "")
                    self.assertFalse(envio_service.envio_pode_reenviar(envio))
                else:
                    self.assertIn("tente reenviar", envio.erro_msg or "")
                    self.assertTrue(envio_service.envio_pode_reenviar(envio))

    def test_accepts_event_name_variants_used_by_brevo_api(self):
        cases = {
            "softBounce": "soft_bounce",
            "hardBounce": "hard_bounce",
            "invalid": "invalid_email",
            "complaint": "spam",
        }
        for offset, (incoming, expected) in enumerate(cases.items(), start=40):
            with self.subTest(event=incoming):
                envio = self._envio(offset)
                self._call(
                    {
                        "event": incoming,
                        "X-Mailin-custom": f"envio_id:{offset}",
                        "ts_event": _epoch(2026, 8, 11),
                    }
                )
                self.assertEqual(envio.status, "erro")
                self.assertEqual(envio.delivery_status, expected)

    def test_unsubscribed_is_recorded_as_a_non_retryable_consent_failure(self):
        envio = self._envio(48)

        self._call(
            {
                "event": "unsubscribed",
                "X-Mailin-custom": "envio_id:48",
                "ts_event": _epoch(2026, 8, 11),
            }
        )

        self.assertEqual(envio.status, "erro")
        self.assertEqual(envio.delivery_status, "unsubscribed")
        self.assertIn("reenvio está bloqueado", envio.erro_msg or "")
        self.assertNotIn("tente reenviar", envio.erro_msg or "")
        self.assertFalse(envio_service.envio_pode_reenviar(envio))

        self._call(
            {
                "event": "delivered",
                "X-Mailin-custom": "envio_id:48",
                "ts_event": _epoch(2026, 8, 11, 13),
            }
        )
        self.assertEqual(envio.status, "erro")
        self.assertEqual(envio.delivery_status, "unsubscribed")
        self.assertFalse(envio_service.envio_pode_reenviar(envio))

    def test_repeated_spam_keeps_reason_and_never_reopens_delivery(self):
        envio = self._envio(47)
        self._call(
            {
                "event": "spam",
                "X-Mailin-custom": "envio_id:47",
                "ts_event": _epoch(2026, 8, 11, 11),
                "reason": "Reclamação confirmada pelo provedor",
            }
        )
        original_message = envio.erro_msg

        self._call(
            {
                "event": "spam",
                "X-Mailin-custom": "envio_id:47",
                "ts_event": _epoch(2026, 8, 11, 12),
            }
        )
        self._call(
            {
                "event": "delivered",
                "X-Mailin-custom": "envio_id:47",
                "ts_event": _epoch(2026, 8, 11, 13),
            }
        )

        self.assertEqual(envio.erro_msg, original_message)
        self.assertIn("Reclamação confirmada", envio.erro_msg or "")
        self.assertEqual(envio.delivery_status, "spam")
        self.assertFalse(envio_service.envio_pode_reenviar(envio))

    def test_failure_without_new_reason_preserves_useful_error_details(self):
        original = "Brevo informou falha permanente. Motivo: caixa inexistente."
        envio = self._envio(
            49,
            status="erro",
            delivery_status="hard_bounce",
            delivery_updated_at=datetime(2026, 8, 11, 10),
            erro_msg=original,
        )

        self._call(
            {
                "event": "hard_bounce",
                "X-Mailin-custom": "envio_id:49",
                "ts_event": _epoch(2026, 8, 11, 11),
            }
        )
        self.assertEqual(envio.erro_msg, original)

        self._call(
            {
                "event": "blocked",
                "X-Mailin-custom": "envio_id:49",
                "ts_event": _epoch(2026, 8, 11, 12),
            }
        )
        self.assertIn("entrega bloqueada", envio.erro_msg or "")
        self.assertIn("caixa inexistente", envio.erro_msg or "")

    def test_deferred_is_transient_and_cannot_overwrite_terminal_state(self):
        accepted = self._envio(
            50,
            delivery_updated_at=datetime(2026, 8, 11, 10),
        )
        self._call(
            {
                "event": "deferred",
                "X-Mailin-custom": "envio_id:50",
                "ts_event": _epoch(2026, 8, 11, 11),
                "reason": "timeout temporário",
            }
        )
        self.assertEqual(accepted.status, "enviado")
        self.assertEqual(accepted.delivery_status, "deferred")
        self.assertIsNone(accepted.erro_msg)

        delivered = self._envio(
            51,
            delivery_status="delivered",
            delivery_updated_at=datetime(2026, 8, 11, 11),
        )
        self._call(
            {
                "event": "deferred",
                "X-Mailin-custom": "envio_id:51",
                "ts_event": _epoch(2026, 8, 11, 12),
            }
        )
        self.assertEqual(delivered.delivery_status, "delivered")
        self.assertEqual(delivered.delivery_updated_at, datetime(2026, 8, 11, 11))

    def test_event_time_and_semantic_precedence_prevent_regressions(self):
        envio = self._envio(
            60,
            delivery_status="delivered",
            delivery_updated_at=datetime(2026, 8, 11, 12),
        )

        # Falha atrasada e abertura posterior não apagam a entrega consolidada.
        self._call(
            {
                "event": "hard_bounce",
                "X-Mailin-custom": "envio_id:60",
                "ts_event": _epoch(2026, 8, 11, 11),
            }
        )
        self._call(
            {
                "event": "opened",
                "X-Mailin-custom": "envio_id:60",
                "ts_event": _epoch(2026, 8, 11, 13),
            }
        )
        self.assertEqual(envio.status, "enviado")
        self.assertEqual(envio.delivery_status, "delivered")

        # Uma rejeição realmente posterior deve abrir reenvio/ajuste.
        self._call(
            {
                "event": "blocked",
                "X-Mailin-custom": "envio_id:60",
                "ts_event": _epoch(2026, 8, 11, 14),
            }
        )
        self.assertEqual(envio.status, "erro")
        self.assertEqual(envio.delivery_status, "blocked")

        # Se a Brevo entregar após uma falha temporária/terminal anterior, sucesso vence.
        self._call(
            {
                "event": "delivered",
                "X-Mailin-custom": "envio_id:60",
                "ts_event": _epoch(2026, 8, 11, 15),
            }
        )
        self.assertEqual(envio.status, "enviado")
        self.assertEqual(envio.delivery_status, "delivered")
        self.assertIsNone(envio.erro_msg)

    def test_ts_epoch_milliseconds_is_stored_as_utc(self):
        envio = self._envio(70, delivery_updated_at=None)
        timestamp = _epoch(2026, 8, 11, 16)

        self._call(
            {
                "event": "delivered",
                "X-Mailin-custom": "envio_id:70",
                "ts_epoch": timestamp * 1000,
            }
        )

        self.assertEqual(envio.delivery_updated_at, datetime(2026, 8, 11, 16))


if __name__ == "__main__":
    unittest.main()
