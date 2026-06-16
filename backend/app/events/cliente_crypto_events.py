"""SQLAlchemy: cifra antes de gravar e decifra ao carregar clientes."""
from sqlalchemy import event

from .. import models
from ..services import data_crypto_service as crypto
from ..services.cliente_crypto import decrypt_cliente_fields, encrypt_cliente_fields
from ..services.data_crypto_service import encryption_enabled


@event.listens_for(models.Cliente, "before_insert")
@event.listens_for(models.Cliente, "before_update")
def _cliente_encrypt(_mapper, _connection, target: models.Cliente) -> None:
    if encryption_enabled():
        nome = target.nome or ""
        if nome.startswith(crypto.SOC_PREFIX):
            return
        encrypt_cliente_fields(target)


@event.listens_for(models.Cliente, "load")
def _cliente_decrypt(target: models.Cliente, _context) -> None:
    if encryption_enabled():
        decrypt_cliente_fields(target)
