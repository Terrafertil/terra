"""CRUD de clientes."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..auth import require_user
from ..services import lgpd_service
from ..services import cliente_crypto


router = APIRouter(prefix="/api/clientes", tags=["clientes"])


@router.get("", response_model=list[schemas.ClienteOut])
def listar(
    q: str | None = Query(None, description="Busca em nome, email, cpf, cnpj"),
    ativo: bool | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    return cliente_crypto.list_clientes(db, q=q, ativo=ativo)


@router.get("/duplicados", response_model=list[schemas.ClienteDuplicadoGrupoOut])
def listar_duplicados(db: Session = Depends(get_db), _=Depends(require_user)):
    """CPF, CNPJ ou e-mail repetido entre cadastros."""
    return lgpd_service.listar_duplicados(db)


@router.get("/{cid}", response_model=schemas.ClienteOut)
def obter(cid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    c = cliente_crypto.get_by_id(db, cid)
    if not c:
        raise HTTPException(404, "Cliente não encontrado")
    return c


@router.post("", response_model=schemas.ClienteOut, status_code=201)
def criar(
    payload: schemas.ClienteCreate,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    c = models.Cliente(**payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    cliente_crypto.decrypt_cliente_fields(c)
    return c


@router.put("/{cid}", response_model=schemas.ClienteOut)
def atualizar(
    cid: int,
    payload: schemas.ClienteUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    c = db.get(models.Cliente, cid)
    if not c:
        raise HTTPException(404, "Cliente não encontrado")
    cliente_crypto.decrypt_cliente_fields(c)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    cliente_crypto.decrypt_cliente_fields(c)
    return c


@router.delete("/{cid}", status_code=204)
def remover(cid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    c = db.get(models.Cliente, cid)
    if not c:
        raise HTTPException(404, "Cliente não encontrado")
    db.delete(c)
    db.commit()


@router.post("/{cid}/exclusao-lgpd", response_model=schemas.ClienteLgpdExclusaoOut)
def exclusao_lgpd(
    cid: int,
    payload: schemas.ClienteLgpdExclusaoIn,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    """Exclusão do titular (LGPD): remove cadastro, histórico e PDFs de backup."""
    try:
        resultado = lgpd_service.excluir_cliente_lgpd(
            db,
            cid,
            confirmar_nome=payload.confirmar_nome,
            remover_backups=payload.remover_backups,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return schemas.ClienteLgpdExclusaoOut(**resultado)
