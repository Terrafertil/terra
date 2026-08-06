"""Criptografia de clientes + busca por hash."""
from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from . import data_crypto_service as crypto


_SENSITIVE = ("nome", "email", "cpf", "cnpj", "telefone", "observacoes")


def _norm_digits(val: str | None) -> str:
    return re.sub(r"\D", "", val or "")


def encrypt_cliente_fields(c: models.Cliente) -> None:
    if not crypto.encryption_enabled():
        return
    plain = {}
    for f in _SENSITIVE:
        val = getattr(c, f)
        if val is None:
            plain[f] = None
            continue
        s = str(val)
        if s.startswith(crypto.ENC_PREFIX) or s.startswith(crypto.SOC_PREFIX):
            continue
        plain[f] = val
    c.cpf_hash = crypto.field_hash(plain.get("cpf"), "cpf")
    c.cnpj_hash = crypto.field_hash(plain.get("cnpj"), "cnpj")
    c.email_hash = crypto.field_hash(plain.get("email"), "email")
    for field in _SENSITIVE:
        val = plain.get(field)
        if val is None:
            continue
        if val != "":
            setattr(c, field, crypto.encrypt_field(str(val)))


def decrypt_cliente_fields(c: models.Cliente) -> None:
    if not crypto.encryption_enabled():
        return
    for field in _SENSITIVE:
        val = getattr(c, field)
        if val is None:
            continue
        s = str(val)
        if s.startswith(crypto.SOC_PREFIX):
            continue
        setattr(c, field, crypto.decrypt_field(s))


def decrypt_many(clientes: Iterable[models.Cliente]) -> list[models.Cliente]:
    out = list(clientes)
    for c in out:
        decrypt_cliente_fields(c)
    return out


def _so_digitos(doc: str | None) -> str:
    return "".join(ch for ch in (doc or "") if ch.isdigit())


def _formatar_cpf(dig: str) -> str:
    if len(dig) != 11:
        return dig
    return f"{dig[:3]}.{dig[3:6]}.{dig[6:9]}-{dig[9:]}"


def _formatar_cnpj(dig: str) -> str:
    if len(dig) != 14:
        return dig
    return f"{dig[:2]}.{dig[2:5]}.{dig[5:8]}/{dig[8:12]}-{dig[12:]}"


def find_by_cpf(db: Session, cpf: str | None) -> models.Cliente | None:
    if not cpf:
        return None
    dig = _so_digitos(cpf)
    if crypto.encryption_enabled():
        h = crypto.field_hash(dig or cpf, "cpf")
        if h:
            c = db.query(models.Cliente).filter(models.Cliente.cpf_hash == h).first()
            if c:
                decrypt_cliente_fields(c)
                return c
        return None
    variantes = {v for v in (cpf, dig, _formatar_cpf(dig)) if v}
    c = (
        db.query(models.Cliente)
        .filter(models.Cliente.cpf.in_(variantes))
        .first()
    )
    if c:
        decrypt_cliente_fields(c)
        return c
    # Fallback: cadastros com formatação mista
    if dig and len(dig) == 11:
        for cand in db.query(models.Cliente).filter(models.Cliente.cpf.isnot(None)).all():
            if _so_digitos(cand.cpf) == dig:
                decrypt_cliente_fields(cand)
                return cand
    return None


def find_by_cnpj(db: Session, cnpj: str | None) -> models.Cliente | None:
    if not cnpj:
        return None
    dig = _so_digitos(cnpj)
    if crypto.encryption_enabled():
        h = crypto.field_hash(dig or cnpj, "cnpj")
        if h:
            c = db.query(models.Cliente).filter(models.Cliente.cnpj_hash == h).first()
            if c:
                decrypt_cliente_fields(c)
                return c
        return None
    variantes = {v for v in (cnpj, dig, _formatar_cnpj(dig)) if v}
    c = (
        db.query(models.Cliente)
        .filter(models.Cliente.cnpj.in_(variantes))
        .first()
    )
    if c:
        decrypt_cliente_fields(c)
        return c
    if dig and len(dig) == 14:
        for cand in db.query(models.Cliente).filter(models.Cliente.cnpj.isnot(None)).all():
            if _so_digitos(cand.cnpj) == dig:
                decrypt_cliente_fields(cand)
                return cand
    return None


def get_by_id(db: Session, cid: int) -> models.Cliente | None:
    c = db.get(models.Cliente, cid)
    if c:
        decrypt_cliente_fields(c)
    return c


def list_clientes(
    db: Session,
    *,
    q: str | None = None,
    ativo: bool | None = None,
) -> list[models.Cliente]:
    query = db.query(models.Cliente)
    if ativo is not None:
        query = query.filter(models.Cliente.ativo == ativo)

    if q and crypto.encryption_enabled():
        term = q.strip()
        digits = _norm_digits(term)
        email_l = term.lower()
        clauses = []
        if len(digits) >= 11:
            h = crypto.field_hash(digits, "cpf")
            if h:
                clauses.append(models.Cliente.cpf_hash == h)
        if len(digits) >= 14:
            h = crypto.field_hash(digits, "cnpj")
            if h:
                clauses.append(models.Cliente.cnpj_hash == h)
        if "@" in email_l:
            h = crypto.field_hash(email_l, "email")
            if h:
                clauses.append(models.Cliente.email_hash == h)
        if clauses:
            query = query.filter(or_(*clauses))
            rows = query.all()
            return decrypt_many(rows)
        # Busca parcial: carrega e filtra em memória (adequado para volume de corretora)
        rows = query.all()
        decrypted = decrypt_many(rows)
        t = term.lower()
        return [
            c
            for c in decrypted
            if t in (c.nome or "").lower()
            or t in (c.email or "").lower()
            or t in (c.cpf or "")
            or t in (c.cnpj or "")
        ]

    if q:
        ilike = f"%{q}%"
        query = query.filter(
            or_(
                models.Cliente.nome.ilike(ilike),
                models.Cliente.email.ilike(ilike),
                models.Cliente.cpf.ilike(ilike),
                models.Cliente.cnpj.ilike(ilike),
            )
        )

    rows = query.all()
    decrypted = decrypt_many(rows)
    decrypted.sort(key=lambda c: (c.nome or "").lower())
    return decrypted


def migrate_plaintext_clientes(db: Session) -> int:
    """Cifra registos antigos em texto claro (uma vez)."""
    if not crypto.encryption_enabled():
        return 0
    rows = db.query(models.Cliente).all()
    n = 0
    for c in rows:
        if (c.nome or "").startswith(crypto.ENC_PREFIX):
            continue
        encrypt_cliente_fields(c)
        n += 1
    if n:
        db.commit()
        log = __import__("logging").getLogger("cliente_crypto")
        log.info("Migrados %s cliente(s) para criptografia dupla.", n)
    return n
