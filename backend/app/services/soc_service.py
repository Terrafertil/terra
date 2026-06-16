"""Modo SOC: bloqueio operacional + recriptografia de emergência (chave separada do .env)."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from . import data_crypto_service as crypto

log = logging.getLogger(__name__)

_SENSITIVE = ("nome", "email", "cpf", "cnpj", "telefone", "observacoes")

SOC_BLOCK_MSG = (
    "Modo SOC ativo: envios e alterações bloqueados. "
    "Desative com a chave de emergência definida na ativação."
)


def _runtime(db: Session) -> models.RuntimeConfig:
    rc = db.get(models.RuntimeConfig, 1)
    if rc is None:
        rc = models.RuntimeConfig(id=1)
        db.add(rc)
        db.commit()
        db.refresh(rc)
    return rc


def is_soc_locked(db: Session) -> bool:
    return bool(_runtime(db).soc_mode_active)


def soc_status(db: Session) -> dict:
    rc = _runtime(db)
    return {
        "soc_mode_active": bool(rc.soc_mode_active),
        "soc_encryption_active": bool(rc.soc_encryption_active),
        "soc_motivo": rc.soc_motivo or "",
        "soc_ativado_em": rc.soc_ativado_em.isoformat(sep=" ") if rc.soc_ativado_em else None,
        "soc_ativado_por_nome": rc.soc_ativado_por_nome or "",
    }


def _plaintext_from_cliente(c: models.Cliente, *, chave_soc: str | None = None) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for field in _SENSITIVE:
        val = getattr(c, field)
        if val is None:
            out[field] = None
            continue
        s = str(val)
        out[field] = crypto.decrypt_field_any(s, chave_soc=chave_soc)
    return out


def _apply_plaintext(c: models.Cliente, plain: dict[str, str | None], *, chave_soc: str) -> None:
    for field in _SENSITIVE:
        val = plain.get(field)
        if val is not None and val != "":
            setattr(c, field, crypto.encrypt_field_soc(str(val), chave_soc))
        else:
            setattr(c, field, val)
    c.cpf_hash = crypto.field_hash_soc(plain.get("cpf"), "cpf", chave_soc)
    c.cnpj_hash = crypto.field_hash_soc(plain.get("cnpj"), "cnpj", chave_soc)
    c.email_hash = crypto.field_hash_soc(plain.get("email"), "email", chave_soc)


def _apply_plaintext_normal(c: models.Cliente, plain: dict[str, str | None]) -> None:
    from . import cliente_crypto

    for field in _SENSITIVE:
        setattr(c, field, plain.get(field))
    cliente_crypto.encrypt_cliente_fields(c)


def ativar_modo_soc(
    db: Session,
    *,
    chave_soc: str,
    motivo: str | None = None,
    ativado_por_id: int | None = None,
    ativado_por_nome: str | None = None,
) -> dict:
    chave = chave_soc.strip()
    if len(chave) < 8:
        raise ValueError("A chave de emergência SOC deve ter pelo menos 8 caracteres")
    if chave == (settings.data_encryption_password or "").strip():
        raise ValueError("Use uma chave SOC diferente da senha mestra do .env")

    rc = _runtime(db)
    if rc.soc_mode_active:
        raise ValueError("Modo SOC já está ativo")

    texto_motivo = (motivo or "").strip() or "Incidente de segurança"

    # 1) Bloqueio imediato
    rc.soc_mode_active = True
    rc.full_scan_active = False
    rc.full_modo_ativo = False
    rc.soc_motivo = texto_motivo
    rc.soc_ativado_em = datetime.utcnow()
    rc.soc_ativado_por_id = ativado_por_id
    rc.soc_ativado_por_nome = (ativado_por_nome or "").strip() or None
    db.commit()

    rows = db.query(models.Cliente).all()
    migrados = 0
    for c in rows:
        try:
            plain = _plaintext_from_cliente(c, chave_soc=None)
        except ValueError:
            plain = _plaintext_from_cliente(c, chave_soc=chave)
        _apply_plaintext(c, plain, chave_soc=chave)
        migrados += 1

    rc.soc_encryption_active = True
    rc.soc_key_verifier = crypto.soc_key_fingerprint(chave)
    db.commit()

    log.warning("MODO SOC ATIVADO. Clientes recifrados: %s. Motivo: %s", migrados, texto_motivo)
    return {
        "soc_mode_active": True,
        "clientes_recifrados": migrados,
        "mensagem": "Modo SOC ativo. Todos os envios estão bloqueados.",
    }


def desativar_modo_soc(db: Session, *, chave_soc: str) -> dict:
    chave = chave_soc.strip()
    rc = _runtime(db)
    if not rc.soc_mode_active:
        raise ValueError("Modo SOC não está ativo")

    if not crypto.verify_soc_key(chave, rc.soc_key_verifier):
        raise ValueError("Chave de emergência incorreta")

    rows = db.query(models.Cliente).all()
    migrados = 0
    for c in rows:
        plain = _plaintext_from_cliente(c, chave_soc=chave)
        _apply_plaintext_normal(c, plain)
        migrados += 1

    rc.soc_mode_active = False
    rc.soc_encryption_active = False
    rc.soc_key_verifier = None
    rc.soc_motivo = None
    rc.soc_ativado_em = None
    rc.soc_ativado_por_id = None
    rc.soc_ativado_por_nome = None
    db.commit()

    log.info("Modo SOC desativado. Clientes restaurados para criptografia normal: %s", migrados)
    return {
        "soc_mode_active": False,
        "clientes_restaurados": migrados,
        "mensagem": "Modo SOC desativado. Operações liberadas com criptografia padrão (.env).",
    }
