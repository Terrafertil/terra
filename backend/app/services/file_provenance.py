"""Identifica quem colocou um ficheiro na pasta FULL (auditoria)."""
from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def ler_usuario_arquivo_auxiliar(caminho_pdf: Path) -> str | None:
    """Ficheiro ao lado do PDF com o utilizador (uma linha).

    Nomes: ``apolice.pdf.usuario``, ``apolice.usuario.txt`` ou ``apolice.usuario``.
    """
    caminho_pdf = Path(caminho_pdf)
    candidatos = [
        Path(str(caminho_pdf) + ".usuario"),
        caminho_pdf.with_name(caminho_pdf.stem + ".usuario.txt"),
        caminho_pdf.with_name(caminho_pdf.stem + ".usuario"),
    ]
    for p in candidatos:
        if p.is_file():
            try:
                linha = p.read_text(encoding="utf-8").strip()
                if linha:
                    return linha[:150]
            except OSError:
                continue
    return None


def _dono_arquivo_unix(caminho: Path) -> str | None:
    try:
        import pwd

        st = caminho.stat()
        return pwd.getpwuid(st.st_uid).pw_name
    except (ImportError, KeyError, OSError):
        return None


def _dono_arquivo_windows(caminho: Path) -> str | None:
    try:
        ps = (
            f'(Get-Acl -LiteralPath "{caminho}").Owner '
            '| ForEach-Object { $_.Value }'
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if r.returncode == 0:
            out = (r.stdout or "").strip()
            if out:
                return out[:150]
    except Exception as e:
        log.debug("Não foi possível obter dono do ficheiro %s: %s", caminho.name, e)
    return None


def detectar_arquivo_colocado_por(caminho_pdf: Path) -> str | None:
    """Sidecar .usuario tem prioridade; senão dono do ficheiro no SO."""
    aux = ler_usuario_arquivo_auxiliar(caminho_pdf)
    if aux:
        return aux

    caminho_pdf = Path(caminho_pdf)
    if not caminho_pdf.is_file():
        return None

    sistema = platform.system().lower()
    if sistema == "windows":
        return _dono_arquivo_windows(caminho_pdf)
    return _dono_arquivo_unix(caminho_pdf)


def rotulo_usuario(nome: str | None, username: str | None) -> str:
    n = (nome or "").strip()
    u = (username or "").strip()
    if n and u and n.lower() != u.lower():
        return f"{n} ({u})"
    return n or u or "—"
