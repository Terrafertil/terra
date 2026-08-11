from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch

from app.services import data_crypto_service as crypto
from scripts import rotate_encryption_key as rotate


class SnapshotRotationTests(unittest.TestCase):
    def test_snapshot_e_recifrado_com_a_nova_chave(self):
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE envios (id INTEGER PRIMARY KEY, destinatario_email TEXT)"
        )
        try:
            with (
                patch.object(crypto.settings, "data_encryption_enabled", True),
                patch.object(crypto.settings, "data_encryption_salt", "salt-rotacao-teste"),
                patch.object(crypto.settings, "data_encryption_password", "senha-antiga-teste"),
            ):
                crypto._master_salt.cache_clear()
                crypto._derive_keys.cache_clear()
                antigo = crypto.encrypt_field("destinatario@example.com")
                connection.execute(
                    "INSERT INTO envios (id, destinatario_email) VALUES (?, ?)",
                    (1, antigo),
                )
                connection.commit()

                plaintext = rotate._load_destinatarios_plaintext(connection)
                self.assertEqual(plaintext, [(1, "destinatario@example.com")])

                crypto.settings.data_encryption_password = "senha-nova-teste"
                crypto._derive_keys.cache_clear()
                novos = rotate._encrypt_destinatarios(plaintext)
                connection.executemany(
                    "UPDATE envios SET destinatario_email=? WHERE id=?",
                    novos,
                )
                connection.commit()

                armazenado = connection.execute(
                    "SELECT destinatario_email FROM envios WHERE id=1"
                ).fetchone()[0]
                self.assertTrue(armazenado.startswith(crypto.ENC_PREFIX))
                self.assertNotEqual(armazenado, antigo)
                self.assertEqual(
                    crypto.decrypt_field(armazenado),
                    "destinatario@example.com",
                )
        finally:
            crypto._master_salt.cache_clear()
            crypto._derive_keys.cache_clear()
            connection.close()


if __name__ == "__main__":
    unittest.main()
