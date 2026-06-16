"""Notificações do modo FULL (PDFs ignorados ou com falha)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .. import models


def registrar(
    db: Session,
    *,
    arquivo: str,
    motivo: str,
    layout: str | None = None,
    tipo_codigo: str | None = None,
    pasta: str | None = None,
) -> models.NotificacaoFull:
    n = models.NotificacaoFull(
        arquivo=arquivo[:500],
        motivo=motivo[:2000],
        layout=layout,
        tipo_codigo=tipo_codigo,
        pasta=pasta,
        lida=False,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def listar(db: Session, *, apenas_nao_lidas: bool = False, limite: int = 50) -> list[models.NotificacaoFull]:
    q = db.query(models.NotificacaoFull)
    if apenas_nao_lidas:
        q = q.filter(models.NotificacaoFull.lida == False)  # noqa: E712
    return q.order_by(models.NotificacaoFull.criado_em.desc()).limit(limite).all()


def contar_nao_lidas(db: Session) -> int:
    return (
        db.query(models.NotificacaoFull)
        .filter(models.NotificacaoFull.lida == False)  # noqa: E712
        .count()
    )


def marcar_lida(db: Session, nid: int) -> models.NotificacaoFull | None:
    n = db.get(models.NotificacaoFull, nid)
    if not n:
        return None
    n.lida = True
    db.commit()
    db.refresh(n)
    return n


def marcar_todas_lidas(db: Session) -> int:
    q = db.query(models.NotificacaoFull).filter(models.NotificacaoFull.lida == False)  # noqa: E712
    count = q.count()
    q.update({"lida": True})
    db.commit()
    return count


def limpar_antigas(db: Session, dias: int = 30) -> int:
    limite = datetime.utcnow()
    from datetime import timedelta

    limite = limite - timedelta(days=dias)
    q = db.query(models.NotificacaoFull).filter(models.NotificacaoFull.criado_em < limite)
    count = q.count()
    q.delete()
    db.commit()
    return count
