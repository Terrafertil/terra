"""Serviço de backup.

Estrutura: {backup_folder}/{YYYY-MM}/{slug_cliente}/{nome_arquivo}
"""
from __future__ import annotations

import re
import shutil
import logging
from datetime import datetime
from pathlib import Path

from ..config import settings


log = logging.getLogger(__name__)


def _slug(texto: str) -> str:
    s = re.sub(r"[^\w\s.-]", "", texto, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s.strip())
    return s or "sem_nome"


def caminho_backup(cliente_nome: str, nome_arquivo: str) -> Path:
    data = datetime.now().strftime("%Y-%m")
    root = settings.data_path(settings.backup_folder)
    destino = root / data / _slug(cliente_nome)
    destino.mkdir(parents=True, exist_ok=True)
    return destino / nome_arquivo


def copiar_para_backup(
    origem: str | Path, cliente_nome: str, nome_arquivo_destino: str | None = None
) -> Path:
    origem = Path(origem)
    if not origem.exists():
        raise FileNotFoundError(origem)
    nome = nome_arquivo_destino or origem.name
    destino = caminho_backup(cliente_nome, nome)
    # Se arquivo já existe, acrescenta timestamp
    if destino.exists():
        ts = datetime.now().strftime("%H%M%S")
        destino = destino.with_stem(f"{destino.stem}_{ts}")
    shutil.copy2(origem, destino)
    return destino


def aplicar_retencao_automatica() -> list[Path]:
    """Remove somente pastas mensais YYYY-MM anteriores Ã  retenÃ§Ã£o configurada."""
    if not settings.backup_retention_auto:
        return []
    meses = max(1, int(settings.backup_retention_months))
    agora = datetime.now()
    indice_atual = agora.year * 12 + (agora.month - 1)
    limite = indice_atual - meses
    root = settings.data_path(settings.backup_folder).resolve()
    removidas: list[Path] = []
    for pasta in root.iterdir() if root.is_dir() else []:
        if not pasta.is_dir() or not re.fullmatch(r"\d{4}-\d{2}", pasta.name):
            continue
        ano, mes = map(int, pasta.name.split("-"))
        if not 1 <= mes <= 12:
            continue
        if ano * 12 + (mes - 1) >= limite:
            continue
        resolved = pasta.resolve()
        resolved.relative_to(root)
        shutil.rmtree(resolved)
        removidas.append(resolved)
        log.info("Backup removido pela retenÃ§Ã£o automÃ¡tica: %s", resolved)
    return removidas
