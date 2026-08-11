from __future__ import annotations

import asyncio
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.routers import envios as envios_router
from app.services import envio_service, lgpd_service


async def _corpo_streaming(response) -> str:
    partes: list[bytes] = []
    async for parte in response.body_iterator:
        partes.append(parte.encode("utf-8") if isinstance(parte, str) else parte)
    return b"".join(partes).decode("utf-8")


class EnvioFluxoTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self._temp.name)
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, future=True)()
        self.cliente = models.Cliente(
            nome="Cliente Teste",
            email="cliente@example.com",
        )
        self.db.add(self.cliente)
        self.db.commit()
        self.db.refresh(self.cliente)
        self.pdf = self.temp_dir / "apolice.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nconteudo")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self._temp.cleanup()

    def _patch_fluxo(self, *, backup_side_effect=None, smtp_side_effect=None):
        stack = ExitStack()
        stack.enter_context(
            patch.object(
                envio_service.soc_service,
                "is_soc_locked",
                return_value=False,
            )
        )
        stack.enter_context(
            patch.object(
                envio_service.pdf_service,
                "garantir_pdf_desbloqueado",
                return_value=(self.pdf, None),
            )
        )
        stack.enter_context(
            patch.object(
                envio_service,
                "_preparar_pdf_final",
                return_value=(self.pdf, self.pdf.name, None),
            )
        )
        stack.enter_context(
            patch.object(envio_service, "_resolver_assinatura", return_value=None)
        )
        stack.enter_context(
            patch.object(envio_service.email_service, "formatar_assunto", return_value="Assunto")
        )
        stack.enter_context(
            patch.object(
                envio_service.email_service,
                "renderizar_template",
                return_value="<p>Oi</p>",
            )
        )
        backup = stack.enter_context(
            patch.object(envio_service.backup_service, "copiar_para_backup")
        )
        if backup_side_effect is None:
            backup.return_value = self.pdf
        else:
            backup.side_effect = backup_side_effect
        smtp = stack.enter_context(
            patch.object(envio_service.email_service, "enviar_email")
        )
        if smtp_side_effect is None:
            smtp.return_value = "<message@example.com>"
        else:
            smtp.side_effect = smtp_side_effect
        return stack, backup, smtp

    def test_manual_repetido_dispara_duas_vezes_e_nao_tem_chave(self):
        stack, _backup, smtp = self._patch_fluxo()
        with stack:
            primeiro = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="MANUAL",
            )
            segundo = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="MANUAL",
            )

        self.assertNotEqual(primeiro.id, segundo.id)
        self.assertIsNone(primeiro.idempotency_key)
        self.assertIsNone(segundo.idempotency_key)
        self.assertEqual(smtp.call_count, 2)
        self.assertFalse(primeiro.deduplicado)
        self.assertFalse(segundo.deduplicado)

    def test_lgpd_remove_toda_a_cadeia_de_reenvio(self):
        origem = models.Envio(
            cliente_id=self.cliente.id,
            tipo_envio="MANUAL",
            status="erro",
        )
        self.db.add(origem)
        self.db.commit()
        filho = models.Envio(
            cliente_id=self.cliente.id,
            tipo_envio="MANUAL",
            status="enviado",
            reenvio_de_id=origem.id,
        )
        self.db.add(filho)
        self.db.commit()

        resultado = lgpd_service.excluir_cliente_lgpd(
            self.db,
            self.cliente.id,
            confirmar_nome="Cliente Teste",
            remover_backups=False,
        )

        self.assertEqual(resultado["envios_removidos"], 2)
        self.assertEqual(self.db.query(models.Envio).count(), 0)
        self.assertIsNone(self.db.get(models.Cliente, self.cliente.id))

    def test_full_deduplica_email_equivalente_mas_nao_email_alterado(self):
        stack, _backup, smtp = self._patch_fluxo()
        with stack:
            primeiro = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="FULL",
                tipo_codigo="auto",
            )
            self.cliente.email = "  CLIENTE@example.COM  "
            segundo = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="FULL",
                tipo_codigo="auto",
            )
            self.cliente.email = "corrigido@example.com"
            terceiro = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="FULL",
                tipo_codigo="auto",
            )

        self.assertEqual(primeiro.id, segundo.id)
        self.assertTrue(segundo.deduplicado)
        self.assertNotEqual(primeiro.id, terceiro.id)
        self.assertEqual(smtp.call_count, 2)
        self.assertEqual(primeiro.destinatario_email, "cliente@example.com")
        self.assertEqual(terceiro.destinatario_email, "corrigido@example.com")

    def test_falha_backup_cria_copia_recuperavel_e_nao_chama_smtp(self):
        recovery_root = self.temp_dir / "uploads"
        stack, _backup, smtp = self._patch_fluxo(
            backup_side_effect=OSError("backup indisponivel")
        )
        with stack, patch.object(
            envio_service.settings, "upload_folder", str(recovery_root)
        ):
            envio = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="MANUAL",
            )

        self.assertEqual(envio.status, "erro")
        self.assertEqual(envio._erro_etapa, "backup")
        self.assertTrue(envio.caminho_backup)
        recuperado = Path(envio.caminho_backup)
        self.assertTrue(recuperado.is_file())
        self.assertEqual(recuperado.read_bytes(), self.pdf.read_bytes())
        self.assertTrue(envio_service.envio_pode_reenviar(envio))
        smtp.assert_not_called()

    def test_falha_smtp_fica_reenviavel_e_mapeia_http_502(self):
        stack, _backup, _smtp = self._patch_fluxo(
            smtp_side_effect=OSError("relay indisponivel")
        )
        with stack:
            envio = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="MANUAL",
            )

        erro = envios_router._falha_envio_http(envio, envio._erro_etapa)
        self.assertEqual(envio.status, "erro")
        self.assertEqual(erro.status_code, 502)
        self.assertEqual(erro.detail["code"], "smtp_send_failed")
        self.assertEqual(erro.detail["envio_id"], envio.id)
        self.assertTrue(erro.detail["pode_reenviar"])

    def test_saida_usa_snapshot_e_nao_inventa_destinatario_legado(self):
        stack, _backup, _smtp = self._patch_fluxo()
        with stack:
            envio = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="MANUAL",
            )

        self.cliente.email = "alterado@example.com"
        saida = envios_router._envio_out(envio)
        self.assertEqual(saida.destinatario_email, "cliente@example.com")
        self.assertEqual(saida.cliente_email, "cliente@example.com")
        self.assertEqual(saida.cliente_email_atual, "alterado@example.com")

        envio.destinatario_email = None
        saida_legada = envios_router._envio_out(envio)
        self.assertIsNone(saida_legada.destinatario_email)
        self.assertIsNone(saida_legada.cliente_email)
        self.assertEqual(saida_legada.cliente_email_atual, "alterado@example.com")

    def test_reenvio_aceita_bounce_e_usa_email_atual_com_novo_snapshot(self):
        stack, _backup, smtp = self._patch_fluxo()
        with stack:
            envio = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="FULL",
            )
            envio.delivery_status = "hard_bounce"
            self.cliente.email = "corrigido@example.com"
            self.db.commit()
            atualizado = envio_service.reenviar_envio(self.db, envio.id)
            reapresentado = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="FULL",
            )

        self.assertEqual(atualizado.status, "enviado")
        self.assertNotEqual(atualizado.id, envio.id)
        self.assertEqual(atualizado.reenvio_de_id, envio.id)
        self.assertEqual(atualizado.delivery_status, "accepted")
        self.assertEqual(atualizado.destinatario_email, "corrigido@example.com")
        self.assertEqual(reapresentado.id, atualizado.id)
        self.assertTrue(reapresentado.deduplicado)
        self.assertTrue(atualizado.idempotency_key)
        self.assertEqual(envio.delivery_status, "hard_bounce")
        self.assertFalse(envio_service.envio_pode_reenviar(envio))
        self.assertEqual(smtp.call_count, 2)
        self.assertEqual(
            smtp.call_args.kwargs["destinatario"], "corrigido@example.com"
        )
        self.assertEqual(
            smtp.call_args.kwargs["tracking_id"], f"envio_id:{atualizado.id}"
        )

    def test_spam_bloqueia_reenvio_mesmo_com_status_erro_e_backup(self):
        stack, _backup, _smtp = self._patch_fluxo()
        with stack:
            envio = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="FULL",
            )
        envio.status = "erro"
        envio.delivery_status = "spam"
        self.db.commit()

        self.assertFalse(envio_service.envio_pode_reenviar(envio))
        with self.assertRaisesRegex(ValueError, "bloqueado"):
            envio_service.reenviar_envio(self.db, envio.id)

    def test_lote_reenvia_somente_folha_da_cadeia(self):
        stack, _backup, smtp = self._patch_fluxo()
        with stack:
            original = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="FULL",
            )
            original.delivery_status = "hard_bounce"
            self.db.commit()

            smtp.side_effect = OSError("falha no primeiro reenvio")
            primeira_tentativa = envio_service.reenviar_envio(
                self.db, original.id
            )
            self.assertEqual(primeira_tentativa.status, "erro")

            falha_manual = models.Envio(
                cliente_id=self.cliente.id,
                tipo_envio="MANUAL",
                status="erro",
                caminho_backup=str(self.pdf),
            )
            self.db.add(falha_manual)
            self.db.commit()

            smtp.side_effect = None
            smtp.return_value = "<retry-ok@example.com>"
            resultado = envio_service.reenviar_envios_com_erro(
                self.db, dias=30, tipo="FULL"
            )

        self.assertEqual(resultado["total"], 1)
        self.assertEqual(resultado["sucesso"], 1)
        tentativa_final = self.db.get(
            models.Envio, resultado["itens"][0]["envio_id"]
        )
        self.assertEqual(tentativa_final.reenvio_de_id, primeira_tentativa.id)
        self.assertEqual(tentativa_final.status, "enviado")
        self.assertFalse(
            self.db.query(models.Envio)
            .filter(models.Envio.reenvio_de_id == falha_manual.id)
            .first()
        )
        self.assertEqual(
            self.db.query(models.Envio)
            .filter(models.Envio.reenvio_de_id == original.id)
            .count(),
            1,
        )
        self.assertFalse(envio_service.envio_pode_reenviar(original))

    def test_full_consulta_folha_quando_chave_ainda_esta_na_raiz(self):
        stack, _backup, smtp = self._patch_fluxo()
        with stack:
            raiz = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="FULL",
            )
            raiz.delivery_status = "hard_bounce"
            self.db.commit()
            folha = envio_service.reenviar_envio(self.db, raiz.id)

            # Simula uma cadeia criada antes da transferência de chave para a
            # tentativa mais nova.
            chave = folha.idempotency_key
            folha.idempotency_key = None
            self.db.commit()
            raiz.idempotency_key = chave
            self.db.commit()

            reapresentado = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="FULL",
            )

        self.assertEqual(reapresentado.id, folha.id)
        self.assertTrue(reapresentado.deduplicado)
        self.assertEqual(smtp.call_count, 2)

    def test_full_nao_mistura_sucesso_de_outro_email_na_cadeia(self):
        stack, _backup, smtp = self._patch_fluxo()
        with stack:
            raiz = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="FULL",
            )
            raiz.delivery_status = "hard_bounce"
            self.cliente.email = "novo@example.com"
            self.db.commit()
            tentativa_novo_email = envio_service.reenviar_envio(self.db, raiz.id)

            self.cliente.email = "cliente@example.com"
            self.db.commit()
            tentativa_email_original = envio_service.processar_envio(
                self.db,
                cliente=self.cliente,
                caminho_pdf=self.pdf,
                tipo_envio="FULL",
            )

        self.assertNotEqual(tentativa_email_original.id, tentativa_novo_email.id)
        self.assertEqual(
            tentativa_email_original.destinatario_email,
            "cliente@example.com",
        )
        self.assertEqual(smtp.call_count, 3)

    def test_soc_bloqueia_reenvio_unitario_e_em_lote(self):
        envio = models.Envio(
            cliente_id=self.cliente.id,
            tipo_envio="MANUAL",
            status="erro",
            caminho_backup=str(self.pdf),
        )
        self.db.add(envio)
        self.db.commit()
        with patch.object(envio_service.soc_service, "is_soc_locked", return_value=True):
            with self.assertRaisesRegex(ValueError, "Modo SOC ativo"):
                envio_service.reenviar_envio(self.db, envio.id)
            with self.assertRaisesRegex(ValueError, "Modo SOC ativo"):
                envio_service.reenviar_envios_com_erro(self.db)

    def test_z_snapshot_e_cifrado_e_acompanha_modo_soc(self):
        # Import tardio: registra os eventos depois dos demais testes de fluxo,
        # permitindo validar separadamente o armazenamento bruto no SQLite.
        from app.events import cliente_crypto_events, envio_crypto_events  # noqa: F401
        from app.services import (
            cliente_crypto,
            data_crypto_service as crypto,
            envio_crypto,
            soc_service,
        )

        with (
            patch.object(crypto.settings, "data_encryption_enabled", True),
            patch.object(crypto.settings, "data_encryption_password", "senha-normal-teste"),
            patch.object(crypto.settings, "data_encryption_salt", "salt-fixo-teste"),
            patch.object(crypto.settings, "secret_key", "segredo-teste-com-32-caracteres-minimo"),
        ):
            crypto._derive_keys.cache_clear()
            envio = models.Envio(
                cliente_id=self.cliente.id,
                tipo_envio="MANUAL",
                status="enviado",
                destinatario_email="snapshot@example.com",
            )
            self.db.add(envio)
            self.db.commit()

            armazenado = self.db.connection().exec_driver_sql(
                "SELECT destinatario_email FROM envios WHERE id=?", (envio.id,)
            ).scalar_one()
            self.assertTrue(armazenado.startswith(crypto.ENC_PREFIX))
            self.assertEqual(envio_crypto.migrate_plaintext_envios(self.db), 0)
            armazenado_sem_recifrar = self.db.connection().exec_driver_sql(
                "SELECT destinatario_email FROM envios WHERE id=?", (envio.id,)
            ).scalar_one()
            self.assertEqual(armazenado_sem_recifrar, armazenado)
            self.db.expire(envio)
            self.assertEqual(envio.destinatario_email, "snapshot@example.com")

            soc_service.ativar_modo_soc(
                self.db,
                chave_soc="senha-soc-teste",
                motivo="teste",
            )
            armazenado_soc = self.db.connection().exec_driver_sql(
                "SELECT destinatario_email FROM envios WHERE id=?", (envio.id,)
            ).scalar_one()
            self.assertTrue(armazenado_soc.startswith(crypto.SOC_PREFIX))

            soc_service.desativar_modo_soc(
                self.db,
                chave_soc="senha-soc-teste",
            )
            armazenado_normal = self.db.connection().exec_driver_sql(
                "SELECT destinatario_email FROM envios WHERE id=?", (envio.id,)
            ).scalar_one()
            self.assertTrue(armazenado_normal.startswith(crypto.ENC_PREFIX))
            cliente_raw = self.db.connection().exec_driver_sql(
                "SELECT email FROM clientes WHERE id=?", (self.cliente.id,)
            ).scalar_one()
            self.assertTrue(cliente_raw.startswith(crypto.ENC_PREFIX))
            self.db.expire(envio)
            self.db.expire(self.cliente)
            self.assertEqual(envio.destinatario_email, "snapshot@example.com")
            self.assertEqual(self.cliente.email, "cliente@example.com")
            self.assertEqual(cliente_crypto.migrate_plaintext_clientes(self.db), 0)
            cliente_raw_sem_recifrar = self.db.connection().exec_driver_sql(
                "SELECT email FROM clientes WHERE id=?", (self.cliente.id,)
            ).scalar_one()
            self.assertEqual(cliente_raw_sem_recifrar, cliente_raw)

            self.cliente.email = "fluxo@example.com"
            self.db.commit()
            stack, backup, smtp_fluxo = self._patch_fluxo()
            with stack:
                envio_processado = envio_service.processar_envio(
                    self.db,
                    cliente=self.cliente,
                    caminho_pdf=self.pdf,
                    tipo_envio="MANUAL",
                )
            self.assertEqual(backup.call_args.args[1], "Cliente Teste")
            self.assertEqual(
                smtp_fluxo.call_args.kwargs["destinatario"], "fluxo@example.com"
            )
            self.assertEqual(
                envio_processado.destinatario_email, "fluxo@example.com"
            )
            snapshot_processado_raw = self.db.connection().exec_driver_sql(
                "SELECT destinatario_email FROM envios WHERE id=?",
                (envio_processado.id,),
            ).scalar_one()
            self.assertTrue(snapshot_processado_raw.startswith(crypto.ENC_PREFIX))

            envio.status = "erro"
            envio.delivery_status = "hard_bounce"
            envio.caminho_backup = str(self.pdf)
            self.cliente.email = "corrigido@example.com"
            self.db.commit()
            self.assertEqual(self.cliente.email, "corrigido@example.com")
            with (
                patch.object(envio_service, "_resolver_corpo_email", return_value=None),
                patch.object(envio_service, "_resolver_assinatura", return_value=None),
                patch.object(
                    envio_service.email_service,
                    "formatar_assunto",
                    return_value="Assunto",
                ),
                patch.object(
                    envio_service.email_service,
                    "renderizar_template",
                    return_value="<p>Oi</p>",
                ),
                patch.object(
                    envio_service.email_service,
                    "enviar_email",
                    return_value="<retry@example.com>",
                ) as smtp,
            ):
                reenviado = envio_service.reenviar_envio(self.db, envio.id)

            smtp.assert_called_once()
            self.assertEqual(
                smtp.call_args.kwargs["destinatario"], "corrigido@example.com"
            )
            self.assertEqual(
                reenviado.destinatario_email, "corrigido@example.com"
            )
            raw_reenvio = self.db.connection().exec_driver_sql(
                "SELECT destinatario_email FROM envios WHERE id=?", (reenviado.id,)
            ).scalar_one()
            self.assertTrue(raw_reenvio.startswith(crypto.ENC_PREFIX))
            self.assertEqual(
                crypto.decrypt_field(raw_reenvio), "corrigido@example.com"
            )

            saida_api = envios_router._envio_out(reenviado)
            self.assertEqual(
                saida_api.destinatario_email, "corrigido@example.com"
            )
            csv_response = envios_router.exportar_csv(
                dias=30,
                db=self.db,
                _=None,
            )
            csv_texto = asyncio.run(_corpo_streaming(csv_response))
            self.assertIn("corrigido@example.com", csv_texto)
            self.assertNotIn(crypto.ENC_PREFIX, csv_texto)
            crypto._derive_keys.cache_clear()


if __name__ == "__main__":
    unittest.main()
