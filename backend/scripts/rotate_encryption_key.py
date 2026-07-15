"""Rotaciona DATA_ENCRYPTION_PASSWORD offline, com backup e operaÃ§Ã£o atÃ´mica."""
from __future__ import annotations

import argparse
import getpass
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import BASE_DIR, settings
from app.services import data_crypto_service as crypto


SENSITIVE_FIELDS = ("nome", "email", "cpf", "cnpj", "telefone", "observacoes")


def _database_path() -> Path:
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        raise SystemExit("A rotaÃ§Ã£o offline atualmente suporta somente SQLite.")
    path = Path(url.removeprefix("sqlite:///"))
    return path.resolve() if path.is_absolute() else (BASE_DIR / path).resolve()


def _replace_env_value(content: str, key: str, value: str) -> str:
    lines = content.splitlines()
    replacement = f"{key}={value}"
    for index, line in enumerate(lines):
        if line.strip().lower().startswith(key.lower() + "="):
            lines[index] = replacement
            break
    else:
        lines.append(replacement)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-offline",
        action="store_true",
        help="Confirma que EnvioApolices-API estÃ¡ parado e nÃ£o hÃ¡ outro acesso ao banco.",
    )
    args = parser.parse_args()
    if not args.confirm_offline:
        raise SystemExit(
            "Pare o serviÃ§o EnvioApolices-API e execute novamente com --confirm-offline."
        )
    if not settings.data_encryption_enabled:
        raise SystemExit("DATA_ENCRYPTION_ENABLED precisa estar ativo.")

    new_password = getpass.getpass("Nova senha mestra (mÃ­nimo 16 caracteres): ").strip()
    confirmation = getpass.getpass("Confirme a nova senha: ").strip()
    if new_password != confirmation:
        raise SystemExit("As senhas nÃ£o coincidem.")
    if len(new_password) < 16:
        raise SystemExit("A nova senha precisa ter pelo menos 16 caracteres.")
    if new_password == settings.data_encryption_password:
        raise SystemExit("A nova senha deve ser diferente da atual.")

    db_path = _database_path()
    env_path = BASE_DIR / ".env"
    if not db_path.is_file() or not env_path.is_file():
        raise SystemExit("Banco SQLite ou .env nÃ£o encontrado.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BASE_DIR / "data" / "rotation-backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    db_backup = backup_dir / "envio.db"
    env_backup = backup_dir / ".env"
    salt_path = BASE_DIR / "data" / ".crypto_salt"
    shutil.copy2(env_path, env_backup)
    if salt_path.is_file():
        shutil.copy2(salt_path, backup_dir / ".crypto_salt")

    connection = sqlite3.connect(db_path)
    try:
        soc = connection.execute(
            "SELECT COALESCE(soc_mode_active, 0) FROM runtime_config WHERE id=1"
        ).fetchone()
        if soc and soc[0]:
            raise SystemExit("Desative o modo SOC antes de rotacionar a chave mestra.")
        with sqlite3.connect(db_backup) as backup_connection:
            connection.backup(backup_connection)

        columns = ", ".join(("id", *SENSITIVE_FIELDS))
        rows = connection.execute(f"SELECT {columns} FROM clientes").fetchall()
        plaintext_rows: list[tuple[int, dict[str, str | None]]] = []
        for row in rows:
            values: dict[str, str | None] = {}
            for field, stored in zip(SENSITIVE_FIELDS, row[1:]):
                if isinstance(stored, str) and stored.startswith(crypto.SOC_PREFIX):
                    raise SystemExit("Foram encontrados dados SOC. Desative o modo SOC primeiro.")
                values[field] = crypto.decrypt_field(stored)
            plaintext_rows.append((row[0], values))

        old_password = settings.data_encryption_password
        settings.data_encryption_password = new_password
        crypto._derive_keys.cache_clear()
        encrypted_rows = []
        for client_id, values in plaintext_rows:
            encrypted_rows.append(
                (
                    *(crypto.encrypt_field(values[field]) for field in SENSITIVE_FIELDS),
                    crypto.field_hash(values["cpf"], "cpf"),
                    crypto.field_hash(values["cnpj"], "cnpj"),
                    crypto.field_hash(values["email"], "email"),
                    client_id,
                )
            )

        original_env = env_path.read_text(encoding="utf-8-sig")
        next_env = _replace_env_value(
            original_env,
            "DATA_ENCRYPTION_PASSWORD",
            new_password,
        )
        temp_env = env_path.with_name(".env.rotation-new")
        temp_env.write_text(next_env, encoding="utf-8")
        db_committed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                "UPDATE clientes SET nome=?, email=?, cpf=?, cnpj=?, telefone=?, "
                "observacoes=?, cpf_hash=?, cnpj_hash=?, email_hash=? WHERE id=?",
                encrypted_rows,
            )
            connection.commit()
            db_committed = True
            os.replace(temp_env, env_path)
        except Exception:
            connection.rollback()
            if db_committed:
                with sqlite3.connect(db_backup) as backup_connection:
                    backup_connection.backup(connection)
            temp_env.unlink(missing_ok=True)
            settings.data_encryption_password = old_password
            crypto._derive_keys.cache_clear()
            raise
    finally:
        connection.close()

    print(f"Chave rotacionada para {len(plaintext_rows)} cliente(s).")
    print(f"Backup de recuperaÃ§Ã£o: {backup_dir}")
    print("Inicie novamente o serviÃ§o EnvioApolices-API e valide os clientes.")


if __name__ == "__main__":
    main()
