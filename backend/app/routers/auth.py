"""Rotas de autenticação."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from .. import models, schemas
from ..auth import (
    verificar_senha,
    criar_token,
    token_extra,
    require_user,
    require_diretor,
    hash_senha,
    usuario_tem_acesso_backup,
)
from ..services.diretor_service import (
    is_diretor,
    diretor_username,
    ler_token_recuperacao,
    verificar_token_recuperacao,
)
from ..services.data_crypto_service import (
    backend_access_enabled,
    encryption_enabled,
    verify_backend_access,
)
from ..services.password_policy import validate_password_strength


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginPayload, db: Session = Depends(get_db)):
    user = (
        db.query(models.Usuario)
        .filter(models.Usuario.username == payload.username)
        .first()
    )
    if not user or not user.ativo or not verificar_senha(payload.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = criar_token(user.username, token_extra(user))
    return schemas.TokenOut(access_token=token, user=user)


@router.post("/trocar-senha", response_model=schemas.TrocaSenhaOut)
def trocar_senha(
    payload: schemas.TrocaSenhaIn,
    db: Session = Depends(get_db),
    user: models.Usuario = Depends(require_user),
):
    if payload.senha_nova != payload.senha_nova_confirmacao:
        raise HTTPException(400, "A nova senha e a confirmação não coincidem")

    if not verificar_senha(payload.senha_atual, user.senha_hash):
        raise HTTPException(400, "Senha atual incorreta")

    if verificar_senha(payload.senha_nova, user.senha_hash):
        raise HTTPException(400, "A nova senha deve ser diferente da atual")

    try:
        validate_password_strength(payload.senha_nova)
    except ValueError as e:
        raise HTTPException(400, str(e))

    user.senha_hash = hash_senha(payload.senha_nova)
    user.must_change_password = False
    db.commit()
    db.refresh(user)

    token = criar_token(user.username, token_extra(user))
    return schemas.TrocaSenhaOut(
        mensagem="Senha alterada com sucesso.",
        access_token=token,
        user=user,
    )


@router.get("/me", response_model=schemas.UsuarioOut)
def usuario_atual(user: models.Usuario = Depends(require_user)):
    return user


@router.get("/status")
def auth_status():
    return {
        "auth_enabled": settings.auth_enabled,
        "backend_access_enabled": backend_access_enabled(),
        "data_encryption_enabled": encryption_enabled(),
    }


@router.get("/pode-acessar-backup")
def pode_acessar_backup(user: models.Usuario = Depends(require_user)):
    return {"permitido": usuario_tem_acesso_backup(user)}


@router.get("/diretor/token-recuperacao", response_model=schemas.DiretorTokenOut)
def obter_token_recuperacao_diretor(user: models.Usuario = Depends(require_diretor)):
    token = ler_token_recuperacao(user)
    if not token:
        raise HTTPException(
            500, "Token de recuperação não configurado. Contacte suporte técnico."
        )
    return schemas.DiretorTokenOut(token=token)


@router.post("/recuperar-diretor", response_model=schemas.TrocaSenhaOut)
def recuperar_diretor(payload: schemas.RecuperarDiretorIn, db: Session = Depends(get_db)):
    if not settings.auth_enabled:
        raise HTTPException(400, "Autenticação desativada")
    user = (
        db.query(models.Usuario)
        .filter(models.Usuario.username == diretor_username())
        .first()
    )
    if not user or not is_diretor(user):
        raise HTTPException(400, "Conta Admin Diretor não encontrada")

    if not verificar_token_recuperacao(user, payload.token):
        raise HTTPException(403, "Token de recuperação inválido")

    if payload.senha_nova != payload.senha_nova_confirmacao:
        raise HTTPException(400, "A nova senha e a confirmação não coincidem")

    try:
        validate_password_strength(payload.senha_nova)
    except ValueError as e:
        raise HTTPException(400, str(e))

    user.senha_hash = hash_senha(payload.senha_nova)
    user.must_change_password = False
    db.commit()
    db.refresh(user)

    token = criar_token(user.username, token_extra(user))
    return schemas.TrocaSenhaOut(
        mensagem="Senha do Admin Diretor redefinida com sucesso.",
        access_token=token,
        user=user,
    )


@router.post("/verificar-acesso-backend")
def verificar_acesso_backend(payload: schemas.BackendAccessVerifyIn):
    """Valida a chave de acesso (rota pública para o painel testar antes de guardar)."""
    if not backend_access_enabled():
        return {"ok": True, "mensagem": "Porta de acesso desativada no servidor."}
    if verify_backend_access(payload.chave):
        return {"ok": True}
    raise HTTPException(status_code=403, detail="Chave de acesso inválida")
