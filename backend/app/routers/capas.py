"""Catalogo de modelos PDF usados antes ou depois da apolice."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import require_admin, require_user
from ..database import get_db
from ..services import capa_service


router = APIRouter(prefix="/api/capas", tags=["capas"])


def _http_error(exc: capa_service.CapaServiceError) -> HTTPException:
    if isinstance(exc, capa_service.CapaNaoEncontradaError):
        return HTTPException(404, str(exc))
    if isinstance(exc, capa_service.CapaEmUsoError):
        return HTTPException(409, str(exc))
    return HTTPException(400, str(exc))


@router.get("", response_model=list[schemas.CapaModeloOut])
def listar(
    ativo: bool | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    return capa_service.listar_modelos(db, ativo=ativo)


@router.post("", response_model=schemas.CapaModeloOut, status_code=201)
async def criar(
    nome: str = Form(...),
    descricao: str | None = Form(None),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        return await capa_service.criar_modelo(
            db,
            nome=nome,
            descricao=descricao,
            arquivo=arquivo,
        )
    except capa_service.CapaServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{capa_id}/arquivo")
def visualizar_arquivo(
    capa_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    try:
        capa = capa_service.obter_modelo(db, capa_id)
        path = capa_service.caminho_arquivo(capa)
    except capa_service.CapaServiceError as exc:
        raise _http_error(exc) from exc
    if not path.is_file():
        raise HTTPException(404, "Arquivo do modelo de capa nao encontrado")
    return FileResponse(
        str(path),
        media_type="application/pdf",
        filename=capa.nome_original or f"{capa.nome}.pdf",
    )


@router.put("/{capa_id}", response_model=schemas.CapaModeloOut)
def atualizar(
    capa_id: int,
    payload: schemas.CapaModeloUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        return capa_service.atualizar_modelo(
            db,
            capa_id,
            dados=payload.model_dump(exclude_unset=True),
        )
    except capa_service.CapaServiceError as exc:
        raise _http_error(exc) from exc


@router.delete("/{capa_id}", status_code=204)
def remover(
    capa_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        capa_service.remover_modelo(db, capa_id)
    except capa_service.CapaServiceError as exc:
        raise _http_error(exc) from exc
