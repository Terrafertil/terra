"""Modo SOC — resposta a incidente de segurança."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_user, require_admin, require_diretor
from ..database import get_db
from .. import schemas
from ..services import soc_service


router = APIRouter(prefix="/api/soc", tags=["soc"])


@router.get("/status", response_model=schemas.SocStatusOut)
def status_soc(db: Session = Depends(get_db), _=Depends(require_user)):
    return schemas.SocStatusOut(**soc_service.soc_status(db))


@router.post("/ativar", response_model=schemas.SocAcaoOut)
def ativar_soc(
    payload: schemas.SocAtivarIn,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    if payload.chave_soc != payload.chave_soc_confirmacao:
        raise HTTPException(400, "As chaves não coincidem")
    try:
        out = soc_service.ativar_modo_soc(
            db,
            chave_soc=payload.chave_soc,
            motivo=payload.motivo,
            ativado_por_id=user.id,
            ativado_por_nome=user.nome,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return schemas.SocAcaoOut(**out)


@router.post("/desativar", response_model=schemas.SocAcaoOut)
def desativar_soc(
    payload: schemas.SocDesativarIn,
    db: Session = Depends(get_db),
    _=Depends(require_diretor),
):
    try:
        out = soc_service.desativar_modo_soc(db, chave_soc=payload.chave_soc)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return schemas.SocAcaoOut(**out)
