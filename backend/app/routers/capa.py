"""Compatibilidade com a antiga rota de capa global.

Novas telas usam ``/api/capas``. Um upload legado e importado para a biblioteca,
mas nunca passa a valer automaticamente para todos os PDFs.
"""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pypdf import PdfReader
from sqlalchemy.orm import Session

from ..config import settings
from .. import schemas
from ..auth import require_user, require_admin
from ..database import get_db
from ..services import capa_service
from ..services.upload_service import save_upload


router = APIRouter(prefix="/api/capa", tags=["capa"])


def _caminho_capa() -> Path:
    return settings.data_path(settings.capa_folder) / settings.capa_arquivo_padrao


def _info_atual() -> schemas.CapaInfoOut:
    p = _caminho_capa()
    if not p.is_file():
        return schemas.CapaInfoOut(
            existe=False,
            nome=settings.capa_arquivo_padrao,
            caminho=str(p),
        )
    paginas = 0
    try:
        r = PdfReader(str(p), strict=False)
        paginas = len(r.pages)
    except Exception:
        paginas = 0
    return schemas.CapaInfoOut(
        existe=True,
        nome=p.name,
        caminho=str(p),
        tamanho_bytes=p.stat().st_size,
        paginas=paginas,
        atualizado_em=datetime.fromtimestamp(p.stat().st_mtime),
    )


@router.get("", response_model=schemas.CapaInfoOut)
def info(_=Depends(require_user)):
    return _info_atual()


@router.get("/visualizar")
def visualizar(_=Depends(require_user)):
    p = _caminho_capa()
    if not p.is_file():
        raise HTTPException(404, "Capa não configurada")
    return FileResponse(str(p), media_type="application/pdf", filename=p.name)


@router.post("", response_model=schemas.CapaInfoOut, deprecated=True)
async def upload(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Importa um upload antigo como modelo selecionavel da biblioteca."""
    pasta = settings.data_path(settings.capa_folder)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = _caminho_capa()
    await save_upload(
        arquivo,
        destino,
        kind="pdf",
        allowed_suffixes={".pdf"},
    )
    capa_service.importar_capa_legada(db)
    return _info_atual()


@router.delete("", status_code=204)
def remover(_=Depends(require_admin)):
    p = _caminho_capa()
    if p.is_file():
        try:
            p.unlink()
        except Exception:
            pass
