"""Gestão da capa (PDF que vai antes da apólice em todo envio)."""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pypdf import PdfReader

from ..config import settings
from .. import schemas
from ..auth import require_user


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
def visualizar():
    p = _caminho_capa()
    if not p.is_file():
        raise HTTPException(404, "Capa não configurada")
    return FileResponse(str(p), media_type="application/pdf", filename=p.name)


@router.post("", response_model=schemas.CapaInfoOut)
async def upload(
    arquivo: UploadFile = File(...),
    _=Depends(require_user),
):
    """Upload de qualquer PDF; é renomeado automaticamente para `capa.pdf`
    (ou o que estiver em CAPA_ARQUIVO_PADRAO) para bater com o .env."""
    if not arquivo.filename:
        raise HTTPException(400, "Arquivo sem nome")
    if Path(arquivo.filename).suffix.lower() != ".pdf":
        raise HTTPException(400, "Envie um PDF (.pdf)")
    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(400, "Arquivo vazio")

    pasta = settings.data_path(settings.capa_folder)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = _caminho_capa()
    destino.write_bytes(conteudo)
    return _info_atual()


@router.delete("", status_code=204)
def remover(_=Depends(require_user)):
    p = _caminho_capa()
    if p.is_file():
        try:
            p.unlink()
        except Exception:
            pass
