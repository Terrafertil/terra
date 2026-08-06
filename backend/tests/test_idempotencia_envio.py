"""Idempotência: não reenvia sucesso; permite retry após erro."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import envio_service


class IdempotenciaEnvioTests(unittest.TestCase):
    def test_enviado_bloqueia_duplicata(self):
        db = MagicMock()
        envio = SimpleNamespace(
            id=1,
            status="enviado",
            criado_em=datetime.utcnow(),
            idempotency_key="k",
            erro_msg=None,
        )
        db.query.return_value.filter.return_value.first.return_value = envio
        self.assertIs(envio_service._envio_existente_idempotente(db, "k"), envio)

    def test_erro_liberta_chave_para_retry(self):
        db = MagicMock()
        envio = SimpleNamespace(
            id=7,
            status="erro",
            criado_em=datetime.utcnow() - timedelta(minutes=10),
            idempotency_key="k",
            erro_msg="smtp fail",
        )
        db.query.return_value.filter.return_value.first.return_value = envio
        self.assertIsNone(envio_service._envio_existente_idempotente(db, "k"))
        self.assertTrue(str(envio.idempotency_key).startswith("k:retired:"))
        db.commit.assert_called()

    def test_pendente_recente_nao_duplica(self):
        db = MagicMock()
        envio = SimpleNamespace(
            id=2,
            status="pendente",
            criado_em=datetime.utcnow(),
            idempotency_key="k",
            erro_msg=None,
        )
        db.query.return_value.filter.return_value.first.return_value = envio
        self.assertIs(envio_service._envio_existente_idempotente(db, "k"), envio)


if __name__ == "__main__":
    unittest.main()
