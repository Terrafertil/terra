"""Webhooks autenticados de entrega da Brevo."""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import get_db
from ..services.rate_limit_service import limiter


router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
_TRACKING_RE = re.compile(r"(?:^|[;,\s])envio_id:(\d+)(?:$|[;,\s])")
_DELIVERY_EVENTS = {
    "request": "accepted",
    "delivered": "delivered",
    "deferred": "deferred",
    "soft_bounce": "soft_bounce",
    "hard_bounce": "hard_bounce",
    "blocked": "blocked",
    "invalid_email": "invalid_email",
    "spam": "spam",
    "error": "error",
}


def _authorize(request: Request) -> None:
    expected = (settings.brevo_webhook_token or "").strip()
    if len(expected) < 32:
        raise HTTPException(503, "Webhook Brevo ainda nÃ£o configurado.")
    authorization = request.headers.get("Authorization", "")
    supplied = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "Webhook nÃ£o autorizado.")


@router.post("/brevo")
async def webhook_brevo(request: Request, db: Session = Depends(get_db)):
    _authorize(request)
    ip = request.client.host if request.client else "desconhecido"
    limiter.check(f"webhook-brevo:{ip}", limit=300, window_seconds=60)

    try:
        content_length = int(request.headers.get("Content-Length", "0") or 0)
    except ValueError as exc:
        raise HTTPException(400, "Content-Length inválido.") from exc
    if content_length > 64 * 1024:
        raise HTTPException(413, "Payload de webhook muito grande.")
    raw = await request.body()
    if len(raw) > 64 * 1024:
        raise HTTPException(413, "Payload de webhook muito grande.")
    try:
        payload = json.loads(raw or b"{}")
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "JSON invÃ¡lido.") from exc

    event = str(payload.get("event") or "").strip().lower()
    message_id = str(payload.get("message-id") or "").strip()
    custom = str(payload.get("X-Mailin-custom") or "")

    envio: models.Envio | None = None
    match = _TRACKING_RE.search(f" {custom} ")
    if match:
        envio = db.get(models.Envio, int(match.group(1)))
    if envio is None and message_id:
        candidates = {message_id, message_id.strip("<>")}
        envio = (
            db.query(models.Envio)
            .filter(models.Envio.provider_message_id.in_(candidates))
            .first()
        )
    if envio is None:
        return {"ok": True, "matched": False}

    if message_id:
        envio.provider_message_id = message_id
    falhas_terminais = {
        "soft_bounce",
        "hard_bounce",
        "bounce",
        "blocked",
        "invalid",
        "error",
        "deferred",
    }
    if event in _DELIVERY_EVENTS:
        envio.delivery_status = _DELIVERY_EVENTS[event]
    elif event in {"opened", "unique_opened", "proxy_open", "click"}:
        # Não sobrescreve entregue nem falhas terminais (bounce/blocked).
        atual = (envio.delivery_status or "").lower()
        if atual not in falhas_terminais | {"delivered"}:
            envio.delivery_status = event
    timestamp = payload.get("ts_event") or payload.get("ts")
    try:
        envio.delivery_updated_at = datetime.utcfromtimestamp(int(timestamp))
    except (TypeError, ValueError, OSError):
        envio.delivery_updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "matched": True, "envio_id": envio.id}
