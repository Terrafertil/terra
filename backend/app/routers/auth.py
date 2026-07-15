"""Rotas de autenticação."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
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
    create_backend_access_cookie_token,
)
from ..services.password_policy import validate_password_strength
from ..services.rate_limit_service import limiter


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=max(300, settings.access_token_expire_minutes * 60),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=schemas.TokenOut)
def login(
    payload: schemas.LoginPayload,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    rate_key = f"login:{_client_ip(request)}:{payload.username.strip().lower()}"
    limiter.check(rate_key, limit=5, window_seconds=60)
    user = (
        db.query(models.Usuario)
        .filter(models.Usuario.username == payload.username)
        .first()
    )
    if not user or not user.ativo or not verificar_senha(payload.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    limiter.clear(rate_key)
    token = criar_token(user.username, token_extra(user))
    _set_auth_cookie(response, token)
    return schemas.TokenOut(user=user)


@router.post("/trocar-senha", response_model=schemas.TrocaSenhaOut)
def trocar_senha(
    payload: schemas.TrocaSenhaIn,
    response: Response,
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
    user.session_version = int(user.session_version or 1) + 1
    db.commit()
    db.refresh(user)

    token = criar_token(user.username, token_extra(user))
    _set_auth_cookie(response, token)
    return schemas.TrocaSenhaOut(
        mensagem="Senha alterada com sucesso.",
        user=user,
    )


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(settings.auth_cookie_name, path="/")
    response.delete_cookie(settings.backend_access_cookie_name, path="/")


@router.get("/me", response_model=schemas.UsuarioOut)
def usuario_atual(user: models.Usuario = Depends(require_user)):
    return user


@router.get("/status")
def auth_status(request: Request):
    backend_cookie = request.cookies.get(settings.backend_access_cookie_name)
    return {
        "auth_enabled": settings.auth_enabled,
        "backend_access_enabled": backend_access_enabled(),
        "backend_access_authorized": verify_backend_access(backend_cookie),
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
def recuperar_diretor(
    payload: schemas.RecuperarDiretorIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    rate_key = f"recuperar-diretor:{_client_ip(request)}"
    limiter.check(rate_key, limit=5, window_seconds=900)
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
    user.session_version = int(user.session_version or 1) + 1
    db.commit()
    db.refresh(user)

    limiter.clear(rate_key)
    token = criar_token(user.username, token_extra(user))
    _set_auth_cookie(response, token)
    return schemas.TrocaSenhaOut(
        mensagem="Senha do Admin Diretor redefinida com sucesso.",
        user=user,
    )


@router.post("/verificar-acesso-backend")
def verificar_acesso_backend(
    payload: schemas.BackendAccessVerifyIn,
    request: Request,
    response: Response,
):
    """Valida a chave de acesso (rota pública para o painel testar antes de guardar)."""
    if not backend_access_enabled():
        return {"ok": True, "mensagem": "Porta de acesso desativada no servidor."}
    rate_key = f"backend-access:{_client_ip(request)}"
    limiter.check(rate_key, limit=10, window_seconds=300)
    if verify_backend_access(payload.chave):
        limiter.clear(rate_key)
        response.set_cookie(
            key=settings.backend_access_cookie_name,
            value=create_backend_access_cookie_token(),
            max_age=max(300, settings.access_token_expire_minutes * 60),
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite="lax",
            path="/",
        )
        return {"ok": True}
    raise HTTPException(status_code=403, detail="Chave de acesso inválida")
