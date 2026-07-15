from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from pypdf import PdfWriter

from app.services.envio_service import _chave_idempotencia
from app.services.upload_service import save_upload
from app.config import settings


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class UploadTests(unittest.TestCase):
    def test_pdf_valido_e_salvo_em_streaming(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "arquivo.pdf"
            upload = UploadFile(file=io.BytesIO(_pdf_bytes()), filename="arquivo.pdf")
            result = asyncio.run(
                save_upload(
                    upload,
                    destination,
                    kind="pdf",
                    allowed_suffixes={".pdf"},
                )
            )

            self.assertTrue(destination.is_file())
            self.assertEqual(result.size, destination.stat().st_size)
            self.assertEqual(len(result.sha256), 64)

    def test_upload_acima_do_limite_e_rejeitado_sem_residuo(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            settings, "max_upload_mb", 1
        ):
            destination = Path(directory) / "grande.pdf"
            upload = UploadFile(
                file=io.BytesIO(b"%PDF-" + b"x" * (1024 * 1024 + 1)),
                filename="grande.pdf",
            )
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    save_upload(
                        upload,
                        destination,
                        kind="pdf",
                        allowed_suffixes={".pdf"},
                    )
                )

            self.assertEqual(raised.exception.status_code, 413)
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(directory).glob("*.part")), [])


class IdempotencyTests(unittest.TestCase):
    def test_mesmo_conteudo_e_contexto_gera_mesma_chave(self):
        args = {
            "arquivo_sha256": "a" * 64,
            "boleto_sha256": "b" * 64,
            "cliente_id": 10,
            "tipo_envio": "MANUAL",
            "tipo_codigo": "auto",
        }
        self.assertEqual(_chave_idempotencia(**args), _chave_idempotencia(**args))
        self.assertNotEqual(
            _chave_idempotencia(**args),
            _chave_idempotencia(**{**args, "cliente_id": 11}),
        )


if __name__ == "__main__":
    unittest.main()
