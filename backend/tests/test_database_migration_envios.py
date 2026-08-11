from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, inspect

from app import database


class EnvioRuntimeMigrationTests(unittest.TestCase):
    def test_adiciona_snapshot_e_cadeia_com_indice_unico_de_forma_idempotente(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE TABLE envios ("
                    "id INTEGER PRIMARY KEY, "
                    "idempotency_key VARCHAR(64), "
                    "provider_message_id VARCHAR(255)"
                    ")"
                )
            with patch.object(database, "engine", engine):
                database._migrate_envios_columns()
                database._migrate_envios_columns()

            inspector = inspect(engine)
            columns = {column["name"] for column in inspector.get_columns("envios")}
            self.assertIn("destinatario_email", columns)
            self.assertIn("reenvio_de_id", columns)
            indexes = {index["name"]: index for index in inspector.get_indexes("envios")}
            self.assertTrue(indexes["ix_envios_reenvio_de_id"]["unique"])
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
