"""Criptografia em duas camadas (AES-256-GCM) para dados sensíveis."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from ..config import settings


log = logging.getLogger(__name__)

ENC_PREFIX = "enc2:"
SOC_PREFIX = "soc2:"
_PBKDF2_ITERS = 480_000


def encryption_enabled() -> bool:
    return bool(settings.data_encryption_enabled)


def backend_access_enabled() -> bool:
    return bool(settings.backend_access_enabled)


def validate_security_config() -> None:
    """Falha rápido na subida se produção estiver mal configurada."""
    host = (settings.app_host or "").strip().lower()
    local_only = host in {"127.0.0.1", "localhost", "::1"}
    if not settings.auth_enabled and not local_only and not settings.app_debug:
        raise RuntimeError(
            "AUTH_ENABLED=false so e permitido com APP_HOST local ou APP_DEBUG=true."
        )
    if settings.auth_enabled and settings.cors_list == ["*"]:
        raise RuntimeError("CORS_ORIGINS=* nao e permitido com autenticacao ativa.")
    if settings.auth_enabled and not local_only:
        weak_values = {
            "",
            "admin",
            "troque-essa-chave",
            "troque-essa-chave-em-producao-32-bytes-minimo",
            "tfd1r3t0r2026",
        }
        secret = (settings.secret_key or "").strip()
        if len(secret) < 32 or secret.lower() in weak_values:
            raise RuntimeError("SECRET_KEY deve ser aleatoria e ter pelo menos 32 caracteres.")
        if (settings.admin_password or "").strip().lower() in weak_values:
            raise RuntimeError("ADMIN_PASSWORD padrao ou vazia nao e permitida em producao.")
        if (settings.diretor_password or "").strip().lower() in weak_values:
            raise RuntimeError("DIRETOR_PASSWORD padrao ou vazia nao e permitida em producao.")

    if backend_access_enabled():
        key = (settings.backend_access_key or "").strip()
        if len(key) < 32:
            raise RuntimeError(
                "BACKEND_ACCESS_ENABLED=true exige BACKEND_ACCESS_KEY com pelo menos 32 caracteres."
            )
    if encryption_enabled():
        pwd = (settings.data_encryption_password or "").strip()
        if len(pwd) < 8:
            raise RuntimeError(
                "DATA_ENCRYPTION_ENABLED=true exige DATA_ENCRYPTION_PASSWORD com pelo menos 8 caracteres."
            )
        if not local_only and pwd == "@Nt1p@r1d@d3":
            raise RuntimeError("DATA_ENCRYPTION_PASSWORD padrao nao e permitida em producao.")


def verify_backend_access(provided: str | None) -> bool:
    if not backend_access_enabled():
        return True
    expected = (settings.backend_access_key or "").strip()
    supplied = (provided or "").strip()
    if not expected or not supplied:
        return False
    if supplied.startswith("bat1:"):
        try:
            _, timestamp, signature = supplied.split(":", 2)
            issued_at = int(timestamp)
        except (TypeError, ValueError):
            return False
        max_age = max(300, settings.access_token_expire_minutes * 60)
        now = int(time.time())
        if issued_at > now + 60 or now - issued_at > max_age:
            return False
        expected_signature = hmac.new(
            settings.secret_key.encode("utf-8"),
            f"backend-access:{timestamp}:{expected}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return secrets.compare_digest(signature, expected_signature)
    return secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


def create_backend_access_cookie_token() -> str:
    """Cria prova temporÃ¡ria sem guardar a chave compartilhada no navegador."""
    if not backend_access_enabled():
        return ""
    timestamp = str(int(time.time()))
    expected = (settings.backend_access_key or "").strip()
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        f"backend-access:{timestamp}:{expected}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"bat1:{timestamp}:{signature}"


@lru_cache(maxsize=1)
def _master_salt() -> bytes:
    fixed = (settings.data_encryption_salt or "").strip()
    if fixed:
        return hashlib.sha256(fixed.encode("utf-8")).digest()
    path = settings.data_path("data") / ".crypto_salt"
    if path.is_file():
        return path.read_bytes()[:32]
    salt = secrets.token_bytes(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(salt)
    return salt


@lru_cache(maxsize=1)
def _derive_keys() -> tuple[bytes, bytes, bytes]:
    """Duas chaves AES + chave HMAC para índices de busca."""
    pwd = (settings.data_encryption_password or "").strip().encode("utf-8")
    salt = _master_salt()
    kdf1 = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt + b"layer1",
        iterations=_PBKDF2_ITERS,
    )
    kdf2 = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt + b"layer2",
        iterations=_PBKDF2_ITERS,
    )
    kdfh = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt + b"hash",
        iterations=_PBKDF2_ITERS,
    )
    return kdf1.derive(pwd), kdf2.derive(pwd), kdfh.derive(pwd)


def _encrypt_layer(data: bytes, key: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, data, None)
    return nonce + ct


def _decrypt_layer(blob: bytes, key: bytes) -> bytes:
    if len(blob) < 13:
        raise ValueError("blob cifrado inválido")
    nonce, ct = blob[:12], blob[12:]
    return AESGCM(key).decrypt(nonce, ct, None)


def encrypt_field(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    text = str(plaintext)
    if not text:
        return text
    if not encryption_enabled():
        return text
    if text.startswith(ENC_PREFIX):
        return text
    k1, k2, _ = _derive_keys()
    layer1 = _encrypt_layer(text.encode("utf-8"), k1)
    layer2 = _encrypt_layer(layer1, k2)
    return ENC_PREFIX + base64.urlsafe_b64encode(layer2).decode("ascii")


def decrypt_field(stored: str | None) -> str | None:
    if stored is None:
        return None
    if not stored or not encryption_enabled():
        return stored
    if not stored.startswith(ENC_PREFIX):
        return stored
    k1, k2, _ = _derive_keys()
    raw = base64.urlsafe_b64decode(stored[len(ENC_PREFIX) :].encode("ascii"))
    layer1 = _decrypt_layer(raw, k2)
    plain = _decrypt_layer(layer1, k1)
    return plain.decode("utf-8")


@lru_cache(maxsize=8)
def _derive_soc_keys(chave_soc: str) -> tuple[bytes, bytes, bytes]:
    pwd = chave_soc.strip().encode("utf-8")
    salt = hashlib.sha256(b"terra_fertil_soc_emergency_v1").digest()
    kdf1 = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt + b"soc1",
        iterations=_PBKDF2_ITERS,
    )
    kdf2 = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt + b"soc2",
        iterations=_PBKDF2_ITERS,
    )
    kdfh = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt + b"sochash",
        iterations=_PBKDF2_ITERS,
    )
    return kdf1.derive(pwd), kdf2.derive(pwd), kdfh.derive(pwd)


def soc_key_fingerprint(chave_soc: str) -> str:
    """Impressão digital da chave SOC (não armazena a chave)."""
    chave = chave_soc.strip()
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        f"soc:{chave}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_soc_key(chave_soc: str, verifier: str | None) -> bool:
    if not verifier:
        return False
    return secrets.compare_digest(soc_key_fingerprint(chave_soc), verifier)


def encrypt_field_soc(plaintext: str | None, chave_soc: str) -> str | None:
    if plaintext is None:
        return None
    text = str(plaintext)
    if not text:
        return text
    if text.startswith(SOC_PREFIX):
        return text
    k1, k2, _ = _derive_soc_keys(chave_soc)
    layer1 = _encrypt_layer(text.encode("utf-8"), k1)
    layer2 = _encrypt_layer(layer1, k2)
    return SOC_PREFIX + base64.urlsafe_b64encode(layer2).decode("ascii")


def decrypt_field_soc(stored: str | None, chave_soc: str) -> str | None:
    if stored is None:
        return None
    if not stored or not stored.startswith(SOC_PREFIX):
        return stored
    k1, k2, _ = _derive_soc_keys(chave_soc)
    raw = base64.urlsafe_b64decode(stored[len(SOC_PREFIX) :].encode("ascii"))
    layer1 = _decrypt_layer(raw, k2)
    plain = _decrypt_layer(layer1, k1)
    return plain.decode("utf-8")


def field_hash_soc(value: str | None, kind: str, chave_soc: str) -> str | None:
    if not value or not str(value).strip():
        return None
    _, _, hkey = _derive_soc_keys(chave_soc)
    normalized = str(value).strip().lower() if kind == "email" else "".join(
        c for c in str(value) if c.isdigit()
    )
    if not normalized:
        return None
    msg = f"soc:{kind}:{normalized}".encode("utf-8")
    return hmac.new(hkey, msg, hashlib.sha256).hexdigest()


def decrypt_field_any(stored: str | None, *, chave_soc: str | None = None) -> str | None:
    """Decifra enc2, soc2 (com chave) ou devolve texto claro."""
    if stored is None:
        return None
    if not stored:
        return stored
    if stored.startswith(SOC_PREFIX):
        if not chave_soc:
            raise ValueError("Chave SOC necessária para decifrar dados em modo SOC")
        return decrypt_field_soc(stored, chave_soc)
    if stored.startswith(ENC_PREFIX):
        return decrypt_field(stored)
    return stored


def field_hash(value: str | None, kind: str) -> str | None:
    """Hash determinístico para busca (CPF, CNPJ, e-mail) sem expor o valor."""
    if not value or not str(value).strip():
        return None
    if not encryption_enabled():
        return None
    _, _, hkey = _derive_keys()
    normalized = str(value).strip().lower() if kind == "email" else "".join(
        c for c in str(value) if c.isdigit()
    )
    if not normalized:
        return None
    msg = f"{kind}:{normalized}".encode("utf-8")
    return hmac.new(hkey, msg, hashlib.sha256).hexdigest()
