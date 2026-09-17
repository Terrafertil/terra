from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import database, models
from app.database import Base


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

    def test_migra_assunto_legado_do_corpo_para_o_tipo(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        try:
            Base.metadata.create_all(engine)
            db = sessionmaker(bind=engine, future=True)()
            corpo = models.CorpoEmail(
                nome="Corpo Auto",
                assunto="Apolice {numero_apolice}",
                html="<p>Oi</p>",
            )
            db.add(corpo)
            db.commit()
            corpo_id = corpo.id
            db.close()

            with engine.begin() as connection:
                connection.execute(text("DROP TABLE tipos_envio"))
                connection.execute(
                    text(
                        "CREATE TABLE tipos_envio ("
                        "id INTEGER PRIMARY KEY, codigo VARCHAR(60) NOT NULL UNIQUE, "
                        "nome VARCHAR(120) NOT NULL, descricao VARCHAR(255), "
                        "ordem INTEGER, na_fila_full BOOLEAN, corpo_email_id INTEGER, "
                        "ativo BOOLEAN, created_at DATETIME, updated_at DATETIME, "
                        "FOREIGN KEY(corpo_email_id) REFERENCES corpos_email(id))"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO tipos_envio "
                        "(codigo, nome, ordem, na_fila_full, corpo_email_id, ativo, "
                        "created_at, updated_at) VALUES "
                        "('auto', 'Auto', 1, 1, :corpo_id, 1, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"corpo_id": corpo_id},
                )
            with patch.object(database, "engine", engine):
                database._migrate_assuntos_email()
                database._migrate_assuntos_email()

            inspector = inspect(engine)
            columns = {
                column["name"]
                for column in inspector.get_columns("tipos_envio")
            }
            self.assertIn("assunto_email_id", columns)
            with engine.connect() as connection:
                linha = connection.execute(
                    text(
                        "SELECT a.assunto FROM tipos_envio t "
                        "JOIN assuntos_email a ON a.id = t.assunto_email_id "
                        "WHERE t.codigo = 'auto'"
                    )
                ).one()
                quantidade = connection.execute(
                    text("SELECT COUNT(*) FROM assuntos_email")
                ).scalar_one()
            self.assertEqual(linha[0], "Apolice {numero_apolice}")
            self.assertEqual(quantidade, 1)
        finally:
            engine.dispose()

    def test_alembic_0003_atualiza_sqlite_legado_diretamente(self):
        with TemporaryDirectory(prefix="terra-alembic-assuntos-") as tmp:
            db_path = Path(tmp) / "legado.db"
            engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
            try:
                Base.metadata.create_all(engine)
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO corpos_email "
                            "(nome, assunto, html, ativo, created_at, updated_at) "
                            "VALUES ('Corpo Auto', 'Apolice {numero_apolice}', "
                            "'<p>Oi</p>', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                        )
                    )
                    corpo_id = connection.execute(
                        text("SELECT id FROM corpos_email WHERE nome = 'Corpo Auto'")
                    ).scalar_one()
                    # Simula de fato o schema na revisão 0002, antes das novas
                    # colunas do compositor (Base.metadata já representa o head).
                    connection.execute(text("DROP TABLE envios"))
                    connection.execute(
                        text(
                            "CREATE TABLE envios ("
                            "id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL, "
                            "tipo_envio VARCHAR(20) NOT NULL, "
                            "destinatario_email VARCHAR(1024), reenvio_de_id INTEGER)"
                        )
                    )
                    connection.execute(text("DROP TABLE tipos_envio"))
                    connection.execute(text("DROP TABLE assuntos_email"))
                    connection.execute(
                        text(
                            "CREATE TABLE tipos_envio ("
                            "id INTEGER PRIMARY KEY, codigo VARCHAR(60) NOT NULL UNIQUE, "
                            "nome VARCHAR(120) NOT NULL, descricao VARCHAR(255), "
                            "ordem INTEGER, na_fila_full BOOLEAN, corpo_email_id INTEGER, "
                            "ativo BOOLEAN, created_at DATETIME, updated_at DATETIME, "
                            "FOREIGN KEY(corpo_email_id) REFERENCES corpos_email(id))"
                        )
                    )
                    connection.execute(
                        text(
                            "INSERT INTO tipos_envio "
                            "(codigo, nome, ordem, na_fila_full, corpo_email_id, ativo, "
                            "created_at, updated_at) VALUES "
                            "('auto', 'Auto', 1, 1, :corpo_id, 1, "
                            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                        ),
                        {"corpo_id": corpo_id},
                    )
                    connection.execute(
                        text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                    )
                    connection.execute(
                        text(
                            "INSERT INTO alembic_version (version_num) "
                            "VALUES ('20260811_0002')"
                        )
                    )
            finally:
                engine.dispose()

            cfg = Config(str(database.BASE_DIR / "alembic.ini"))
            cfg.set_main_option(
                "script_location", str(database.BASE_DIR / "alembic")
            )
            cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
            command.upgrade(cfg, "head")

            migrated = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
            try:
                inspector = inspect(migrated)
                self.assertIn("assuntos_email", inspector.get_table_names())
                self.assertIn("capas_modelos", inspector.get_table_names())
                self.assertIn(
                    "assunto_email_id",
                    {column["name"] for column in inspector.get_columns("tipos_envio")},
                )
                self.assertTrue(
                    {
                        "forma_pagamento",
                        "parcelamento",
                        "numero_proposta",
                        "item_segurado",
                        "capas_iniciais_json",
                        "capas_finais_json",
                        "destinatarios_manuais_qtd",
                    }.issubset(
                        {
                            column["name"]
                            for column in inspector.get_columns("envios")
                        }
                    )
                )
                with migrated.connect() as connection:
                    self.assertEqual(
                        connection.execute(
                            text("SELECT version_num FROM alembic_version")
                        ).scalar_one(),
                        "20260825_0004",
                    )
                    self.assertEqual(
                        connection.execute(
                            text(
                                "SELECT a.assunto FROM tipos_envio t "
                                "JOIN assuntos_email a ON a.id = t.assunto_email_id "
                                "WHERE t.codigo = 'auto'"
                            )
                        ).scalar_one(),
                        "Apolice {numero_apolice}",
                    )
            finally:
                migrated.dispose()


if __name__ == "__main__":
    unittest.main()
