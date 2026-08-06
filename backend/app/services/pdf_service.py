"""Extração de dados de PDFs de apólice.

Modelos suportados (pasta ``Modelos/`` de referência):
- **tokio_marine** — Tokio Marine Auto/Moto (GRP_AUS_ONLINE)
- **yelum_casco** — Apólice Ramo 31 Automóvel Casco (Quadient/Yelum)
- **sompo** — Sompo Penhor Rural / apólice de seguro
- **capa_terrafertil** — Capa institucional Terra Fértil (não é apólice)
- **porto_sulamerica_criptografado** — PDF protegido (ex.: S53101…)
- **sem_texto** — PDF só imagem / impressão sem camada de texto

Estratégia:
1. Lê texto (pdfplumber; se encriptado, tenta desbloquear com pypdf).
2. Identifica o layout.
3. Extrai CPF/CNPJ/nº apólice/nome/telefone com regras do layout + genéricas.
"""
from __future__ import annotations

import re
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber
from pypdf import PdfReader, PdfWriter


class PdfRequerSenhaError(ValueError):
    """PDF protegido e nenhuma senha foi informada."""


class PdfSenhaInvalidaError(ValueError):
    """Senha informada não desbloqueia o PDF."""


# ====== Regex genéricos ======
RE_CPF = re.compile(r"\b(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})\b")
RE_CNPJ = re.compile(r"\b(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})\b")
RE_DOC_CPF_CNPJ = re.compile(
    r"CPF\s*/\s*CNPJ\s*:?\s*"
    r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})",
    re.IGNORECASE,
)
RE_CPF_ROTULO = re.compile(
    r"CPF(?:\s*/\s*CNPJ)?\s*:?\s*(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})",
    re.IGNORECASE,
)
RE_CNPJ_ROTULO = re.compile(
    r"(?<![/\w])CNPJ\s*:?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})",
    re.IGNORECASE,
)
RE_NOME_ROTULO = re.compile(
    r"(?:NOME(?:\s+DO\s+SEGURADO)?|SEGURADO\(A\))\s*:?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç\s.'-]{2,80})",
    re.IGNORECASE,
)
RE_TELEFONE_ROTULO = re.compile(
    r"TELEFONE\s*:?\s*(\(?\d{2}\)?[\s\-]*\d{8,11})",
    re.IGNORECASE,
)

# Prioridade: formatos explícitos com número (evita capturar "dever", "ANTERIOR", etc.)
RE_APOLICE_PRIORITARIAS = [
    re.compile(
        r"AP[ÓO]LICE\s+DE\s+SEGURO\s*[−\-–]?\s*N\s*[º°o\.]*\s*(\d{6,20})",
        re.IGNORECASE,
    ),
    re.compile(
        r"AP[ÓO]LICE\s+DE\s+SEGURO\s*N[º°o\.]\s*(\d{6,20})",
        re.IGNORECASE,
    ),
    re.compile(
        r"N\s*[º°o\.]\s*(?:DA\s+)?AP[ÓO]LICE\s*[:\s]*(\d{6,20})",
        re.IGNORECASE,
    ),
    re.compile(
        r"AP[ÓO]LICE\s*N[º°o\.]\s*(\d{6,20})",
        re.IGNORECASE,
    ),
    re.compile(
        r"AP[ÓO]LICE\s*[:#]\s*(\d{5,20})",
        re.IGNORECASE,
    ),
    re.compile(
        r"policy\s*(?:number|no\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\./]{4,30})",
        re.IGNORECASE,
    ),
]

# Tokio Marine: "Ramo: 05.31 Apólice: 06548820"
RE_TOKIO_APOLICE = re.compile(
    r"Ramo:\s*[\d.]+\s*Ap[óo]lice:\s*(\d{5,12})",
    re.IGNORECASE,
)
RE_TOKIO_BARCODE = re.compile(r"^1N\d{11}(\d{8,12})", re.MULTILINE)

# Yelum: "31.09.2026.0907318" na seção DADOS DA APOLICE
RE_YELUM_APOLICE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4}\.\d{7,10})\b")

# Palavras que o regex antigo capturava por engano após "apólice"
APOLICE_STOPWORDS = frozenset(
    {
        "dever",
        "anterior",
        "condi",
        "declaro",
        "conforme",
        "seguro",
        "seguinte",
        "renovada",
        "endosso",
        "nova",
        "atual",
        "vigente",
        "abaixo",
        "acima",
        "deste",
        "desta",
        "neste",
        "nesta",
        "para",
        "com",
        "sem",
        "por",
    }
)

LAYOUT_DESCONHECIDO = "desconhecido"
LAYOUT_TOKIO = "tokio_marine"
LAYOUT_YELUM = "yelum_casco"
LAYOUT_SOMPO = "sompo"
LAYOUT_CAPA = "capa_terrafertil"
LAYOUT_CRIPTO = "porto_sulamerica_criptografado"
LAYOUT_SEM_TEXTO = "sem_texto"


@dataclass
class DadosPDF:
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    numero_apolice: Optional[str] = None
    nome: Optional[str] = None
    telefone: Optional[str] = None
    texto_completo: str = ""
    layout: str = LAYOUT_DESCONHECIDO
    seguradora: Optional[str] = None
    produto: Optional[str] = None  # auto, moto, casco, etc.
    avisos: list[str] = field(default_factory=list)
    extracao_automatica: bool = True
    ocr_usado: bool = False
    amostra_texto: str = ""
    requer_senha: bool = False
    senha_invalida: bool = False

    def as_dict(self) -> dict:
        return {
            "cpf": self.cpf,
            "cnpj": self.cnpj,
            "numero_apolice": self.numero_apolice,
            "nome": self.nome,
            "telefone": self.telefone,
            "layout": self.layout,
            "seguradora": self.seguradora,
            "produto": self.produto,
            "avisos": self.avisos,
            "extracao_automatica": self.extracao_automatica,
            "ocr_usado": self.ocr_usado,
            "amostra_texto": self.amostra_texto,
            "requer_senha": self.requer_senha,
            "senha_invalida": self.senha_invalida,
        }


def _limpar_doc(doc: str) -> str:
    return re.sub(r"\D", "", doc)


def pdf_esta_criptografado(caminho: str | Path) -> bool:
    try:
        r = PdfReader(str(caminho), strict=False)
        return bool(r.is_encrypted)
    except Exception:
        return False


def ler_senha_arquivo_auxiliar(caminho_pdf: Path) -> str | None:
    """Modo FULL: senha em ficheiro ao lado do PDF (uma linha, só uso interno).

    Nomes aceites: ``apolice.pdf.senha`` ou ``apolice.senha.txt`` (mesma pasta).
    """
    caminho_pdf = Path(caminho_pdf)
    candidatos = [
        Path(str(caminho_pdf) + ".senha"),
        caminho_pdf.with_name(caminho_pdf.stem + ".senha.txt"),
        caminho_pdf.with_name(caminho_pdf.stem + ".senha"),
    ]
    for p in candidatos:
        if p.is_file():
            try:
                linha = p.read_text(encoding="utf-8").strip()
                if linha:
                    return linha
            except OSError:
                continue
    return None


def _texto_com_reader(reader: PdfReader) -> str:
    partes = []
    for pagina in reader.pages:
        partes.append(pagina.extract_text() or "")
    return "\n".join(partes)


def _ler_texto_pdf(
    caminho: Path, senha: str | None = None
) -> tuple[str, bool, bool]:
    """Retorna (texto, requer_senha, senha_invalida)."""
    senha = (senha or "").strip() or None
    if not senha:
        senha = ler_senha_arquivo_auxiliar(caminho)

    try:
        with pdfplumber.open(str(caminho), password=senha) as pdf:
            partes = [(p.extract_text() or "") for p in pdf.pages]
            return "\n".join(partes), False, False
    except Exception:
        pass

    try:
        reader = PdfReader(str(caminho), strict=False)
        if reader.is_encrypted:
            if not senha:
                return "", True, False
            if reader.decrypt(senha) == 0:
                return "", True, True
        return _texto_com_reader(reader), False, False
    except Exception as e:
        return f"[ERRO ao ler PDF: {e}]", False, False


def garantir_pdf_desbloqueado(
    caminho: str | Path,
    *,
    senha: str | None = None,
) -> tuple[Path, Path | None]:
    """Se o PDF tiver senha, grava cópia temporária desbloqueada para envio/mesclagem.

    Retorna (caminho_a_usar, temporario_para_apagar_ou_None).
    """
    caminho = Path(caminho)
    reader = PdfReader(str(caminho), strict=False)
    if not reader.is_encrypted:
        return caminho, None

    senha_efetiva = (senha or "").strip() or ler_senha_arquivo_auxiliar(caminho)
    if not senha_efetiva:
        raise PdfRequerSenhaError(
            "PDF protegido por senha. Informe a senha no envio manual ou crie um ficheiro "
            f"«{caminho.name}.senha» na pasta do FULL com a senha numa linha."
        )
    if reader.decrypt(senha_efetiva) == 0:
        raise PdfSenhaInvalidaError("Senha do PDF incorreta.")

    tmp = Path(tempfile.gettempdir()) / f"pdf_desbloqueado_{uuid.uuid4().hex}.pdf"
    writer = PdfWriter()
    writer.append(reader, import_outline=False)
    with tmp.open("wb") as fh:
        writer.write(fh)
    return tmp, tmp


def _detectar_layout(texto: str, *, nome_arquivo: str, cripto: bool) -> str:
    nome = nome_arquivo.upper()
    if cripto or (nome.startswith("S53101") or "S53101" in nome):
        return LAYOUT_CRIPTO
    t = texto.strip()
    if len(t) < 80:
        return LAYOUT_SEM_TEXTO
    up = t.upper()
    if "TOKIO MARINE" in up:
        return LAYOUT_TOKIO
    if "APÓLICE - RAMO 31" in up or "APOLICE - RAMO 31" in up:
        return LAYOUT_YELUM
    if "YELUM" in up and "DADOS DA APOLICE" in up.replace("Ó", "O"):
        return LAYOUT_YELUM
    if "SOMPO" in up and (
        "APÓLICE DE SEGURO" in up
        or "APOLICE DE SEGURO" in up.replace("Ó", "O")
        or "PENHOR" in up
    ):
        return LAYOUT_SOMPO
    if (
        ("TERRA FÉRTIL" in t or "TERRA FERTIL" in up or "TERRAFERTILSEGUROS" in up)
        and (
            "SOLUÇÕES QUE PROTEGEM" in up
            or "SOLUCOES QUE PROTEGEM" in up
            or "PLANTÃO 24" in up
            or "PLANTAO 24" in up
        )
    ):
        return LAYOUT_CAPA
    return LAYOUT_DESCONHECIDO


def _candidato_apolice_ok(val: str) -> bool:
    v = (val or "").strip().rstrip(".,;:")
    if not v:
        return False
    if v.lower() in APOLICE_STOPWORDS:
        return False
    if re.fullmatch(r"[A-Za-zÀ-ÿ]+", v):
        return False
    digits = _limpar_doc(v)
    if len(digits) >= 6 and len(digits) >= max(4, int(len(v) * 0.5)):
        return True
    # códigos alfanuméricos (Tokio etc.) com dígitos suficientes
    if re.fullmatch(r"[A-Z0-9][A-Z0-9\-\./]{4,30}", v, re.IGNORECASE) and len(digits) >= 4:
        return True
    return False


def _score_apolice(val: str) -> tuple[int, int]:
    """Maior score = melhor candidato. Empate: mais dígitos."""
    digits = _limpar_doc(val)
    score = 0
    if val.isdigit() or (len(digits) == len(val.replace(".", "").replace("-", "").replace("/", ""))):
        score += 30
    if 8 <= len(digits) <= 14:
        score += 20
    elif 6 <= len(digits) <= 20:
        score += 10
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}\.\d{7,10}", val):
        score += 40
    return score, len(digits)


def _extrair_apolice_do_texto(texto: str) -> str | None:
    candidatos: list[str] = []
    for pat in RE_APOLICE_PRIORITARIAS:
        for m in pat.finditer(texto):
            val = m.group(1).strip().rstrip(".,;:")
            if _candidato_apolice_ok(val):
                candidatos.append(val)
    m_yelum = RE_YELUM_APOLICE.search(texto)
    if m_yelum and _candidato_apolice_ok(m_yelum.group(1)):
        candidatos.append(m_yelum.group(1))
    m_tokio = RE_TOKIO_APOLICE.search(texto)
    if m_tokio and _candidato_apolice_ok(m_tokio.group(1)):
        candidatos.append(m_tokio.group(1))
    if not candidatos:
        return None
    return max(candidatos, key=_score_apolice)


def _apolice_do_nome_arquivo(nome_arquivo: str) -> str | None:
    """Ex.: 6200159735-0-Via Segurado.pdf → 6200159735"""
    stem = Path(nome_arquivo).stem
    m = re.match(r"^(\d{6,20})(?:[-_\s]|$)", stem)
    if m and _candidato_apolice_ok(m.group(1)):
        return m.group(1)
    return None


def _extrair_nome(texto: str) -> str | None:
    m = RE_NOME_ROTULO.search(texto)
    if not m:
        return None
    nome = re.sub(r"\s+", " ", m.group(1)).strip(" .-")
    # corta se o regex ultrapassou para a linha seguinte de rótulo
    for corte in (" CPF", " CNPJ", " TELEFONE", " ENDEREÇO", " ENDERECO", " VIGÊNCIA", " VIGENCIA"):
        idx = nome.upper().find(corte.strip())
        if idx > 3:
            nome = nome[:idx].strip()
    if len(nome) < 3 or nome.upper() in {"SEGURADO", "PROPONENTE"}:
        return None
    return nome.title() if nome.isupper() else nome


def _extrair_telefone(texto: str) -> str | None:
    m = RE_TELEFONE_ROTULO.search(texto)
    if not m:
        return None
    tel = re.sub(r"\s+", " ", m.group(1)).strip()
    digits = _limpar_doc(tel)
    if len(digits) < 10:
        return None
    return tel


def _aplicar_documento(dados: DadosPDF, bruto: str) -> None:
    dig = _limpar_doc(bruto)
    if len(dig) == 11 and not dados.cpf:
        dados.cpf = dig
    elif len(dig) == 14 and not dados.cnpj:
        dados.cnpj = dig


def _extrair_generico(dados: DadosPDF) -> None:
    texto = dados.texto_completo

    m_doc = RE_DOC_CPF_CNPJ.search(texto)
    if m_doc:
        _aplicar_documento(dados, m_doc.group(1))

    if not dados.cpf:
        m = RE_CPF_ROTULO.search(texto)
        if m:
            dados.cpf = _limpar_doc(m.group(1))
    if not dados.cpf:
        m = RE_CPF.search(texto)
        if m:
            dados.cpf = _limpar_doc(m.group(1))

    # CNPJ solto costuma ser da seguradora — só aceita perto de âncora de segurado.
    _MARCAS_SEGURADORA = (
        "SOMPO",
        "TOKIO",
        "YELUM",
        "PORTO",
        "SULAMERICA",
        "SULAMÉRICA",
        "MAPFRE",
        "BRADESCO",
        "LIBERTY",
        "SEGUROS S",
        "S/A",
        "S.A",
        "SUSEP",
    )
    if not dados.cnpj:
        for m in RE_CNPJ_ROTULO.finditer(texto):
            trecho = texto[max(0, m.start() - 80) : min(len(texto), m.end() + 40)].upper()
            if any(x in trecho for x in _MARCAS_SEGURADORA):
                continue
            if any(
                x in trecho
                for x in ("SEGURADO", "PROPONENTE", "CPF/CNPJ", "TOMADOR", "ESTIPULANTE")
            ):
                dados.cnpj = _limpar_doc(m.group(1))
                break

    if not dados.numero_apolice:
        dados.numero_apolice = _extrair_apolice_do_texto(texto)

    if not dados.nome:
        dados.nome = _extrair_nome(texto)
    if not dados.telefone:
        dados.telefone = _extrair_telefone(texto)


def _extrair_tokio(dados: DadosPDF) -> None:
    dados.seguradora = "Tokio Marine"
    texto = dados.texto_completo
    up = texto.upper()
    if " MOTO" in up or texto.strip().startswith("Tokio Marine\nMOTO"):
        dados.produto = "moto"
    elif " AUTO" in up or "TOKIO MARINE AUTO" in up:
        dados.produto = "auto"

    m = RE_CPF_ROTULO.search(texto)
    if m:
        dados.cpf = _limpar_doc(m.group(1))
    if not dados.cpf:
        m_bar = RE_TOKIO_BARCODE.search(texto)
        if m_bar:
            # Barcode 1N000 + CPF(11) + ...
            linha = re.search(r"1N\d{11}", texto)
            if linha:
                bloco = linha.group(0)
                if len(bloco) >= 14:
                    dados.cpf = bloco[4:15]

    m_ap = RE_TOKIO_APOLICE.search(texto)
    if m_ap:
        dados.numero_apolice = m_ap.group(1)
    elif not dados.numero_apolice:
        m_bar = re.search(r"Ap[óo]lice:\s*(\d{5,12})", texto, re.IGNORECASE)
        if m_bar:
            dados.numero_apolice = m_bar.group(1)

    # CI da Tokio não é CNPJ do segurado — não preencher cnpj a partir do texto genérico
    dados.cnpj = None


def _extrair_yelum(dados: DadosPDF) -> None:
    dados.seguradora = "Yelum"
    dados.produto = "auto_casco"
    texto = dados.texto_completo

    m = RE_CPF_ROTULO.search(texto)
    if m:
        dados.cpf = _limpar_doc(m.group(1))
    if not dados.cpf:
        bloco = re.search(
            r"Segurado\(a\).*?(\d{3}\.\d{3}\.\d{3}-\d{2})",
            texto,
            re.IGNORECASE | re.DOTALL,
        )
        if bloco:
            dados.cpf = _limpar_doc(bloco.group(1))

    m_ap = RE_YELUM_APOLICE.search(texto)
    if m_ap:
        dados.numero_apolice = m_ap.group(1)
    if not dados.numero_apolice:
        dados.numero_apolice = _extrair_apolice_do_texto(texto)

    dados.nome = dados.nome or _extrair_nome(texto)
    dados.telefone = dados.telefone or _extrair_telefone(texto)
    dados.cnpj = None


def _extrair_sompo(dados: DadosPDF) -> None:
    dados.seguradora = "Sompo"
    texto = dados.texto_completo
    up = texto.upper()
    if "PENHOR" in up:
        dados.produto = "penhor_rural"
    elif "AUTO" in up:
        dados.produto = "auto"

    m_doc = RE_DOC_CPF_CNPJ.search(texto) or RE_CPF_ROTULO.search(texto)
    if m_doc:
        _aplicar_documento(dados, m_doc.group(1))
    if not dados.cpf:
        m = RE_CPF.search(texto)
        if m:
            dados.cpf = _limpar_doc(m.group(1))

    # CNPJ da Sompo no rodapé não é do segurado
    dados.cnpj = None
    dados.numero_apolice = _extrair_apolice_do_texto(texto)
    dados.nome = _extrair_nome(texto)
    dados.telefone = _extrair_telefone(texto)


def _aplicar_layout(dados: DadosPDF, layout: str) -> None:
    dados.layout = layout
    if layout == LAYOUT_TOKIO:
        _extrair_tokio(dados)
        return
    if layout == LAYOUT_YELUM:
        _extrair_yelum(dados)
        return
    if layout == LAYOUT_SOMPO:
        _extrair_sompo(dados)
        return
    if layout == LAYOUT_CAPA:
        dados.extracao_automatica = False
        dados.avisos.append("Arquivo é capa institucional; não contém dados de apólice.")
        return
    if layout == LAYOUT_CRIPTO:
        dados.extracao_automatica = False
        dados.requer_senha = True
        dados.seguradora = "Porto/SulAmérica (provável)"
        dados.avisos.append(
            "PDF protegido por senha. Informe a senha no envio manual ou coloque um ficheiro "
            "«nome.pdf.senha» na pasta do FULL (uma linha com a senha)."
        )
        return
    if layout == LAYOUT_SEM_TEXTO:
        dados.extracao_automatica = False
        dados.avisos.append(
            "PDF sem texto selecionável (imagem/impressão). Informe cliente manualmente."
        )
        return
    _extrair_generico(dados)


def extrair_dados(
    caminho_pdf: str | Path,
    *,
    usar_ocr: bool = False,
    senha: str | None = None,
) -> DadosPDF:
    caminho = Path(caminho_pdf)
    if not caminho.exists():
        raise FileNotFoundError(caminho)

    texto, requer_senha, senha_invalida = _ler_texto_pdf(caminho, senha=senha)
    cripto = requer_senha and not senha_invalida
    layout = _detectar_layout(texto, nome_arquivo=caminho.name, cripto=cripto)
    ocr_usado = False

    if (
        usar_ocr
        and layout in (LAYOUT_SEM_TEXTO, LAYOUT_DESCONHECIDO)
        and len(texto.strip()) < 80
        and not requer_senha
    ):
        from . import ocr_service

        texto_ocr, err_ocr = ocr_service.extrair_texto_ocr(caminho)
        if texto_ocr:
            texto = texto_ocr
            ocr_usado = True
            layout = _detectar_layout(texto, nome_arquivo=caminho.name, cripto=False)
        elif err_ocr:
            pass  # mantém layout sem_texto; aviso abaixo

    dados = DadosPDF(
        texto_completo=texto,
        ocr_usado=ocr_usado,
        requer_senha=requer_senha,
        senha_invalida=senha_invalida,
    )
    _aplicar_layout(dados, layout)

    if not dados.numero_apolice:
        dados.numero_apolice = _apolice_do_nome_arquivo(caminho.name)
    if not dados.nome:
        dados.nome = _extrair_nome(texto)
    if not dados.telefone:
        dados.telefone = _extrair_telefone(texto)

    if senha_invalida:
        dados.extracao_automatica = False
        dados.avisos.append("Senha do PDF incorreta.")
    elif requer_senha:
        dados.extracao_automatica = False

    if ocr_usado:
        dados.avisos.append("Texto obtido via OCR (revise CPF e nº da apólice).")
        if dados.layout == LAYOUT_SEM_TEXTO:
            dados.extracao_automatica = bool(dados.cpf or dados.numero_apolice)

    if layout == LAYOUT_DESCONHECIDO and dados.extracao_automatica:
        _extrair_generico(dados)
        if not dados.numero_apolice:
            dados.numero_apolice = _apolice_do_nome_arquivo(caminho.name)

    dados.amostra_texto = (dados.texto_completo or "")[:1200]
    return dados


def formatar_cpf(doc: str) -> str:
    d = _limpar_doc(doc)
    if len(d) != 11:
        return doc
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def formatar_cnpj(doc: str) -> str:
    d = _limpar_doc(doc)
    if len(d) != 14:
        return doc
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _reader_desbloqueado(pdf_path: Path, senha: str | None = None) -> PdfReader:
    r = PdfReader(str(pdf_path), strict=False)
    if r.is_encrypted:
        senha_efetiva = (senha or "").strip() or ler_senha_arquivo_auxiliar(pdf_path)
        if not senha_efetiva:
            raise PdfRequerSenhaError(f"PDF protegido por senha: {pdf_path.name}")
        if r.decrypt(senha_efetiva) == 0:
            raise PdfSenhaInvalidaError("Senha do PDF incorreta.")
    return r


def mesclar_capa_e_apolice(
    capa: Path, apolice: Path, saida: Path, *, senha_apolice: str | None = None
) -> Path:
    """Junta PDFs na ordem: páginas da capa, depois páginas da apólice. Escreve em `saida`.

    Usa ``PdfWriter.append(reader)`` (com ``import_outline=False``), mais robusto com
    PDFs de seguradoras/Word do que ``append_pages_from_reader``, que falha em vários casos.
    """
    capa = Path(capa)
    apolice = Path(apolice)
    saida = Path(saida)
    if not capa.is_file():
        raise FileNotFoundError(capa)
    if not apolice.is_file():
        raise FileNotFoundError(apolice)

    r_capa = _reader_desbloqueado(capa)
    r_apol = _reader_desbloqueado(apolice, senha_apolice)
    n_esperado = len(r_capa.pages) + len(r_apol.pages)

    writer = PdfWriter()
    writer.append(r_capa, import_outline=False)
    writer.append(r_apol, import_outline=False)

    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("wb") as fh:
        writer.write(fh)

    ver = PdfReader(str(saida), strict=False)
    n_saida = len(ver.pages)
    if n_saida != n_esperado:
        raise ValueError(
            f"Junção incompleta: esperadas {n_esperado} páginas (capa {len(r_capa.pages)} + "
            f"apólice {len(r_apol.pages)}), obtidas {n_saida}."
        )
    return saida
