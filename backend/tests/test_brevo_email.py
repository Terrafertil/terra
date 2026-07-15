from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.services import email_service


class BrevoSettingsTests(unittest.TestCase):
    def _settings(self, **env: str) -> Settings:
        with patch.dict(os.environ, env, clear=True):
            return Settings(_env_file=None)

    def test_brevo_is_the_default_provider(self):
        config = self._settings()

        self.assertTrue(config.use_brevo)
        self.assertEqual(config.email_provider, "brevo")
        self.assertEqual(config.smtp_host, "smtp-relay.brevo.com")
        self.assertFalse(config.email_configured)

    def test_legacy_ses_host_is_replaced(self):
        config = self._settings(
            USE_BREVO="true",
            SMTP_HOST="email-smtp.sa-east-1.amazonaws.com",
        )

        self.assertEqual(config.smtp_host, "smtp-relay.brevo.com")

    def test_brevo_aliases_complete_the_configuration(self):
        config = self._settings(
            BREVO_SMTP_LOGIN="login@example.com",
            BREVO_SMTP_KEY="smtp-key",
            BREVO_SENDER_EMAIL="sender@example.com",
        )

        self.assertEqual(config.smtp_user, "login@example.com")
        self.assertEqual(config.smtp_password, "smtp-key")
        self.assertEqual(config.smtp_from_email, "sender@example.com")
        self.assertTrue(config.email_configured)

    def test_port_465_uses_implicit_tls(self):
        config = self._settings(SMTP_PORT="465")

        self.assertTrue(config.smtp_use_ssl)
        self.assertFalse(config.smtp_use_tls)


class BrevoEmailTests(unittest.TestCase):
    def test_apolice_e_boleto_mantem_nomes_distintos(self):
        smtp_context = MagicMock()
        connection = smtp_context.return_value.__enter__.return_value
        with tempfile.TemporaryDirectory() as directory:
            apolice = Path(directory) / "a.pdf"
            boleto = Path(directory) / "b.pdf"
            apolice.write_bytes(b"%PDF-1.4\napolice")
            boleto.write_bytes(b"%PDF-1.4\nboleto")
            with (
                patch.object(email_service.settings, "smtp_host", "smtp-relay.brevo.com"),
                patch.object(email_service.settings, "smtp_port", 587),
                patch.object(email_service.settings, "smtp_use_tls", True),
                patch.object(email_service.settings, "smtp_use_ssl", False),
                patch.object(email_service.settings, "smtp_user", "login@example.com"),
                patch.object(email_service.settings, "smtp_password", "smtp-key"),
                patch.object(email_service.settings, "smtp_from_email", "sender@example.com"),
                patch.object(email_service.smtplib, "SMTP", smtp_context),
            ):
                email_service.enviar_email(
                    destinatario="client@example.com",
                    assunto="Documentos",
                    corpo_html="<p>Documentos</p>",
                    anexos=[apolice, boleto],
                    nomes_anexos=["apolice.pdf", "boleto.pdf"],
                )

        message = connection.send_message.call_args.args[0]
        self.assertEqual(
            [part.get_filename() for part in message.iter_attachments()],
            ["apolice.pdf", "boleto.pdf"],
        )

    def test_missing_credentials_fail_before_network_access(self):
        with (
            patch.object(email_service.settings, "use_brevo", True),
            patch.object(email_service.settings, "smtp_user", ""),
            patch.object(email_service.settings, "smtp_password", ""),
            patch.object(email_service.settings, "smtp_from_email", "sender@example.com"),
            patch.object(email_service.smtplib, "SMTP") as smtp,
        ):
            with self.assertRaisesRegex(RuntimeError, "Brevo SMTP não configurada"):
                email_service.enviar_email(
                    destinatario="client@example.com",
                    assunto="Teste",
                    corpo_html="<p>Teste</p>",
                )

        smtp.assert_not_called()

    def test_pdf_is_sent_through_brevo_with_starttls(self):
        smtp_context = MagicMock()
        smtp_connection = smtp_context.return_value.__enter__.return_value

        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "apolice.pdf"
            pdf.write_bytes(b"%PDF-1.4\n% test")

            with (
                patch.object(email_service.settings, "use_brevo", True),
                patch.object(email_service.settings, "smtp_host", "smtp-relay.brevo.com"),
                patch.object(email_service.settings, "smtp_port", 587),
                patch.object(email_service.settings, "smtp_use_tls", True),
                patch.object(email_service.settings, "smtp_use_ssl", False),
                patch.object(email_service.settings, "smtp_user", "login@example.com"),
                patch.object(email_service.settings, "smtp_password", "smtp-key"),
                patch.object(email_service.settings, "smtp_from_email", "sender@example.com"),
                patch.object(email_service.smtplib, "SMTP", smtp_context),
            ):
                email_service.enviar_email(
                    destinatario="client@example.com",
                    assunto="Apólice",
                    corpo_html="<p>Segue a apólice</p>",
                    anexos=[pdf],
                )

        smtp_context.assert_called_once_with(
            "smtp-relay.brevo.com", 587, timeout=30
        )
        smtp_connection.starttls.assert_called_once()
        smtp_connection.login.assert_called_once_with("login@example.com", "smtp-key")
        sent_message = smtp_connection.send_message.call_args.args[0]
        attachments = list(sent_message.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "apolice.pdf")

    def test_message_over_brevo_limit_fails_before_network_access(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "apolice-grande.pdf"
            pdf.write_bytes(b"x" * 900_000)

            with (
                patch.object(email_service.settings, "use_brevo", True),
                patch.object(email_service.settings, "brevo_max_message_mb", 1),
                patch.object(email_service.settings, "smtp_user", "login@example.com"),
                patch.object(email_service.settings, "smtp_password", "smtp-key"),
                patch.object(email_service.settings, "smtp_from_email", "sender@example.com"),
                patch.object(email_service.smtplib, "SMTP") as smtp,
            ):
                with self.assertRaisesRegex(ValueError, "excede o limite"):
                    email_service.enviar_email(
                        destinatario="client@example.com",
                        assunto="Apólice",
                        corpo_html="<p>Segue a apólice</p>",
                        anexos=[pdf],
                    )

        smtp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
