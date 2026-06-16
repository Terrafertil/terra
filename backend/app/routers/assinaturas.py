"""CRUD de assinaturas (com upload da imagem)."""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from .. import models, schemas
from ..auth import require_user


router = APIRouter(prefix="/api/assinaturas", tags=["assinaturas"])

EXTS_OK = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _slug(texto: str) -> str:
    s = re.sub(r"[^\w\s.-]", "", texto, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s.strip())
    return (s or "assinatura")[:60]


def _salvar_arquivo(nome: str, conteudo: bytes, ext: str) -> str:
    pasta = settings.data_path(settings.assinaturas_folder)
    pasta.mkdir(parents=True, exist_ok=True)
    nome_final = f"{_slug(nome)}_{uuid.uuid4().hex[:8]}{ext.lower()}"
    (pasta / nome_final).write_bytes(conteudo)
    return nome_final


@router.get("", response_model=list[schemas.AssinaturaOut])
def listar(
    ativo: bool | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    q = db.query(models.Assinatura)
    if ativo is not None:
        q = q.filter(models.Assinatura.ativo == ativo)
    return q.order_by(models.Assinatura.nome).all()


@router.get("/{aid}", response_model=schemas.AssinaturaOut)
def obter(aid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    a = db.get(models.Assinatura, aid)
    if not a:
        raise HTTPException(404, "Assinatura não encontrada")
    return a


@router.get("/{aid}/imagem")
def imagem(aid: int, db: Session = Depends(get_db)):
    a = db.get(models.Assinatura, aid)
    if not a or not a.arquivo:
        raise HTTPException(404, "Imagem não encontrada")
    p = settings.data_path(settings.assinaturas_folder) / a.arquivo
    if not p.is_file():
        raise HTTPException(404, "Arquivo da imagem não existe no disco")
    return FileResponse(str(p))


@router.post("", response_model=schemas.AssinaturaOut, status_code=201)
async def criar(
    nome: str = Form(...),
    pessoa: str | None = Form(None),
    cargo: str | None = Form(None),
    email_contato: str | None = Form(None),
    telefone: str | None = Form(None),
    arquivo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    if db.query(models.Assinatura).filter(models.Assinatura.nome == nome).first():
        raise HTTPException(400, "Já existe assinatura com esse nome")

    arquivo_nome: str | None = None
    if arquivo and arquivo.filename:
        ext = Path(arquivo.filename).suffix.lower()
        if ext not in EXTS_OK:
            raise HTTPException(400, f"Extensão não suportada: {ext}")
        conteudo = await arquivo.read()
        if not conteudo:
            raise HTTPException(400, "Arquivo vazio")
        arquivo_nome = _salvar_arquivo(nome, conteudo, ext)

    a = models.Assinatura(
        nome=nome,
        pessoa=pessoa,
        cargo=cargo,
        email_contato=email_contato,
        telefone=telefone,
        arquivo=arquivo_nome,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.put("/{aid}", response_model=schemas.AssinaturaOut)
async def atualizar(
    aid: int,
    nome: str | None = Form(None),
    pessoa: str | None = Form(None),
    cargo: str | None = Form(None),
    email_contato: str | None = Form(None),
    telefone: str | None = Form(None),
    ativo: bool | None = Form(None),
    arquivo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    a = db.get(models.Assinatura, aid)
    if not a:
        raise HTTPException(404, "Assinatura não encontrada")

    if nome is not None and nome != a.nome:
        existe = db.query(models.Assinatura).filter(
            models.Assinatura.nome == nome,
            models.Assinatura.id != aid,
        ).first()
        if existe:
            raise HTTPException(400, "Já existe assinatura com esse nome")
        a.nome = nome
    if pessoa is not None:
        a.pessoa = pessoa
    if cargo is not None:
        a.cargo = cargo
    if email_contato is not None:
        a.email_contato = email_contato
    if telefone is not None:
        a.telefone = telefone
    if ativo is not None:
        a.ativo = ativo

    if arquivo and arquivo.filename:
        ext = Path(arquivo.filename).suffix.lower()
        if ext not in EXTS_OK:
            raise HTTPException(400, f"Extensão não suportada: {ext}")
        conteudo = await arquivo.read()
        if not conteudo:
            raise HTTPException(400, "Arquivo vazio")
        # apaga o antigo
        if a.arquivo:
            antigo = settings.data_path(settings.assinaturas_folder) / a.arquivo
            if antigo.is_file():
                try:
                    antigo.unlink()
                except Exception:
                    pass
        a.arquivo = _salvar_arquivo(a.nome, conteudo, ext)

    db.commit()
    db.refresh(a)
    return a


@router.delete("/{aid}", status_code=204)
def remover(aid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    a = db.get(models.Assinatura, aid)
    if not a:
        raise HTTPException(404, "Assinatura não encontrada")
    if a.arquivo:
        p = settings.data_path(settings.assinaturas_folder) / a.arquivo
        if p.is_file():
            try:
                p.unlink()
            except Exception:
                pass
    # libera referência em RuntimeConfig
    rc = db.get(models.RuntimeConfig, 1)
    if rc and rc.full_assinatura_id == aid:
        rc.full_assinatura_id = None
    db.delete(a)
    db.commit()
