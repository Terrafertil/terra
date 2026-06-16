"""OCR opcional para PDFs sem camada de texto (requer Tesseract no sistema)."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from ..config import settings

log = logging.getLogger(__name__)

_ocr_disponivel: bool | None = None


def ocr_disponivel() -> bool:
    global _ocr_disponivel
    if _ocr_disponivel is not None:
        return _ocr_disponivel
    if not settings.ocr_enabled:
        _ocr_disponivel = False
        return False
    try:
        import pytesseract
        import fitz  # noqa: F401
        from PIL import Image  # noqa: F401

        cmd = (settings.tesseract_cmd or "").strip()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        elif not shutil.which("tesseract"):
            log.warning("Tesseract não encontrado no PATH; OCR desativado.")
            _ocr_disponivel = False
            return False
        _ocr_disponivel = True
    except ImportError:
        log.warning("Pacotes OCR não instalados (pymupdf, pytesseract, Pillow).")
        _ocr_disponivel = False
    return _ocr_disponivel


def extrair_texto_ocr(caminho: Path, *, max_paginas: int | None = None) -> tuple[str, str | None]:
    """Retorna (texto, erro)."""
    if not ocr_disponivel():
        return "", "OCR não disponível (instale Tesseract e pacotes Python)."

    import fitz
    import pytesseract
    from PIL import Image

    cmd = (settings.tesseract_cmd or "").strip()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd

    limite = max_paginas if max_paginas is not None else settings.ocr_max_pages
    limite = max(1, min(20, int(limite)))

    partes: list[str] = []
    try:
        doc = fitz.open(str(caminho))
        try:
            for i, page in enumerate(doc):
                if i >= limite:
                    break
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                txt = pytesseract.image_to_string(img, lang=settings.ocr_lang)
                if txt and txt.strip():
                    partes.append(txt)
        finally:
            doc.close()
    except Exception as e:
        return "", f"Erro no OCR: {e}"

    texto = "\n".join(partes).strip()
    if not texto:
        return "", "OCR não extraiu texto legível."
    return texto, None
