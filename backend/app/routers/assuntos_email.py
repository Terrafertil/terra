"""CRUD de assuntos de e-mail reutilizaveis por tipo de envio."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_admin, require_user
from ..database import get_db


router = APIRouter(prefix="/api/assuntos-email", tags=["assuntos-email"])


def _normalizar_textos(dados: dict) -> dict:
    for campo in ("nome", "descricao", "assunto"):
        valor = dados.get(campo)
        if isinstance(valor, str):
            dados[campo] = valor.strip()
    return dados


@router.get("", response_model=list[schemas.AssuntoEmailOut])
def listar(
    ativo: bool | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    q = db.query(models.AssuntoEmail)
    if ativo is not None:
        q = q.filter(models.AssuntoEmail.ativo == ativo)
    return q.order_by(models.AssuntoEmail.nome, models.AssuntoEmail.id).all()


@router.get("/{aid}", response_model=schemas.AssuntoEmailOut)
def obter(aid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    assunto = db.get(models.AssuntoEmail, aid)
    if not assunto:
        raise HTTPException(404, "Assunto de e-mail nao encontrado")
    return assunto


@router.post("", response_model=schemas.AssuntoEmailOut, status_code=201)
def criar(
    payload: schemas.AssuntoEmailCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    dados = _normalizar_textos(payload.model_dump())
    if not dados["nome"] or not dados["assunto"]:
        raise HTTPException(400, "Nome e assunto sao obrigatorios")
    if db.query(models.AssuntoEmail).filter(
        models.AssuntoEmail.nome == dados["nome"]
    ).first():
        raise HTTPException(400, "Nome ja existe")
    assunto = models.AssuntoEmail(**dados)
    db.add(assunto)
    db.commit()
    db.refresh(assunto)
    return assunto


@router.put("/{aid}", response_model=schemas.AssuntoEmailOut)
def atualizar(
    aid: int,
    payload: schemas.AssuntoEmailUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    assunto = db.get(models.AssuntoEmail, aid)
    if not assunto:
        raise HTTPException(404, "Assunto de e-mail nao encontrado")
    dados = _normalizar_textos(payload.model_dump(exclude_unset=True))
    if "nome" in dados and not dados["nome"]:
        raise HTTPException(400, "Nome e obrigatorio")
    if "assunto" in dados and not dados["assunto"]:
        raise HTTPException(400, "Assunto e obrigatorio")
    if "nome" in dados and dados["nome"] != assunto.nome:
        existe = db.query(models.AssuntoEmail).filter(
            models.AssuntoEmail.nome == dados["nome"],
            models.AssuntoEmail.id != aid,
        ).first()
        if existe:
            raise HTTPException(400, "Nome ja existe")
    for campo, valor in dados.items():
        setattr(assunto, campo, valor)
    db.commit()
    db.refresh(assunto)
    return assunto


@router.delete("/{aid}", status_code=204)
def remover(aid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    assunto = db.get(models.AssuntoEmail, aid)
    if not assunto:
        raise HTTPException(404, "Assunto de e-mail nao encontrado")
    vinculado = db.query(models.TipoEnvio.id).filter(
        models.TipoEnvio.assunto_email_id == aid
    ).first()
    if vinculado:
        raise HTTPException(
            409, "Assunto vinculado a um tipo de envio; desvincule antes de excluir"
        )
    db.delete(assunto)
    db.commit()
