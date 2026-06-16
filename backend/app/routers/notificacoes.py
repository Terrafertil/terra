"""Notificações do modo FULL (PDFs não processados)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from .. import schemas
from ..auth import require_user
from ..services import notificacoes_service


router = APIRouter(prefix="/api/notificacoes", tags=["notificacoes"])


@router.get("", response_model=list[schemas.NotificacaoFullOut])
def listar(
    apenas_nao_lidas: bool = Query(False),
    limite: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    return notificacoes_service.listar(db, apenas_nao_lidas=apenas_nao_lidas, limite=limite)


@router.get("/contagem")
def contagem(db: Session = Depends(get_db), _=Depends(require_user)):
    return {"nao_lidas": notificacoes_service.contar_nao_lidas(db)}


@router.patch("/{nid}/lida", response_model=schemas.NotificacaoFullOut)
def marcar_lida(nid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    n = notificacoes_service.marcar_lida(db, nid)
    if not n:
        raise HTTPException(404, "Notificação não encontrada")
    return n


@router.post("/marcar-todas-lidas")
def marcar_todas(db: Session = Depends(get_db), _=Depends(require_user)):
    n = notificacoes_service.marcar_todas_lidas(db)
    return {"marcadas": n}
