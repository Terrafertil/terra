"""CRUD de corpos de e-mail (HTML reutilizável com placeholders)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..auth import require_user
from ..services import email_service, atalhos_service


router = APIRouter(prefix="/api/corpos-email", tags=["corpos-email"])


@router.get("", response_model=list[schemas.CorpoEmailOut])
def listar(
    ativo: bool | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    q = db.query(models.CorpoEmail)
    if ativo is not None:
        q = q.filter(models.CorpoEmail.ativo == ativo)
    return q.order_by(models.CorpoEmail.nome).all()


@router.get("/placeholders")
def placeholders():
    """Lista de placeholders disponíveis para o editor."""
    return {"placeholders": email_service.PLACEHOLDERS_DISPONIVEIS}


@router.get("/atalhos")
def listar_atalhos(db: Session = Depends(get_db), _=Depends(require_user)):
    """Placeholders, blocos por modelo de apólice e atalhos personalizados."""
    return {
        "placeholders": email_service.PLACEHOLDERS_DISPONIVEIS,
        "modelos": email_service.ATALHOS_MODELOS,
        "personalizados": atalhos_service.listar_personalizados(db),
    }


@router.put("/atalhos-personalizados")
def salvar_atalhos_personalizados(
    payload: schemas.AtalhosPersonalizadosPatch,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    """Substitui a lista de atalhos HTML criados pela equipe."""
    itens = [a.model_dump() for a in payload.atalhos]
    atalhos_service.salvar_personalizados(db, itens)
    return {"personalizados": itens}


@router.get("/{cid}", response_model=schemas.CorpoEmailOut)
def obter(cid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    c = db.get(models.CorpoEmail, cid)
    if not c:
        raise HTTPException(404, "Corpo de e-mail não encontrado")
    return c


@router.post("", response_model=schemas.CorpoEmailOut, status_code=201)
def criar(
    payload: schemas.CorpoEmailCreate,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    if db.query(models.CorpoEmail).filter(models.CorpoEmail.nome == payload.nome).first():
        raise HTTPException(400, "Nome já existe")
    c = models.CorpoEmail(**payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.put("/{cid}", response_model=schemas.CorpoEmailOut)
def atualizar(
    cid: int,
    payload: schemas.CorpoEmailUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    c = db.get(models.CorpoEmail, cid)
    if not c:
        raise HTTPException(404, "Corpo de e-mail não encontrado")
    dados = payload.model_dump(exclude_unset=True)
    if "nome" in dados and dados["nome"] != c.nome:
        existe = db.query(models.CorpoEmail).filter(
            models.CorpoEmail.nome == dados["nome"],
            models.CorpoEmail.id != cid,
        ).first()
        if existe:
            raise HTTPException(400, "Nome já existe")
    for k, v in dados.items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{cid}", status_code=204)
def remover(cid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    c = db.get(models.CorpoEmail, cid)
    if not c:
        raise HTTPException(404, "Corpo de e-mail não encontrado")
    # desvincula de tipos antes de remover
    db.query(models.TipoEnvio).filter(models.TipoEnvio.corpo_email_id == cid).update(
        {"corpo_email_id": None}
    )
    db.delete(c)
    db.commit()
