"""Testes da extração de dados de apólices (texto / layouts)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import pdf_service


SOMPO_TEXTO = """
A T E N Ç Ã O !
PENHOR RURAL
APÓLICE DE SEGURO Nº 6200159735 VIGÊNCIA: 24/07/2026 A 24/07/2027
CONFIRA ABAIXO AS SUAS INFORMAÇÕES CADASTRAIS:
NOME: UESLEY AUGUSTO SILVA
CPF/CNPJ: 096.961.576-06 TELEFONE: 38 0099637373
ENDEREÇO: FAZEND, 0
A Sompo e empresas de seu grupo econômico tem o compromisso de proteger
É com satisfação que encaminhamos sua apólice
deveria comunicar
APÓLICE DE SEGURO − N° 6200159735
SOMPO SEGUROS S.A. 61.383.493/0001-80 5720
PROCESSO INTERNO APÓLICE Nº APÓLICE ANTERIOR
2620098728 6200159735 0000000000
"""


class ExtracaoPdfTests(unittest.TestCase):
    def test_candidato_rejeita_palavra_dever(self):
        self.assertFalse(pdf_service._candidato_apolice_ok("dever"))
        self.assertFalse(pdf_service._candidato_apolice_ok("ANTERIOR"))
        self.assertTrue(pdf_service._candidato_apolice_ok("6200159735"))

    def test_sompo_extrai_dados_principais(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            path = Path(tmp.name)
        self.addCleanup(path.unlink, missing_ok=True)

        with patch.object(
            pdf_service,
            "_ler_texto_pdf",
            return_value=(SOMPO_TEXTO, False, False),
        ):
            dados = pdf_service.extrair_dados(path, usar_ocr=False)

        self.assertEqual(dados.layout, pdf_service.LAYOUT_SOMPO)
        self.assertEqual(dados.seguradora, "Sompo")
        self.assertEqual(dados.numero_apolice, "6200159735")
        self.assertEqual(dados.cpf, "09696157606")
        self.assertIsNone(dados.cnpj)  # CNPJ da Sompo não é do segurado
        self.assertIn("UESLEY", (dados.nome or "").upper())
        self.assertTrue(dados.telefone)

    def test_apolice_pelo_nome_do_arquivo(self):
        self.assertEqual(
            pdf_service._apolice_do_nome_arquivo("6200159735-0-Via Segurado.pdf"),
            "6200159735",
        )

    def test_nao_captura_dever_no_texto_generico(self):
        texto = "encaminhamos sua apólice\ndeveria comunicar o corretor APÓLICE: 99887766"
        self.assertEqual(pdf_service._extrair_apolice_do_texto(texto), "99887766")


if __name__ == "__main__":
    unittest.main()
