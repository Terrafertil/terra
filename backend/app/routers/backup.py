"""Browser de backup: navegação por sub-pastas e download (1 ou vários como zip)."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from ..config import settings
from .. import schemas
from ..auth import require_backup_access


router = APIRouter(prefix="/api/backup", tags=["backup"])


def _root() -> Path:
    return settings.data_path(settings.backup_folder)


def _resolver(rel: str | None) -> Path:
    """Resolve um caminho relativo dentro do backup root, com proteção anti path-traversal."""
    root = _root().resolve()
    rel = (rel or "").strip().strip("/").strip("\\")
    if not rel:
        return root
    rel = unquote(rel)
    p = (root / rel).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise HTTPException(400, "Caminho fora do backup")
    return p


def _rel_str(p: Path) -> str:
    root = _root().resolve()
    try:
        return p.resolve().relative_to(root).as_posix()
    except ValueError:
        return ""


@router.get("/listar", response_model=schemas.BackupListagemOut)
def listar(
    caminho: str = Query("", description="Caminho relativo dentro do backup"),
    _=Depends(require_backup_access),
):
    p = _resolver(caminho)
    p.mkdir(parents=True, exist_ok=True)
    if not p.is_dir():
        raise HTTPException(404, "Pasta não encontrada")

    itens: list[schemas.BackupItemOut] = []
    for f in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        try:
            stat = f.stat()
        except Exception:
            continue
        itens.append(
            schemas.BackupItemOut(
                nome=f.name,
                caminho_relativo=_rel_str(f),
                eh_pasta=f.is_dir(),
                tamanho_bytes=stat.st_size if f.is_file() else 0,
                atualizado_em=datetime.fromtimestamp(stat.st_mtime),
            )
        )

    parent = None
    if p != _root().resolve():
        parent = _rel_str(p.parent)
    return schemas.BackupListagemOut(
        caminho_atual=_rel_str(p),
        parent_relativo=parent,
        itens=itens,
    )


@router.get("/download")
def download_um(
    caminho: str = Query(..., description="Caminho relativo do arquivo"),
    _=Depends(require_backup_access),
):
    p = _resolver(caminho)
    if not p.is_file():
        raise HTTPException(404, "Arquivo não encontrado")
    return FileResponse(str(p), filename=p.name)


@router.get("/download-zip")
def download_zip(
    caminhos: list[str] = Query(..., description="Lista de caminhos relativos"),
    _=Depends(require_backup_access),
):
    if not caminhos:
        raise HTTPException(400, "Nenhum caminho informado")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for c in caminhos:
            p = _resolver(c)
            if p.is_file():
                zf.write(p, arcname=p.name)
            elif p.is_dir():
                root = _root().resolve()
                for sub in p.rglob("*"):
                    if sub.is_file():
                        try:
                            arc = sub.resolve().relative_to(root.parent).as_posix()
                        except Exception:
                            arc = sub.name
                        zf.write(sub, arcname=arc)
    buf.seek(0)
    nome_zip = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nome_zip}"'},
    )
