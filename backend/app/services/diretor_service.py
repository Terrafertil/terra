"""Admin Diretor: conta protegida, token de recuperação e desativação SOC."""
from __future__ import annotations

import secrets
import string

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from .data_crypto_service import encrypt_field, decrypt_field


def diretor_username() -> str:
    return (settings.diretor_username or "admindiretor").strip().lower()


def is_diretor(user: models.Usuario | None) -> bool:
    if not user:
        return False
    if bool(getattr(user, "is_diretor", False)):
        return True
    try:
        return (user.username or "").strip().lower() == diretor_username()
    except Exception:
        return False


def usuario_visivel_na_gestao(user: models.Usuario) -> bool:
    """False para Admin Diretor — nunca listar nem editar na gestão de utilizadores."""
    return not is_diretor(user)


def gerar_token_recuperacao(tamanho: int = 32) -> str:
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(tamanho))


def guardar_token_recuperacao(user: models.Usuario, token: str) -> None:
    user.recovery_token_enc = encrypt_field(token.strip())


def ler_token_recuperacao(user: models.Usuario) -> str | None:
    if not user.recovery_token_enc:
        return None
    return decrypt_field(user.recovery_token_enc)


def verificar_token_recuperacao(user: models.Usuario, token: str) -> bool:
    guardado = ler_token_recuperacao(user)
    if not guardado:
        return False
    import secrets as sec

    return sec.compare_digest(guardado.strip(), token.strip())


def seed_diretor(db: Session) -> None:
    """Garante o utilizador Admin Diretor (oculto na lista de utilizadores)."""
    from ..auth import hash_senha

    username = diretor_username()
    u = db.query(models.Usuario).filter(models.Usuario.username == username).first()
    token_plain = (settings.diretor_recovery_token or "").strip()
    if not token_plain:
        token_plain = gerar_token_recuperacao()

    if u is None:
        u = models.Usuario(
            username=username,
            nome="Admin Diretor",
            email=None,
            senha_hash=hash_senha(settings.diretor_password),
            must_change_password=True,
            is_admin=True,
            is_diretor=True,
            acesso_backup=True,
            ativo=True,
        )
        guardar_token_recuperacao(u, token_plain)
        db.add(u)
        db.commit()
        return

    changed = False
    if not u.is_diretor:
        u.is_diretor = True
        changed = True
    if not u.is_admin:
        u.is_admin = True
        changed = True
    u.acesso_backup = True
    if not u.recovery_token_enc:
        guardar_token_recuperacao(u, token_plain)
        changed = True
    if changed:
        db.commit()
