"""CRUD de usuários (só admin). Admin Diretor nunca aparece e não pode ser alterado."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas
from ..auth import require_admin, hash_senha
from ..services.diretor_service import (
    is_diretor,
    diretor_username,
    usuario_visivel_na_gestao,
)
from ..services.password_policy import validate_password_strength


router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


def _query_usuarios_gestao(db: Session):
    """Exclui Admin Diretor (is_diretor ou username reservado)."""
    un = diretor_username()
    return (
        db.query(models.Usuario)
        .filter(func.coalesce(models.Usuario.is_diretor, False).is_(False))
        .filter(func.lower(func.trim(models.Usuario.username)) != un)
    )


def _obter_para_gestao(db: Session, user_id: int) -> models.Usuario:
    u = db.get(models.Usuario, user_id)
    if not u or not usuario_visivel_na_gestao(u):
        raise HTTPException(404, "Usuário não encontrado")
    return u


@router.get("", response_model=list[schemas.UsuarioOut])
def listar(db: Session = Depends(get_db), _=Depends(require_admin)):
    return _query_usuarios_gestao(db).order_by(models.Usuario.username).all()


@router.post("", response_model=schemas.UsuarioOut, status_code=201)
def criar(payload: schemas.UsuarioCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    nome_user = payload.username.strip().lower()
    if nome_user == diretor_username():
        raise HTTPException(400, "Este nome de utilizador é reservado ao sistema (Admin Diretor)")

    if db.query(models.Usuario).filter(models.Usuario.username == payload.username).first():
        raise HTTPException(400, "Username já existe")

    try:
        validate_password_strength(payload.senha)
    except ValueError as e:
        raise HTTPException(400, str(e))

    u = models.Usuario(
        username=payload.username,
        nome=payload.nome,
        email=payload.email,
        senha_hash=hash_senha(payload.senha),
        is_admin=payload.is_admin,
        is_diretor=False,
        acesso_backup=payload.acesso_backup or payload.is_admin,
        ativo=payload.ativo,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.put("/{user_id}", response_model=schemas.UsuarioOut)
def atualizar(
    user_id: int,
    payload: schemas.UsuarioUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    u = _obter_para_gestao(db, user_id)

    data = payload.model_dump(exclude_unset=True)
    data.pop("is_diretor", None)
    if "senha" in data and data["senha"]:
        try:
            validate_password_strength(data["senha"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        u.senha_hash = hash_senha(data.pop("senha"))
    else:
        data.pop("senha", None)

    for k, v in data.items():
        setattr(u, k, v)
    if u.is_admin:
        u.acesso_backup = True

    db.commit()
    db.refresh(u)
    return u


@router.delete("/{user_id}", status_code=204)
def remover(user_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    u = _obter_para_gestao(db, user_id)
    db.delete(u)
    db.commit()
