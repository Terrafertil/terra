"""Atalhos HTML personalizados no editor de corpos de e-mail."""
from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from .. import models


def listar_personalizados(db: Session) -> list[dict]:
    rc = db.get(models.RuntimeConfig, 1)
    if not rc or not rc.atalhos_email_json:
        return []
    try:
        data = json.loads(rc.atalhos_email_json)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def salvar_personalizados(db: Session, atalhos: list[dict]) -> list[dict]:
    rc = db.get(models.RuntimeConfig, 1)
    if rc is None:
        rc = models.RuntimeConfig(id=1)
        db.add(rc)
    rc.atalhos_email_json = json.dumps(atalhos, ensure_ascii=False)
    db.commit()
    return atalhos


def novo_id() -> str:
    return uuid.uuid4().hex[:12]
