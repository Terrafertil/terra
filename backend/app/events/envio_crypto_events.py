"""SQLAlchemy: cifra e decifra o snapshot de destinatário dos envios."""
from sqlalchemy import event

from .. import models
from ..services import envio_crypto


@event.listens_for(models.Envio, "before_insert")
@event.listens_for(models.Envio, "before_update")
def _envio_encrypt(_mapper, _connection, target: models.Envio) -> None:
    envio_crypto.encrypt_destinatario(target)


@event.listens_for(models.Envio, "load")
def _envio_decrypt_load(target: models.Envio, _context) -> None:
    envio_crypto.decrypt_destinatario(target)


@event.listens_for(models.Envio, "refresh")
def _envio_decrypt_refresh(target: models.Envio, _context, _attrs) -> None:
    envio_crypto.decrypt_destinatario(target)
