from __future__ import annotations

import unittest

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, schemas
from app.database import Base
from app.routers import assuntos_email, tipos_envio


class AssuntosEmailTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, future=True)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_crud_e_exclusao_protegida_quando_vinculado(self):
        criado = assuntos_email.criar(
            schemas.AssuntoEmailCreate(
                nome="Auto",
                descricao="Envio de auto",
                assunto="Apolice Auto {numero_apolice}",
            ),
            db=self.db,
        )
        self.assertEqual(criado.nome, "Auto")
        self.assertEqual(assuntos_email.listar(True, db=self.db), [criado])

        tipo = models.TipoEnvio(
            codigo="auto",
            nome="Auto",
            assunto_email_id=criado.id,
        )
        self.db.add(tipo)
        self.db.commit()
        self.db.refresh(tipo)
        self.assertEqual(
            tipos_envio._to_out(tipo)["assunto_email_id"], criado.id
        )
        with self.assertRaises(HTTPException) as invalido:
            tipos_envio.atualizar(
                tipo.id,
                schemas.TipoEnvioUpdate(assunto_email_id=999999),
                db=self.db,
            )
        self.assertEqual(invalido.exception.status_code, 400)
        with self.assertRaises(HTTPException) as contexto:
            assuntos_email.remover(criado.id, db=self.db)
        self.assertEqual(contexto.exception.status_code, 409)

        tipo.assunto_email_id = None
        self.db.commit()
        assuntos_email.remover(criado.id, db=self.db)
        self.assertIsNone(self.db.get(models.AssuntoEmail, criado.id))

    def test_rejeita_quebra_de_linha_no_assunto(self):
        with self.assertRaises(ValidationError):
            schemas.AssuntoEmailCreate(
                nome="Invalido",
                assunto="Assunto valido\r\nBcc: terceiro@example.com",
            )


if __name__ == "__main__":
    unittest.main()
