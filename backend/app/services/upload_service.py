"""Upload em streaming com limite, validaÃ§Ã£o de conteÃºdo e escrita atÃ´mica."""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from ..config import settings


_CHUNK_SIZE = 1024 * 1024
_IMAGE_FORMATS = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".gif": "GIF",
    ".webp": "WEBP",
}


@dataclass(frozen=True)
class SavedUpload:
    path: Path
    size: int
    sha256: str


def _validate_pdf(path: Path) -> None:
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise HTTPException(400, "O arquivo enviado nÃ£o possui assinatura de PDF vÃ¡lida.")
    try:
        reader = PdfReader(str(path), strict=False)
        if not reader.is_encrypted and len(reader.pages) > settings.max_pdf_pages:
            raise HTTPException(
                413,
                f"PDF excede o limite de {settings.max_pdf_pages} pÃ¡ginas.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"PDF invÃ¡lido ou corrompido: {exc}") from exc


def _validate_image(path: Path, suffix: str) -> None:
    try:
        with Image.open(path) as image:
            if image.format != _IMAGE_FORMATS[suffix]:
                raise HTTPException(400, "A extensÃ£o da imagem nÃ£o corresponde ao conteÃºdo.")
            width, height = image.size
            if width * height > 20_000_000:
                raise HTTPException(413, "Imagem excede o limite de 20 megapixels.")
            image.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(400, "Imagem invÃ¡lida ou corrompida.") from exc


def validate_existing_pdf(path: Path) -> None:
    max_bytes = max(1, settings.max_upload_mb) * 1024 * 1024
    if not path.is_file() or path.stat().st_size == 0:
        raise HTTPException(400, "PDF inexistente ou vazio.")
    if path.stat().st_size > max_bytes:
        raise HTTPException(413, f"PDF excede o limite de {settings.max_upload_mb} MB.")
    _validate_pdf(path)


async def save_upload(
    upload: UploadFile,
    destination: Path,
    *,
    kind: str,
    allowed_suffixes: set[str],
) -> SavedUpload:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in allowed_suffixes:
        allowed = ", ".join(sorted(allowed_suffixes))
        raise HTTPException(400, f"ExtensÃ£o nÃ£o permitida. Use: {allowed}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
    max_bytes = max(1, settings.max_upload_mb) * 1024 * 1024
    total = 0
    digest = hashlib.sha256()
    try:
        with temp.open("xb") as handle:
            while chunk := await upload.read(_CHUNK_SIZE):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        413,
                        f"Arquivo excede o limite de {settings.max_upload_mb} MB.",
                    )
                digest.update(chunk)
                handle.write(chunk)
        if total == 0:
            raise HTTPException(400, "Arquivo vazio.")
        if kind == "pdf":
            _validate_pdf(temp)
        elif kind == "image":
            _validate_image(temp, suffix)
        else:
            raise ValueError(f"Tipo de upload desconhecido: {kind}")
        os.replace(temp, destination)
        return SavedUpload(path=destination, size=total, sha256=digest.hexdigest())
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
