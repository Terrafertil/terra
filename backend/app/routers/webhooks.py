"""Webhooks autenticados de entrega da Brevo."""
from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import get_db
from ..services.rate_limit_service import limiter


router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)

_MAX_PAYLOAD_BYTES = 64 * 1024
_TRACKING_RE = re.compile(
    r"(?:^|[;,&\s])envio_id\s*[:=]\s*(\d+)(?:$|[;,&\s])",
    re.IGNORECASE,
)
_CAMEL_CASE_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

_EVENT_ALIASES = {
    "sent": "request",
    "hardbounce": "hard_bounce",
    "softbounce": "soft_bounce",
    "invalid": "invalid_email",
    "complaint": "spam",
    "uniqueopened": "unique_opened",
    "proxyopen": "proxy_open",
    "uniqueproxyopen": "unique_proxy_open",
}
_TRANSIENT_EVENTS = {"request", "deferred"}
_ENGAGEMENT_EVENTS = {
    "opened",
    "unique_opened",
    "proxy_open",
    "unique_proxy_open",
    "click",
}
_FAILURE_LABELS = {
    "soft_bounce": "falha temporária de entrega (soft bounce)",
    "hard_bounce": "falha permanente de entrega (hard bounce)",
    "bounce": "falha de entrega",
    "blocked": "entrega bloqueada",
    "invalid_email": "endereço de e-mail inválido",
    "error": "erro de entrega",
    "spam": "mensagem denunciada como spam",
    "unsubscribed": "cancelamento de inscrição pelo destinatário",
}
_NON_RETRYABLE_FAILURES = {"spam", "unsubscribed"}
_TERMINAL_EVENTS = {"delivered", *_FAILURE_LABELS}
_KNOWN_EVENTS = _TRANSIENT_EVENTS | _ENGAGEMENT_EVENTS | _TERMINAL_EVENTS
_EVENT_PRIORITY = {
    "request": 10,
    "deferred": 20,
    "opened": 30,
    "unique_opened": 30,
    "proxy_open": 30,
    "unique_proxy_open": 30,
    "click": 30,
    # Uma confirmação de entrega é evidência mais forte que bounces/erros com o
    # mesmo segundo. Spam permanece acima, pois é uma reclamação pós-entrega.
    "delivered": 65,
    "soft_bounce": 50,
    "bounce": 60,
    "hard_bounce": 60,
    "blocked": 60,
    "invalid_email": 60,
    "error": 60,
    "spam": 70,
    "unsubscribed": 70,
}


def _authorize(request: Request) -> None:
    expected = (settings.brevo_webhook_token or "").strip()
    if not settings.webhook_configured:
        raise HTTPException(503, "Webhook Brevo ainda não configurado.")
    authorization = request.headers.get("Authorization", "")
    supplied = (
        authorization[7:].strip()
        if authorization.lower().startswith("bearer ")
        else ""
    )
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "Webhook não autorizado.")


def _payload_value(payload: dict[str, Any], name: str) -> Any:
    """Lê campos da Brevo sem depender da capitalização dos cabeçalhos customizados."""
    if name in payload:
        return payload[name]
    wanted = name.casefold()
    for key, value in payload.items():
        if str(key).casefold() == wanted:
            return value
    return None


def _normalize_event(value: Any) -> str:
    raw = str(value or "").strip()
    raw = _CAMEL_CASE_RE.sub("_", raw).replace("-", "_").replace(" ", "_")
    event = re.sub(r"_+", "_", raw).strip("_").lower()
    return _EVENT_ALIASES.get(event, event)


def _normalize_message_id(value: Any) -> str:
    return str(value or "").strip().strip("<>").strip()


def _message_id_candidates(value: Any) -> tuple[str, ...]:
    original = str(value or "").strip()
    normalized = _normalize_message_id(original)
    if not normalized:
        return ()
    return tuple({original, normalized, f"<{normalized}>"})


def _find_by_message_id(db: Session, message_id: str) -> models.Envio | None:
    candidates = _message_id_candidates(message_id)
    if not candidates:
        return None
    return (
        db.query(models.Envio)
        .filter(models.Envio.provider_message_id.in_(candidates))
        .first()
    )


def _match_envio(
    db: Session, payload: dict[str, Any]
) -> tuple[models.Envio | None, str]:
    """Correlaciona por tracking e message-id, recusando identificadores conflitantes."""
    custom = str(_payload_value(payload, "X-Mailin-custom") or "")
    message_id = str(_payload_value(payload, "message-id") or "").strip()

    tracking_envio: models.Envio | None = None
    match = _TRACKING_RE.search(f" {custom} ")
    if match:
        tracking_envio = db.get(models.Envio, int(match.group(1)))

    message_envio = _find_by_message_id(db, message_id)
    if (
        tracking_envio is not None
        and message_envio is not None
        and tracking_envio.id != message_envio.id
    ):
        # Não há uma escolha segura: atualizar qualquer um dos registros poderia
        # atribuir a entrega de um cliente ao envio de outro.
        log.warning(
            "Webhook Brevo ignorado: tracking do envio %s conflita com message-id "
            "do envio %s.",
            tracking_envio.id,
            message_envio.id,
        )
        return None, message_id

    return tracking_envio or message_envio, message_id


def _event_datetime(payload: dict[str, Any]) -> tuple[datetime, bool]:
    for field in ("ts_event", "ts", "ts_epoch"):
        value = _payload_value(payload, field)
        if value is None or isinstance(value, bool):
            continue
        try:
            timestamp = float(value)
            # ts_epoch é documentado em milissegundos, mas algumas integrações
            # enviam segundos. A magnitude permite aceitar os dois formatos.
            if timestamp > 100_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(
                tzinfo=None
            ), True
        except (TypeError, ValueError, OSError, OverflowError):
            continue
    return datetime.now(timezone.utc).replace(tzinfo=None), False


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _should_apply_event(
    envio: models.Envio,
    event: str,
    event_at: datetime,
    has_provider_timestamp: bool,
) -> bool:
    current = _normalize_event(envio.delivery_status)
    current_at = envio.delivery_updated_at

    # Reclamação e descadastro são bloqueios de consentimento. Nenhum evento de
    # transporte posterior pode reabrir o envio; somente outro bloqueio equivalente
    # pode complementar o estado.
    if current in _NON_RETRYABLE_FAILURES and event not in _NON_RETRYABLE_FAILURES:
        return False

    if has_provider_timestamp and current_at is not None:
        # A Brevo usa segundos; o estado local de aceite SMTP possui microssegundos.
        # Comparar nessa mesma resolução evita descartar o primeiro webhook do envio.
        incoming_second = event_at.replace(microsecond=0)
        current_second = _utc_naive(current_at).replace(microsecond=0)
        if incoming_second < current_second:
            return False
        if (
            incoming_second == current_second
            and _EVENT_PRIORITY.get(event, 0) < _EVENT_PRIORITY.get(current, 0)
        ):
            return False

    # Aceite, adiamento e interação são informativos e nunca podem apagar uma
    # confirmação ou falha terminal, mesmo quando chegam fora de ordem.
    if event not in _TERMINAL_EVENTS:
        if current in _TERMINAL_EVENTS:
            return False
        if _EVENT_PRIORITY.get(event, 0) < _EVENT_PRIORITY.get(current, 0):
            return False

    return True


def _failure_message(
    event: str,
    payload: dict[str, Any],
    *,
    previous_event: str = "",
    previous_message: str = "",
) -> str:
    label = _FAILURE_LABELS[event]
    reason = ""
    for field in ("reason", "description", "message", "response", "error"):
        candidate = _payload_value(payload, field)
        if candidate not in (None, ""):
            reason = re.sub(r"\s+", " ", str(candidate)).strip()[:1000]
            break

    if (
        not reason
        and previous_message
        and previous_event == event
        and (
            event not in _NON_RETRYABLE_FAILURES
            or "reenvio está bloqueado" in previous_message.casefold()
        )
    ):
        # Uma repetição sem motivo não deve apagar a resposta detalhada recebida
        # anteriormente para a mesma falha.
        return previous_message[:2000]

    message = f"Brevo informou {label}."
    detail = ""
    if reason:
        message += f" Motivo: {reason}."
    elif previous_message:
        detail = re.sub(r"\s+", " ", previous_message).strip()
        # Remove a orientação antiga de retry caso uma reclamação/cancelamento
        # chegue depois de outro erro reenviável.
        if event in _NON_RETRYABLE_FAILURES:
            detail = detail.split(" Revise o destinatário", 1)[0]
            detail = detail.split(" O reenvio está bloqueado", 1)[0]
            if "reenvi" in detail.casefold():
                detail = ""
        detail = detail[:1200]
    if detail:
        message += f" Detalhe anterior preservado: {detail}"
    if event in _NON_RETRYABLE_FAILURES:
        message += (
            " O reenvio está bloqueado para respeitar a preferência do "
            "destinatário; confirme o consentimento antes de qualquer novo contato."
        )
    else:
        message += " Revise o destinatário e tente reenviar pelo histórico."
    return message[:2000]


def _apply_event(
    envio: models.Envio,
    event: str,
    payload: dict[str, Any],
) -> bool:
    if event not in _KNOWN_EVENTS:
        return False

    event_at, has_provider_timestamp = _event_datetime(payload)
    if not _should_apply_event(envio, event, event_at, has_provider_timestamp):
        return False

    previous_event = _normalize_event(envio.delivery_status)
    previous_error = (envio.erro_msg or "").strip()
    envio.delivery_status = "accepted" if event == "request" else event
    envio.delivery_updated_at = event_at

    if event == "delivered":
        # Uma entrega posterior a um soft bounce é o desfecho definitivo da
        # tentativa: restaura o sucesso e remove a mensagem que abria reenvio.
        envio.status = "enviado"
        envio.erro_msg = None
    elif event in _FAILURE_LABELS:
        # Falhas ficam visíveis como erro. A camada de envio permite retry das
        # falhas operacionais e bloqueia spam/descadastro por consentimento.
        envio.status = "erro"
        envio.erro_msg = _failure_message(
            event,
            payload,
            previous_event=previous_event,
            previous_message=previous_error,
        )

    return True


@router.post("/brevo")
async def webhook_brevo(request: Request, db: Session = Depends(get_db)):
    _authorize(request)
    ip = request.client.host if request.client else "desconhecido"
    limiter.check(f"webhook-brevo:{ip}", limit=300, window_seconds=60)

    try:
        content_length = int(request.headers.get("Content-Length", "0") or 0)
    except ValueError as exc:
        raise HTTPException(400, "Content-Length inválido.") from exc
    if content_length > _MAX_PAYLOAD_BYTES:
        raise HTTPException(413, "Payload de webhook muito grande.")
    raw = await request.body()
    if len(raw) > _MAX_PAYLOAD_BYTES:
        raise HTTPException(413, "Payload de webhook muito grande.")
    try:
        payload = json.loads(raw or b"{}")
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "JSON inválido.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(400, "Payload do webhook deve ser um objeto JSON.")

    event = _normalize_event(_payload_value(payload, "event"))
    envio, message_id = _match_envio(db, payload)
    if envio is None:
        log.warning(
            "Webhook Brevo sem correspondência segura: evento=%s message_id=%s",
            event or "-",
            message_id or "-",
        )
        return {"ok": True, "matched": False}

    changed = False
    if event in _KNOWN_EVENTS and message_id and not envio.provider_message_id:
        # Não substitui o identificador da tentativa atual. Isso impede que um
        # webhook atrasado de uma tentativa anterior passe a identificar o retry.
        envio.provider_message_id = message_id
        changed = True
    changed = _apply_event(envio, event, payload) or changed

    if changed:
        db.commit()
        log.info(
            "Webhook Brevo aplicado: envio_id=%s evento=%s delivery_status=%s",
            envio.id,
            event,
            envio.delivery_status,
        )
    elif event not in _KNOWN_EVENTS:
        log.info(
            "Webhook Brevo ignorado: envio_id=%s evento desconhecido=%s",
            envio.id,
            event or "-",
        )
    return {"ok": True, "matched": True, "envio_id": envio.id}
