"""Status geral do sistema e ajustes do modo FULL (painel)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import settings
from .. import models, schemas
from ..auth import require_user
from ..services import notificacoes_service, ocr_service
from ..services.data_crypto_service import backend_access_enabled, encryption_enabled
from ..services import soc_service


router = APIRouter(prefix="/api", tags=["status"])


def _montar_status(db: Session) -> schemas.StatusOut:
    rc = db.get(models.RuntimeConfig, 1)
    env_on = settings.full_enabled
    scan_active = rc.full_scan_active if rc else True
    interval = rc.full_scan_interval_seconds if rc else settings.full_scan_interval_seconds
    interval = max(10, min(3600, int(interval)))
    effective = bool(env_on and scan_active and (rc.full_modo_ativo if rc else True))
    exec_time = "08:00"
    if rc and rc.full_scan_exec_time:
        exec_time = rc.full_scan_exec_time
    soc = soc_service.soc_status(db)
    return schemas.StatusOut(
        status="ok",
        versao="1.0.0",
        auth_enabled=settings.auth_enabled,
        full_enabled=effective,
        full_env_enabled=env_on,
        full_scan_active=scan_active,
        full_scan_interval_seconds=interval,
        full_scan_exec_time=exec_time,
        full_watch_folder=str(settings.data_path(settings.full_watch_folder)),
        full_lote_size=rc.full_lote_size if rc else settings.full_lote_size,
        full_intervalo_lote_min=rc.full_intervalo_lote_min if rc else settings.full_intervalo_lote_min,
        full_rescan_horas=rc.full_rescan_horas if rc else settings.full_rescan_horas,
        full_modo_ativo=rc.full_modo_ativo if rc else True,
        full_assinatura_id=rc.full_assinatura_id if rc else None,
        total_clientes=db.query(models.Cliente).count(),
        total_envios=db.query(models.Envio).count(),
        notificacoes_nao_lidas=notificacoes_service.contar_nao_lidas(db),
        ocr_disponivel=ocr_service.ocr_disponivel(),
        backend_access_enabled=backend_access_enabled(),
        data_encryption_enabled=encryption_enabled(),
        **soc,
    )


@router.get("/status", response_model=schemas.StatusOut)
def status(db: Session = Depends(get_db)):
    return _montar_status(db)


@router.patch("/settings/full", response_model=schemas.StatusOut)
def atualizar_full_runtime(
    body: schemas.FullRuntimePatch,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    rc = db.get(models.RuntimeConfig, 1)
    if rc is None:
        rc = models.RuntimeConfig(
            id=1,
            full_scan_active=True,
            full_scan_interval_seconds=settings.full_scan_interval_seconds,
            full_scan_exec_time="08:00",
            full_lote_size=settings.full_lote_size,
            full_intervalo_lote_min=settings.full_intervalo_lote_min,
            full_rescan_horas=settings.full_rescan_horas,
            full_modo_ativo=True,
        )
        db.add(rc)
        db.flush()

    if body.full_scan_active is not None:
        rc.full_scan_active = body.full_scan_active
    if body.full_scan_interval_seconds is not None:
        rc.full_scan_interval_seconds = max(10, min(3600, body.full_scan_interval_seconds))
    if body.full_scan_exec_time is not None:
        rc.full_scan_exec_time = body.full_scan_exec_time
    if body.full_lote_size is not None:
        rc.full_lote_size = max(1, min(200, body.full_lote_size))
    if body.full_intervalo_lote_min is not None:
        rc.full_intervalo_lote_min = max(0, min(240, body.full_intervalo_lote_min))
    if body.full_rescan_horas is not None:
        rc.full_rescan_horas = max(0, min(72, body.full_rescan_horas))
    if body.full_modo_ativo is not None:
        rc.full_modo_ativo = body.full_modo_ativo
    if body.full_assinatura_id is not None:
        # 0 ou null limpa
        if body.full_assinatura_id == 0:
            rc.full_assinatura_id = None
        else:
            if not db.get(models.Assinatura, body.full_assinatura_id):
                from fastapi import HTTPException
                raise HTTPException(400, "Assinatura inexistente")
            rc.full_assinatura_id = body.full_assinatura_id

    db.commit()
    db.refresh(rc)
    return _montar_status(db)


@router.get("/health")
def health():
    return {"ok": True}
