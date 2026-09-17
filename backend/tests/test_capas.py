from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import settings
from app.database import Base
from app.services import capa_service, pdf_service


def _criar_pdf(path: Path, larguras: list[int], *, senha: str | None = None) -> None:
    writer = PdfWriter()
    for largura in larguras:
        writer.add_blank_page(width=largura, height=100)
    if senha:
        writer.encrypt(senha)
    with path.open("wb") as handle:
        writer.write(handle)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PdfComposicaoTests(unittest.TestCase):
    def test_mescla_n_pdfs_na_ordem_e_mantem_wrapper_legado(self):
        with tempfile.TemporaryDirectory() as directory:
            pasta = Path(directory)
            inicial_a = pasta / "inicial-a.pdf"
            inicial_b = pasta / "inicial-b.pdf"
            apolice = pasta / "apolice.pdf"
            final = pasta / "final.pdf"
            saida = pasta / "completo.pdf"
            _criar_pdf(inicial_a, [101])
            _criar_pdf(inicial_b, [201, 202])
            _criar_pdf(apolice, [301])
            _criar_pdf(final, [401])

            pdf_service.mesclar_pdfs(
                [inicial_a, inicial_b, apolice, final],
                saida,
            )

            reader = PdfReader(str(saida), strict=False)
            larguras = [int(page.mediabox.width) for page in reader.pages]
            self.assertEqual(larguras, [101, 201, 202, 301, 401])

            legado = pasta / "legado.pdf"
            pdf_service.mesclar_capa_e_apolice(inicial_a, apolice, legado)
            reader_legado = PdfReader(str(legado), strict=False)
            self.assertEqual(
                [int(page.mediabox.width) for page in reader_legado.pages],
                [101, 301],
            )

    def test_senha_remove_todo_whitespace_antes_de_abrir_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            pasta = Path(directory)
            protegido = pasta / "protegido.pdf"
            saida = pasta / "saida.pdf"
            _criar_pdf(protegido, [123], senha="abc123")

            self.assertEqual(
                pdf_service.normalizar_senha_pdf(" a b\tc\n1 2 3 "),
                "abc123",
            )
            pdf_service.mesclar_pdfs(
                [protegido],
                saida,
                senhas=[" a b\tc\n1 2 3 "],
            )
            self.assertEqual(len(PdfReader(str(saida)).pages), 1)

    def test_falha_ao_gravar_pdf_desbloqueado_remove_temporario(self):
        with tempfile.TemporaryDirectory() as directory:
            pasta = Path(directory)
            protegido = pasta / "protegido.pdf"
            _criar_pdf(protegido, [123], senha="abc123")

            with (
                patch.object(pdf_service.tempfile, "gettempdir", return_value=str(pasta)),
                patch.object(pdf_service.PdfWriter, "write", side_effect=OSError("disco")),
                self.assertRaises(OSError),
            ):
                pdf_service.garantir_pdf_desbloqueado(protegido, senha="abc123")

            self.assertEqual(list(pasta.glob("pdf_desbloqueado_*.pdf")), [])


class CapaServiceTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._temp.name)
        self._patch_capa_folder = patch.object(
            settings, "capa_folder", str(self.pasta)
        )
        self._patch_capa_folder.start()
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, future=True)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self._patch_capa_folder.stop()
        self._temp.cleanup()

    def _capa(self, nome: str, largura: int) -> models.CapaModelo:
        arquivo = self.pasta / f"{nome.lower()}.pdf"
        _criar_pdf(arquivo, [largura])
        capa = models.CapaModelo(
            nome=nome,
            arquivo=arquivo.name,
            nome_original=arquivo.name,
            tamanho_bytes=arquivo.stat().st_size,
            paginas=1,
            sha256=_sha(arquivo),
            ativo=True,
        )
        self.db.add(capa)
        self.db.commit()
        self.db.refresh(capa)
        return capa

    def test_resolve_heranca_ordem_e_lista_vazia_explicita(self):
        capa_a = self._capa("A", 100)
        capa_b = self._capa("B", 200)
        capa_final = self._capa("Final", 300)
        tipo = models.TipoEnvio(codigo="auto", nome="Auto")
        tipo.capas_iniciais_ids = [capa_b.id, capa_a.id]
        tipo.capas_finais_ids = [capa_final.id]
        self.db.add(tipo)
        self.db.commit()

        iniciais, finais = capa_service.resolver_listas(
            self.db,
            tipo_codigo="auto",
        )
        self.assertEqual([c.id for c in iniciais], [capa_b.id, capa_a.id])
        self.assertEqual([c.id for c in finais], [capa_final.id])

        iniciais, finais = capa_service.resolver_listas(
            self.db,
            tipo_codigo="auto",
            capas_iniciais_ids=[],
            capas_finais_ids=None,
        )
        self.assertEqual(iniciais, [])
        self.assertEqual([c.id for c in finais], [capa_final.id])

    def test_parse_limite_snapshots_e_fingerprint_consideram_ordem(self):
        capa_a = self._capa("A", 100)
        capa_b = self._capa("B", 200)

        self.assertEqual(
            capa_service.parse_ids_json(
                f"[{capa_b.id}, {capa_a.id}]", "capas_iniciais_ids"
            ),
            [capa_b.id, capa_a.id],
        )
        with self.assertRaises(capa_service.CapaServiceError):
            capa_service.parse_ids_json(
                list(range(1, capa_service.MAX_CAPAS_POR_LADO + 2)),
                "capas_iniciais_ids",
            )
        with self.assertRaises(capa_service.CapaServiceError):
            capa_service.parse_ids_json(
                [capa_a.id, capa_a.id], "capas_iniciais_ids"
            )

        self.assertEqual(
            capa_service.snapshots([capa_a]),
            [{"id": capa_a.id, "nome": "A", "sha256": capa_a.sha256}],
        )
        self.assertNotEqual(
            capa_service.fingerprint([capa_a, capa_b], []),
            capa_service.fingerprint([capa_b, capa_a], []),
        )
        self.assertNotEqual(
            capa_service.fingerprint([capa_a], [capa_b]),
            capa_service.fingerprint([capa_a, capa_b], []),
        )
        self.assertEqual(
            capa_service.fingerprint([capa_a], [capa_b]),
            capa_service.fingerprint_snapshots_json(
                capa_service.snapshots_json([capa_a]),
                capa_service.snapshots_json([capa_b]),
            ),
        )

    def test_exclusao_e_protegida_enquanto_tipo_referencia_capa(self):
        capa = self._capa("Obrigatoria", 100)
        tipo = models.TipoEnvio(codigo="rural", nome="Rural")
        tipo.capas_finais_ids = [capa.id]
        self.db.add(tipo)
        self.db.commit()

        with self.assertRaises(capa_service.CapaEmUsoError):
            capa_service.remover_modelo(self.db, capa.id)
        self.assertIsNotNone(self.db.get(models.CapaModelo, capa.id))
        self.assertTrue(capa_service.caminho_arquivo(capa).is_file())

    def test_importacao_legada_e_idempotente_e_nao_cria_associacao(self):
        legado = self.pasta / Path(settings.capa_arquivo_padrao).name
        _criar_pdf(legado, [100, 200])

        primeira = capa_service.importar_capa_legada(self.db)
        segunda = capa_service.importar_capa_legada(self.db)

        self.assertIsNotNone(primeira)
        self.assertEqual(primeira.id, segunda.id)
        self.assertNotEqual(primeira.arquivo, legado.name)
        self.assertTrue(legado.is_file())
        self.assertTrue(capa_service.caminho_arquivo(primeira).is_file())
        self.assertEqual(self.db.query(models.CapaModelo).count(), 1)
        self.assertEqual(self.db.query(models.TipoEnvio).count(), 0)


if __name__ == "__main__":
    unittest.main()
