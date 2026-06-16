"""CRUD de autos/veículos vinculados a clientes."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..auth import require_user


router = APIRouter(prefix="/api/autos", tags=["autos"])


def _to_out(a: models.Auto) -> dict:
    return {
        "id": a.id,
        "cliente_id": a.cliente_id,
        "cliente_nome": a.cliente.nome if a.cliente else None,
        "placa": a.placa,
        "marca": a.marca,
        "modelo": a.modelo,
        "ano": a.ano,
        "chassi": a.chassi,
        "renavam": a.renavam,
        "cor": a.cor,
        "combustivel": a.combustivel,
        "observacoes": a.observacoes,
        "ativo": a.ativo,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


@router.get("", response_model=list[schemas.AutoOut])
def listar(
    cliente_id: int | None = None,
    q: str | None = Query(None, description="Busca em placa, marca, modelo, chassi"),
    ativo: bool | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    query = db.query(models.Auto)
    if cliente_id:
        query = query.filter(models.Auto.cliente_id == cliente_id)
    if q:
        ilike = f"%{q}%"
        query = query.filter(
            or_(
                models.Auto.placa.ilike(ilike),
                models.Auto.marca.ilike(ilike),
                models.Auto.modelo.ilike(ilike),
                models.Auto.chassi.ilike(ilike),
            )
        )
    if ativo is not None:
        query = query.filter(models.Auto.ativo == ativo)

    autos = query.order_by(models.Auto.placa).all()
    return [_to_out(a) for a in autos]


@router.get("/{aid}", response_model=schemas.AutoOut)
def obter(aid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    a = db.get(models.Auto, aid)
    if not a:
        raise HTTPException(404, "Auto não encontrado")
    return _to_out(a)


@router.post("", response_model=schemas.AutoOut, status_code=201)
def criar(
    payload: schemas.AutoCreate,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    cli = db.get(models.Cliente, payload.cliente_id)
    if not cli:
        raise HTTPException(400, "cliente_id inválido")
    a = models.Auto(**payload.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return _to_out(a)


@router.put("/{aid}", response_model=schemas.AutoOut)
def atualizar(
    aid: int,
    payload: schemas.AutoUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    a = db.get(models.Auto, aid)
    if not a:
        raise HTTPException(404, "Auto não encontrado")
    dados = payload.model_dump(exclude_unset=True)
    if "cliente_id" in dados and dados["cliente_id"]:
        cli = db.get(models.Cliente, dados["cliente_id"])
        if not cli:
            raise HTTPException(400, "cliente_id inválido")
    for k, v in dados.items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return _to_out(a)


@router.delete("/{aid}", status_code=204)
def remover(aid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    a = db.get(models.Auto, aid)
    if not a:
        raise HTTPException(404, "Auto não encontrado")
    db.delete(a)
    db.commit()
