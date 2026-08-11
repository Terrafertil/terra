"""Criptografia do snapshot de destinatário gravado em Envio."""
from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from .. import models
from . import data_crypto_service as crypto


def encrypt_destinatario(envio: models.Envio) -> None:
    if not crypto.encryption_enabled():
        return
    valor = envio.destinatario_email
    if valor is None or valor == "":
        return
    armazenado = str(valor)
    if armazenado.startswith((crypto.ENC_PREFIX, crypto.SOC_PREFIX)):
        return
    envio.destinatario_email = crypto.encrypt_field(armazenado)


def decrypt_destinatario(envio: models.Envio) -> None:
    if not crypto.encryption_enabled():
        return
    valor = envio.destinatario_email
    if valor is None or valor == "":
        return
    armazenado = str(valor)
    # Durante o modo SOC a chave só é fornecida na desativação. Assim
    # como nos clientes, não se tenta abrir esse valor em carregamentos comuns.
    if armazenado.startswith(crypto.SOC_PREFIX):
        return
    # Eventos load/refresh não podem marcar a instância como alterada; isso
    # provocaria uma recifragem aleatória no próximo autoflush sem mudança real.
    set_committed_value(
        envio,
        "destinatario_email",
        crypto.decrypt_field(armazenado),
    )


def migrate_plaintext_envios(db: Session) -> int:
    """Cifra snapshots legados que tenham sido gravados em texto claro."""
    if not crypto.encryption_enabled():
        return 0
    # O filtro roda no banco, antes do listener ``load`` decifrar valores enc2.
    # Assim snapshots já protegidos não são recifrados a cada inicialização.
    rows = (
        db.query(models.Envio)
        .filter(
            models.Envio.destinatario_email.isnot(None),
            models.Envio.destinatario_email != "",
            ~models.Envio.destinatario_email.like(f"{crypto.ENC_PREFIX}%"),
            ~models.Envio.destinatario_email.like(f"{crypto.SOC_PREFIX}%"),
        )
        .all()
    )
    for envio in rows:
        encrypt_destinatario(envio)
    if rows:
        db.commit()
    return len(rows)
