"""CRUD dos tipos de envio. Cria sub-pasta dentro de FULL_WATCH_FOLDER."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from .. import models, schemas
from ..auth import require_user, require_admin


router = APIRouter(prefix="/api/tipos-envio", tags=["tipos-envio"])


def _pasta_tipo(codigo: str) -> str:
    return str(settings.data_path(settings.full_watch_folder) / codigo)


def _to_out(t: models.TipoEnvio) -> dict:
    return {
        "id": t.id,
        "codigo": t.codigo,
        "nome": t.nome,
        "descricao": t.descricao,
        "ordem": t.ordem,
        "na_fila_full": t.na_fila_full,
        "corpo_email_id": t.corpo_email_id,
        "assunto_email_id": t.assunto_email_id,
        "capas_iniciais_ids": t.capas_iniciais_ids,
        "capas_finais_ids": t.capas_finais_ids,
        "ativo": t.ativo,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "pasta": _pasta_tipo(t.codigo),
    }


def _validar_capas(db: Session, *listas: list[int] | None) -> None:
    for ids in listas:
        if ids is None:
            continue
        if len(ids) != len(set(ids)):
            raise HTTPException(400, "Uma mesma capa não pode ser repetida na mesma posição")
        if not ids:
            continue
        encontrados = {
            row[0]
            for row in db.query(models.CapaModelo.id).filter(
                models.CapaModelo.id.in_(ids), models.CapaModelo.ativo.is_(True)
            )
        }
        faltantes = [capa_id for capa_id in ids if capa_id not in encontrados]
        if faltantes:
            raise HTTPException(400, f"Capas inválidas ou inativas: {faltantes}")


@router.get("", response_model=list[schemas.TipoEnvioOut])
def listar(
    ativo: bool | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    q = db.query(models.TipoEnvio)
    if ativo is not None:
        q = q.filter(models.TipoEnvio.ativo == ativo)
    tipos = q.order_by(models.TipoEnvio.ordem, models.TipoEnvio.id).all()
    return [_to_out(t) for t in tipos]


@router.get("/{tid}", response_model=schemas.TipoEnvioOut)
def obter(tid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    t = db.get(models.TipoEnvio, tid)
    if not t:
        raise HTTPException(404, "Tipo de envio não encontrado")
    return _to_out(t)


@router.post("", response_model=schemas.TipoEnvioOut, status_code=201)
def criar(
    payload: schemas.TipoEnvioCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    if db.query(models.TipoEnvio).filter(models.TipoEnvio.codigo == payload.codigo).first():
        raise HTTPException(400, "Código já existe")
    if payload.corpo_email_id:
        if not db.get(models.CorpoEmail, payload.corpo_email_id):
            raise HTTPException(400, "corpo_email_id inválido")
    if payload.assunto_email_id:
        if not db.get(models.AssuntoEmail, payload.assunto_email_id):
            raise HTTPException(400, "assunto_email_id invalido")
    _validar_capas(db, payload.capas_iniciais_ids, payload.capas_finais_ids)
    if payload.ordem == 0:
        # próxima ordem
        max_ordem = db.query(models.TipoEnvio).count()
        payload_ordem = max_ordem + 1
    else:
        payload_ordem = payload.ordem
    t = models.TipoEnvio(**payload.model_dump())
    t.ordem = payload_ordem
    db.add(t)
    db.commit()
    db.refresh(t)
    # Cria sub-pasta
    settings.data_path(settings.full_watch_folder).mkdir(parents=True, exist_ok=True)
    (settings.data_path(settings.full_watch_folder) / t.codigo).mkdir(parents=True, exist_ok=True)
    return _to_out(t)


@router.put("/{tid}", response_model=schemas.TipoEnvioOut)
def atualizar(
    tid: int,
    payload: schemas.TipoEnvioUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    t = db.get(models.TipoEnvio, tid)
    if not t:
        raise HTTPException(404, "Tipo de envio não encontrado")
    dados = payload.model_dump(exclude_unset=True)
    if "codigo" in dados and dados["codigo"] != t.codigo:
        existe = db.query(models.TipoEnvio).filter(
            models.TipoEnvio.codigo == dados["codigo"],
            models.TipoEnvio.id != tid,
        ).first()
        if existe:
            raise HTTPException(400, "Código já existe")
    if "corpo_email_id" in dados and dados["corpo_email_id"]:
        if not db.get(models.CorpoEmail, dados["corpo_email_id"]):
            raise HTTPException(400, "corpo_email_id inválido")
    if "assunto_email_id" in dados and dados["assunto_email_id"]:
        if not db.get(models.AssuntoEmail, dados["assunto_email_id"]):
            raise HTTPException(400, "assunto_email_id invalido")
    _validar_capas(
        db,
        dados.get("capas_iniciais_ids"),
        dados.get("capas_finais_ids"),
    )
    codigo_antigo = t.codigo
    for k, v in dados.items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    # Renomeia sub-pasta se o codigo mudou
    if codigo_antigo != t.codigo:
        old = settings.data_path(settings.full_watch_folder) / codigo_antigo
        new = settings.data_path(settings.full_watch_folder) / t.codigo
        try:
            if old.is_dir() and not new.exists():
                old.rename(new)
            else:
                new.mkdir(parents=True, exist_ok=True)
        except Exception:
            new.mkdir(parents=True, exist_ok=True)
    return _to_out(t)


@router.delete("/{tid}", status_code=204)
def remover(tid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    t = db.get(models.TipoEnvio, tid)
    if not t:
        raise HTTPException(404, "Tipo de envio não encontrado")
    db.delete(t)
    db.commit()


@router.patch("/ordem", response_model=list[schemas.TipoEnvioOut])
def reordenar(
    payload: schemas.TipoEnvioOrdemPatch,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Reordena os tipos pela lista de codigos enviada."""
    for idx, codigo in enumerate(payload.ordem, start=1):
        t = db.query(models.TipoEnvio).filter(models.TipoEnvio.codigo == codigo).first()
        if t:
            t.ordem = idx
    db.commit()
    tipos = db.query(models.TipoEnvio).order_by(models.TipoEnvio.ordem, models.TipoEnvio.id).all()
    return [_to_out(t) for t in tipos]
