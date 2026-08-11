from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services import ocr_service


class OcrTimeoutTests(unittest.TestCase):
    def test_tesseract_recebe_timeout_por_pagina(self):
        pixmap = types.SimpleNamespace(width=1, height=1, samples=b"\x00\x00\x00")
        page = types.SimpleNamespace(get_pixmap=MagicMock(return_value=pixmap))
        document = MagicMock()
        document.__iter__.side_effect = lambda: iter([page])

        fitz = types.ModuleType("fitz")
        fitz.open = MagicMock(return_value=document)
        fitz.Matrix = MagicMock(return_value=object())

        pytesseract = types.ModuleType("pytesseract")
        pytesseract.pytesseract = types.SimpleNamespace(tesseract_cmd="")
        pytesseract.image_to_string = MagicMock(return_value="texto extraido")

        image = types.ModuleType("PIL.Image")
        image.frombytes = MagicMock(return_value=object())
        pil = types.ModuleType("PIL")
        pil.Image = image

        modules = {
            "fitz": fitz,
            "pytesseract": pytesseract,
            "PIL": pil,
            "PIL.Image": image,
        }
        with (
            patch.object(ocr_service, "ocr_disponivel", return_value=True),
            patch.object(ocr_service.settings, "tesseract_cmd", ""),
            patch.object(ocr_service.settings, "ocr_lang", "por"),
            patch.object(ocr_service.settings, "ocr_page_timeout_seconds", 17),
            patch.dict(sys.modules, modules),
        ):
            texto, erro = ocr_service.extrair_texto_ocr(Path("apolice.pdf"))

        self.assertEqual(texto, "texto extraido")
        self.assertIsNone(erro)
        pytesseract.image_to_string.assert_called_once_with(
            image.frombytes.return_value,
            lang="por",
            timeout=17,
        )
        document.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
