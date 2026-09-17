"""Biblioteca de modelos de capa e resolucao da composicao de PDFs.

Os ficheiros sao imutaveis e recebem nome UUID dentro de ``CAPA_FOLDER``. A
posicao (antes/depois da apolice) nao pertence ao modelo: ela e definida pela
lista ordenada selecionada no tipo de envio ou no envio manual.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Iterable, Sequence

from fastapi import UploadFile
from pypdf import PdfReader
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from .upload_service import save_upload


log = logging.getLogger(__name__)

MAX_CAPAS_POR_LADO = 10
_NOME_LEGADO = "Capa padrao (legada)"


class CapaServiceError(ValueError):
    """Erro de dominio da biblioteca de capas."""


class CapaNaoEncontradaError(CapaServiceError):
    pass


class CapaNomeDuplicadoError(CapaServiceError):
    pass


class CapaEmUsoError(CapaServiceError):
    pass


def _pasta_capas() -> Path:
    pasta = settings.data_path(settings.capa_folder).resolve()
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _sha256_arquivo(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validar_nome(nome: str) -> str:
    valor = (nome or "").strip()
    if not valor:
        raise CapaServiceError("Informe o nome do modelo de capa")
    if len(valor) > 120:
        raise CapaServiceError("O nome do modelo de capa deve ter no maximo 120 caracteres")
    return valor


def _validar_descricao(descricao: str | None) -> str | None:
    if descricao is None:
        return None
    valor = descricao.strip()
    if len(valor) > 255:
        raise CapaServiceError("A descricao deve ter no maximo 255 caracteres")
    return valor or None


def _nome_ja_existe(db: Session, nome: str, *, ignorar_id: int | None = None) -> bool:
    query = db.query(models.CapaModelo.id).filter(
        func.lower(models.CapaModelo.nome) == nome.casefold()
    )
    if ignorar_id is not None:
        query = query.filter(models.CapaModelo.id != ignorar_id)
    return query.first() is not None


def caminho_arquivo(capa: models.CapaModelo) -> Path:
    """Resolve o ficheiro de uma capa sem permitir fuga de ``CAPA_FOLDER``."""
    nome = (capa.arquivo or "").strip()
    relativo = Path(nome)
    if not nome or relativo.is_absolute() or relativo.name != nome:
        raise CapaServiceError(f"Caminho invalido no modelo de capa #{capa.id}")

    raiz = _pasta_capas()
    caminho = (raiz / relativo).resolve()
    try:
        caminho.relative_to(raiz)
    except ValueError as exc:
        raise CapaServiceError(
            f"Caminho invalido no modelo de capa #{capa.id}"
        ) from exc
    return caminho


def parse_ids_json(
    valor: str | Sequence[int] | None,
    campo: str,
) -> list[int]:
    """Valida uma lista JSON ordenada de IDs usada em multipart ou no banco."""
    if valor is None:
        return []
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return []
        try:
            itens = json.loads(texto)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CapaServiceError(f"{campo} deve ser uma lista JSON de IDs") from exc
    elif isinstance(valor, Sequence) and not isinstance(valor, (bytes, bytearray)):
        itens = list(valor)
    else:
        raise CapaServiceError(f"{campo} deve ser uma lista de IDs")

    if not isinstance(itens, list):
        raise CapaServiceError(f"{campo} deve ser uma lista de IDs")
    if len(itens) > MAX_CAPAS_POR_LADO:
        raise CapaServiceError(
            f"{campo} aceita no maximo {MAX_CAPAS_POR_LADO} capas"
        )

    ids: list[int] = []
    for item in itens:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise CapaServiceError(f"{campo} contem um ID invalido")
        ids.append(item)
    if len(set(ids)) != len(ids):
        raise CapaServiceError(f"{campo} nao pode repetir a mesma capa")
    return ids


def _modelos_por_ids(
    db: Session,
    ids_iniciais: Sequence[int],
    ids_finais: Sequence[int],
) -> tuple[list[models.CapaModelo], list[models.CapaModelo]]:
    todos_ids = list(dict.fromkeys([*ids_iniciais, *ids_finais]))
    if not todos_ids:
        return [], []

    encontrados = (
        db.query(models.CapaModelo)
        .filter(models.CapaModelo.id.in_(todos_ids))
        .all()
    )
    por_id = {capa.id: capa for capa in encontrados}
    ausentes = [capa_id for capa_id in todos_ids if capa_id not in por_id]
    if ausentes:
        raise CapaNaoEncontradaError(
            "Modelo(s) de capa nao encontrado(s): " + ", ".join(map(str, ausentes))
        )

    inativas = [capa_id for capa_id in todos_ids if not por_id[capa_id].ativo]
    if inativas:
        raise CapaServiceError(
            "Modelo(s) de capa inativo(s): " + ", ".join(map(str, inativas))
        )

    for capa_id in todos_ids:
        path = caminho_arquivo(por_id[capa_id])
        if not path.is_file():
            raise CapaServiceError(
                f"Arquivo do modelo de capa #{capa_id} nao foi encontrado"
            )

    return (
        [por_id[capa_id] for capa_id in ids_iniciais],
        [por_id[capa_id] for capa_id in ids_finais],
    )


def resolver_listas(
    db: Session,
    *,
    tipo_codigo: str | None,
    capas_iniciais_ids: str | Sequence[int] | None = None,
    capas_finais_ids: str | Sequence[int] | None = None,
) -> tuple[list[models.CapaModelo], list[models.CapaModelo]]:
    """Resolve capas preservando ordem e a semantica herdar/zerar.

    ``None`` herda a lista do ``TipoEnvio``. Uma lista vazia explicita remove
    todas as capas daquele lado para o envio atual.
    """
    tipo: models.TipoEnvio | None = None
    codigo = (tipo_codigo or "").strip()
    if codigo:
        tipo = (
            db.query(models.TipoEnvio)
            .filter(models.TipoEnvio.codigo == codigo)
            .first()
        )
        # O processador tambem e usado por integracoes e testes que informam
        # apenas um codigo externo, sem manter o cadastro de TipoEnvio local.
        # Nesse caso nao ha listas padrao para herdar, mas o envio continua
        # valido (e ainda pode informar capas explicitamente).

    origem_iniciais: str | Sequence[int] | None = capas_iniciais_ids
    origem_finais: str | Sequence[int] | None = capas_finais_ids
    if origem_iniciais is None:
        origem_iniciais = tipo.capas_iniciais_json if tipo else []
    if origem_finais is None:
        origem_finais = tipo.capas_finais_json if tipo else []

    ids_iniciais = parse_ids_json(origem_iniciais, "capas_iniciais_ids")
    ids_finais = parse_ids_json(origem_finais, "capas_finais_ids")
    return _modelos_por_ids(db, ids_iniciais, ids_finais)


def _sha_capa(capa: models.CapaModelo) -> str:
    sha = (capa.sha256 or "").strip()
    if sha:
        return sha
    path = caminho_arquivo(capa)
    if not path.is_file():
        raise CapaServiceError(
            f"Arquivo do modelo de capa #{capa.id} nao foi encontrado"
        )
    return _sha256_arquivo(path)


def snapshots(capas: Iterable[models.CapaModelo]) -> list[dict]:
    """Cria o snapshot minimo e estavel persistido junto ao envio."""
    return [
        {
            "id": int(capa.id) if capa.id is not None else None,
            "nome": capa.nome,
            # O hash precisa estar no snapshot, inclusive para capas legadas,
            # pois o retry deve reconstruir a mesma chave de idempotencia.
            "sha256": _sha_capa(capa),
        }
        for capa in capas
    ]


def snapshots_json(capas: Iterable[models.CapaModelo]) -> str:
    return json.dumps(snapshots(capas), ensure_ascii=False, separators=(",", ":"))


def fingerprint(
    iniciais: Iterable[models.CapaModelo],
    finais: Iterable[models.CapaModelo],
) -> str:
    """Hash da composicao; lado e ordem fazem parte do resultado."""
    iniciais = list(iniciais)
    finais = list(finais)
    if not iniciais and not finais:
        return ""

    def _item(capa: models.CapaModelo) -> dict[str, int | str | None]:
        return {"id": capa.id, "sha256": _sha_capa(capa)}

    payload = {
        "versao": 1,
        "iniciais": [_item(capa) for capa in iniciais],
        "finais": [_item(capa) for capa in finais],
    }
    canonico = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def fingerprint_snapshots_json(
    iniciais_json: str | None,
    finais_json: str | None,
) -> str:
    """Reconstrui o fingerprint salvo sem depender dos arquivos das capas."""

    def _ler(valor: str | None, campo: str) -> list[dict[str, int | str | None]]:
        if not valor or not valor.strip():
            return []
        try:
            itens = json.loads(valor)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CapaServiceError(f"Snapshot invalido em {campo}") from exc
        if not isinstance(itens, list):
            raise CapaServiceError(f"Snapshot invalido em {campo}")

        normalizados: list[dict[str, int | str | None]] = []
        for item in itens:
            if not isinstance(item, dict):
                raise CapaServiceError(f"Snapshot invalido em {campo}")
            capa_id = item.get("id")
            sha = str(item.get("sha256") or "").strip()
            if (
                isinstance(capa_id, bool)
                or not isinstance(capa_id, int)
                or capa_id <= 0
                or not sha
            ):
                raise CapaServiceError(f"Snapshot invalido em {campo}")
            normalizados.append({"id": capa_id, "sha256": sha})
        return normalizados

    iniciais = _ler(iniciais_json, "capas_iniciais_json")
    finais = _ler(finais_json, "capas_finais_json")
    if not iniciais and not finais:
        return ""
    payload = {"versao": 1, "iniciais": iniciais, "finais": finais}
    canonico = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def listar_modelos(db: Session, *, ativo: bool | None = None) -> list[models.CapaModelo]:
    query = db.query(models.CapaModelo)
    if ativo is not None:
        query = query.filter(models.CapaModelo.ativo == ativo)
    return query.order_by(models.CapaModelo.nome.asc(), models.CapaModelo.id.asc()).all()


def obter_modelo(db: Session, capa_id: int) -> models.CapaModelo:
    capa = db.get(models.CapaModelo, capa_id)
    if capa is None:
        raise CapaNaoEncontradaError("Modelo de capa nao encontrado")
    return capa


async def criar_modelo(
    db: Session,
    *,
    nome: str,
    descricao: str | None,
    arquivo: UploadFile,
) -> models.CapaModelo:
    nome_ok = _validar_nome(nome)
    descricao_ok = _validar_descricao(descricao)
    if _nome_ja_existe(db, nome_ok):
        raise CapaNomeDuplicadoError("Ja existe um modelo de capa com esse nome")

    nome_original = Path(arquivo.filename or "capa.pdf").name[:255]
    destino = _pasta_capas() / f"{uuid.uuid4().hex}.pdf"
    salvo = await save_upload(
        arquivo,
        destino,
        kind="pdf",
        allowed_suffixes={".pdf"},
    )
    try:
        reader = PdfReader(str(destino), strict=False)
        if reader.is_encrypted:
            raise CapaServiceError("Modelos de capa nao podem ser protegidos por senha")
        paginas = len(reader.pages)
        capa = models.CapaModelo(
            nome=nome_ok,
            descricao=descricao_ok,
            arquivo=destino.name,
            nome_original=nome_original,
            tamanho_bytes=salvo.size,
            paginas=paginas,
            sha256=salvo.sha256,
            ativo=True,
        )
        db.add(capa)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise CapaNomeDuplicadoError(
                "Ja existe um modelo de capa com esse nome"
            ) from exc
        db.refresh(capa)
        return capa
    except Exception:
        destino.unlink(missing_ok=True)
        raise


def atualizar_modelo(
    db: Session,
    capa_id: int,
    *,
    dados: dict,
) -> models.CapaModelo:
    capa = obter_modelo(db, capa_id)
    if "nome" in dados and dados["nome"] is not None:
        nome = _validar_nome(dados["nome"])
        if _nome_ja_existe(db, nome, ignorar_id=capa.id):
            raise CapaNomeDuplicadoError("Ja existe um modelo de capa com esse nome")
        capa.nome = nome
    if "descricao" in dados:
        capa.descricao = _validar_descricao(dados["descricao"])
    if "ativo" in dados and dados["ativo"] is not None:
        if not bool(dados["ativo"]):
            referencias = tipos_referenciando(db, capa.id)
            if referencias:
                nomes = ", ".join(tipo.nome for tipo in referencias)
                raise CapaEmUsoError(
                    f"Modelo de capa vinculado a tipo(s) de envio: {nomes}"
                )
        capa.ativo = bool(dados["ativo"])

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CapaNomeDuplicadoError("Ja existe um modelo de capa com esse nome") from exc
    db.refresh(capa)
    return capa


def tipos_referenciando(db: Session, capa_id: int) -> list[models.TipoEnvio]:
    referencias: list[models.TipoEnvio] = []
    for tipo in db.query(models.TipoEnvio).order_by(models.TipoEnvio.id.asc()).all():
        ids_iniciais = tipo.capas_iniciais_ids
        ids_finais = tipo.capas_finais_ids
        if capa_id in ids_iniciais or capa_id in ids_finais:
            referencias.append(tipo)
    return referencias


def remover_modelo(db: Session, capa_id: int) -> None:
    capa = obter_modelo(db, capa_id)
    referencias = tipos_referenciando(db, capa_id)
    if referencias:
        nomes = ", ".join(f"{tipo.nome} ({tipo.codigo})" for tipo in referencias)
        raise CapaEmUsoError(
            f"Modelo de capa vinculado a tipo(s) de envio: {nomes}"
        )

    path = caminho_arquivo(capa)
    db.delete(capa)
    db.commit()
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("Nao foi possivel remover ficheiro orfao de capa %s: %s", path, exc)


def _nome_legado_disponivel(db: Session) -> str:
    nome = _NOME_LEGADO
    sufixo = 2
    while _nome_ja_existe(db, nome):
        marcador = f" ({sufixo})"
        nome = f"{_NOME_LEGADO[:120 - len(marcador)]}{marcador}"
        sufixo += 1
    return nome


def importar_capa_legada(db: Session) -> models.CapaModelo | None:
    """Copia ``capa.pdf`` antigo para o catalogo, sem associar a nenhum tipo.

    A origem e mantida para que uma instalacao em transicao continue compativel
    com a antiga rota singular ate o novo compositor assumir todos os envios.
    """
    raiz = _pasta_capas()
    nome_legado = Path(settings.capa_arquivo_padrao or "capa.pdf").name
    origem = (raiz / nome_legado).resolve()
    try:
        origem.relative_to(raiz)
    except ValueError:
        log.warning("Capa legada ignorada por caminho inseguro: %s", origem)
        return None
    if not origem.is_file():
        return None

    try:
        reader = PdfReader(str(origem), strict=False)
        if reader.is_encrypted:
            log.warning("Capa legada criptografada nao foi importada: %s", origem)
            return None
        paginas = len(reader.pages)
        sha = _sha256_arquivo(origem)
    except Exception as exc:
        log.warning("Capa legada invalida nao foi importada (%s): %s", origem, exc)
        return None

    existente = (
        db.query(models.CapaModelo)
        .filter(models.CapaModelo.sha256 == sha)
        .first()
    )
    if existente is not None:
        return existente

    destino = raiz / f"{uuid.uuid4().hex}.pdf"
    try:
        shutil.copy2(origem, destino)
        capa = models.CapaModelo(
            nome=_nome_legado_disponivel(db),
            descricao="Importada automaticamente da capa global anterior.",
            arquivo=destino.name,
            nome_original=origem.name,
            tamanho_bytes=destino.stat().st_size,
            paginas=paginas,
            sha256=sha,
            ativo=True,
        )
        db.add(capa)
        db.commit()
        db.refresh(capa)
        log.info("Capa legada importada para o catalogo como modelo #%s", capa.id)
        return capa
    except Exception:
        db.rollback()
        destino.unlink(missing_ok=True)
        raise
