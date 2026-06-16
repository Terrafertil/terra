"""Serviço de backup.

Estrutura: {backup_folder}/{YYYY-MM}/{slug_cliente}/{nome_arquivo}
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from ..config import settings


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
