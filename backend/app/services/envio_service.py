"""Orquestra o ciclo completo de um envio (MANUAL ou FULL).

Passos:
1. Resolve corpo de e-mail (associado ao tipo) + assinatura
2. Junta capa (PDF) + apólice se capa.pdf existir
3. Copia para backup
4. Envia e-mail (com placeholders renderizados, assinatura inline)
5. Registra na tabela de envios com status final
"""
from __future__ import annotations

import logging
import base64
import hashlib
import hmac
import mimetypes
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, aliased, object_session
from sqlalchemy.exc import IntegrityError

from .. import models
from ..config import settings
from . import email_service, backup_service, pdf_service, soc_service, file_provenance


log = logging.getLogger(__name__)


FALHAS_ENTREGA_REENVIAVEIS = frozenset(
    {
        "soft_bounce",
        "hard_bounce",
        "bounce",
        "blocked",
        "invalid",
        "invalid_email",
        "error",
    }
)
FALHAS_ENTREGA_NAO_REENVIAVEIS = frozenset({"spam", "unsubscribed"})


def _normalizar_email_destinatario(email: str | None) -> str:
    """Forma estável usada apenas para comparar destinatários."""
    return (email or "").strip().casefold()


def _falha_de_entrega(envio: models.Envio) -> bool:
    status = getattr(envio, "delivery_status", None)
    return (status or "").strip().casefold() in FALHAS_ENTREGA_REENVIAVEIS


def _bloqueio_de_reenvio(envio: models.Envio) -> bool:
    status = getattr(envio, "delivery_status", None)
    return (status or "").strip().casefold() in FALHAS_ENTREGA_NAO_REENVIAVEIS


def _possui_reenvio(db: Session, envio_id: int) -> bool:
    return (
        db.query(models.Envio.id)
        .filter(models.Envio.reenvio_de_id == envio_id)
        .first()
        is not None
    )


def _folha_da_cadeia(db: Session, envio: models.Envio) -> models.Envio:
    atual = envio
    visitados: set[int] = set()
    while atual.id is not None and atual.id not in visitados:
        visitados.add(atual.id)
        filho = (
            db.query(models.Envio)
            .filter(models.Envio.reenvio_de_id == atual.id)
            .first()
        )
        if filho is None:
            break
        atual = filho
    return atual


def _tentativa_mais_recente_do_contexto(
    db: Session,
    dono_da_chave: models.Envio,
    *,
    key: str,
    destinatario_email: str | None,
) -> models.Envio:
    """Segue a cadeia sem misturar tentativas feitas para outro endereço."""
    atual = dono_da_chave
    contextual = dono_da_chave
    email_normalizado = _normalizar_email_destinatario(destinatario_email)
    visitados: set[int] = set()
    while atual.id is not None and atual.id not in visitados:
        visitados.add(atual.id)
        filho = (
            db.query(models.Envio)
            .filter(models.Envio.reenvio_de_id == atual.id)
            .first()
        )
        if filho is None:
            break
        filho_email = _normalizar_email_destinatario(
            getattr(filho, "destinatario_email", None)
        )
        if filho.idempotency_key == key or (
            filho.idempotency_key is None
            and email_normalizado
            and filho_email == email_normalizado
        ):
            contextual = filho
        atual = filho
    return contextual


def envio_pode_reenviar(envio: models.Envio) -> bool:
    elegivel = (
        bool(getattr(envio, "caminho_backup", None))
        and not _bloqueio_de_reenvio(envio)
        and (envio.status == "erro" or _falha_de_entrega(envio))
    )
    if not elegivel:
        return False
    tem_reenvio = getattr(envio, "_tem_reenvio", None)
    if tem_reenvio is not None:
        return not bool(tem_reenvio)
    try:
        db = object_session(envio)
    except Exception:
        db = None
    envio_id = getattr(envio, "id", None)
    return not bool(db and envio_id and _possui_reenvio(db, envio_id))


def _arquivo_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _chave_idempotencia(
    *,
    arquivo_sha256: str,
    boleto_sha256: str,
    cliente_id: int,
    destinatario_email: str,
    tipo_envio: str,
    tipo_codigo: str | None,
) -> str:
    raw = ":".join(
        [
            arquivo_sha256,
            boleto_sha256,
            str(cliente_id),
            _normalizar_email_destinatario(destinatario_email),
            (tipo_envio or "").upper(),
            tipo_codigo or "",
        ]
    )
    segredo = (settings.secret_key or "").encode("utf-8")
    return hmac.new(
        segredo,
        f"envio-idempotencia:v2:{raw}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _envio_existente_idempotente(
    db: Session,
    key: str,
    *,
    destinatario_email: str | None = None,
) -> models.Envio | None:
    """Evita duplicar envio bem-sucedido; permite nova tentativa após erro/pendente antigo."""
    dono_da_chave = (
        db.query(models.Envio)
        .filter(models.Envio.idempotency_key == key)
        .first()
    )
    if not dono_da_chave:
        return None
    envio = _tentativa_mais_recente_do_contexto(
        db,
        dono_da_chave,
        key=key,
        destinatario_email=destinatario_email,
    )

    # Reclamação de spam/descadastro é um bloqueio de conformidade, não
    # uma falha operacional. Nunca liberta a chave para reenvio automático.
    if _bloqueio_de_reenvio(envio):
        envio.deduplicado = True
        return envio

    # Uma rejeição posterior do provedor não é sucesso. Liberta a chave
    # para o FULL poder tentar novamente se o ficheiro voltar à entrada.
    if _falha_de_entrega(envio):
        dono_da_chave.idempotency_key = _chave_idempotencia_retirada(
            key, dono_da_chave.id
        )
        db.commit()
        return None

    # Já aceite pelo SMTP — não reenviar automaticamente no FULL.
    if envio.status == "enviado":
        envio.deduplicado = True
        return envio

    # Ainda em processamento recente — devolver o mesmo registo.
    if envio.status == "pendente":
        idade = datetime.utcnow() - (envio.criado_em or datetime.utcnow())
        if idade.total_seconds() < 120:
            envio.deduplicado = True
            return envio
        envio.status = "erro"
        envio.erro_msg = (
            "Envio anterior ficou em estado incerto. A chave de idempotência foi "
            "libertada para permitir nova tentativa automática ou manual."
        )

    # erro / pendente antigo: liberta a chave única para nova tentativa.
    if envio.status == "erro":
        dono_da_chave.idempotency_key = _chave_idempotencia_retirada(
            key, dono_da_chave.id
        )
        db.commit()
        return None

    return None


def _chave_idempotencia_retirada(key: str, envio_id: int) -> str:
    """Mantém a chave aposentada dentro do limite VARCHAR(64)."""
    digest = hashlib.sha256(
        f"{key}:retired:{envio_id}:{uuid.uuid4().hex}".encode("utf-8")
    ).hexdigest()
    return f"retired:{digest[:56]}"


def _copiar_para_recuperacao(
    origem: Path,
    *,
    envio_id: int,
    rotulo: str,
) -> Path | None:
    """Cria uma cópia recuperável fora do backup principal que falhou."""
    if not origem.is_file():
        return None
    try:
        pasta = settings.data_path(settings.upload_folder) / "recuperacao"
        pasta.mkdir(parents=True, exist_ok=True)
        sufixo = origem.suffix if origem.suffix else ".pdf"
        destino = pasta / f"envio_{envio_id}_{rotulo}_{uuid.uuid4().hex}{sufixo}"
        shutil.copy2(origem, destino)
        return destino
    except Exception as exc:
        log.exception("Não foi possível criar cópia de recuperação: %s", exc)
        return None


def _resolver_caminho_capa() -> Path | None:
    if not settings.capa_enabled:
        return None
    capa = settings.data_path(settings.capa_folder) / settings.capa_arquivo_padrao
    if capa.is_file():
        log.info("Capa a usar: %s", capa)
        return capa
    log.info("Capa não aplicada (ficheiro inexistente): %s", capa)
    return None


def _preparar_pdf_final(original: Path) -> tuple[Path, str, Path | None]:
    capa = _resolver_caminho_capa()
    if not capa:
        return original, original.name, None
    tmp = Path(tempfile.gettempdir()) / f"envio_mesclado_{uuid.uuid4().hex}.pdf"
    try:
        pdf_service.mesclar_capa_e_apolice(capa, original, tmp)
        nome = f"com_capa_{original.name}"
        log.info("PDF mesclado com capa: %s + %s -> %s", capa.name, original.name, nome)
        return tmp, nome, tmp
    except Exception as e:
        log.exception("Junção com capa falhou; usa PDF original. Erro: %s", e)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return original, original.name, None


def _resolver_corpo_email(
    db: Session, tipo_codigo: str | None
) -> models.CorpoEmail | None:
    if not tipo_codigo:
        return None
    tipo = (
        db.query(models.TipoEnvio)
        .filter(models.TipoEnvio.codigo == tipo_codigo)
        .first()
    )
    if not tipo or not tipo.corpo_email_id:
        return None
    return db.get(models.CorpoEmail, tipo.corpo_email_id)


def _resolver_assinatura(
    db: Session, *, tipo_envio: str, override_id: int | None = None
) -> models.Assinatura | None:
    if override_id:
        a = db.get(models.Assinatura, override_id)
        if a and a.ativo:
            return a
    if tipo_envio == "FULL":
        rc = db.get(models.RuntimeConfig, 1)
        if rc and rc.full_assinatura_id:
            a = db.get(models.Assinatura, rc.full_assinatura_id)
            if a and a.ativo:
                return a
    return None


def _montar_contexto(
    *,
    cliente: models.Cliente,
    auto: models.Auto | None,
    numero_apolice: str | None,
    tipo_envio: str,
    tipo_codigo: str | None,
) -> dict[str, Any]:
    return {
        # Cliente
        "nome": cliente.nome or "",
        "email": cliente.email or "",
        "cpf": cliente.cpf or "",
        "cnpj": cliente.cnpj or "",
        "telefone": cliente.telefone or "",
        # Apólice
        "numero_apolice": numero_apolice or "",
        "tipo_envio": tipo_envio,
        "tipo_codigo": tipo_codigo or "",
        "data_envio": datetime.now().strftime("%d/%m/%Y"),
        "seguradora": "",
        "produto": "",
        "layout_apolice": "",
        # Auto
        "placa": (auto.placa if auto else "") or "",
        "marca": (auto.marca if auto else "") or "",
        "modelo": (auto.modelo if auto else "") or "",
        "ano": (auto.ano if auto else "") or "",
        # Outros
        "from_name": settings.smtp_from_name,
    }


def _assinatura_data_uri(path: Path) -> str | None:
    """Converte a imagem da assinatura em data URI para pré-visualização no browser."""
    if not path.is_file():
        return None
    ctype, _ = mimetypes.guess_type(path.name)
    if not ctype or not ctype.startswith("image/"):
        ctype = "image/png"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{ctype};base64,{encoded}"


def renderizar_demonstracao(
    db: Session,
    *,
    cliente: models.Cliente,
    auto: models.Auto | None = None,
    numero_apolice: str | None = None,
    tipo_envio: str = "MANUAL",
    tipo_codigo: str | None = None,
    assinatura_id: int | None = None,
    corpo_email_id: int | None = None,
) -> dict[str, Any]:
    """Gera dict com os dados que apareceriam no e-mail (assunto + html), sem enviar."""
    corpo = None
    if corpo_email_id:
        corpo = db.get(models.CorpoEmail, corpo_email_id)
    if corpo is None:
        corpo = _resolver_corpo_email(db, tipo_codigo)

    assin = _resolver_assinatura(db, tipo_envio=tipo_envio, override_id=assinatura_id)
    cid = email_service.gerar_cid() if assin and assin.arquivo else None
    assin_path: Path | None = None
    if assin and assin.arquivo:
        assin_path = settings.data_path(settings.assinaturas_folder) / assin.arquivo

    ctx = _montar_contexto(
        cliente=cliente,
        auto=auto,
        numero_apolice=numero_apolice,
        tipo_envio=tipo_envio,
        tipo_codigo=tipo_codigo,
    )

    assunto = email_service.formatar_assunto(
        numero_apolice, custom=(corpo.assunto if corpo else None)
    )
    html = email_service.renderizar_template(
        contexto=ctx,
        template_html=(corpo.html if corpo and corpo.html else None),
        assinatura_cid=cid,
    )
    # No browser, cid: não carrega; troca pela data URI só na demonstração.
    if cid and assin_path:
        data_uri = _assinatura_data_uri(assin_path)
        if data_uri:
            html = html.replace(f"cid:{cid}", data_uri)
    return {
        "de": f"{settings.smtp_from_name} <{settings.smtp_from_email}>",
        "para": cliente.email,
        "assunto": assunto,
        "html": html,
    }


def processar_envio(
    db: Session,
    *,
    cliente: models.Cliente,
    caminho_pdf: str | Path,
    tipo_envio: str,  # FULL | MANUAL
    tipo_codigo: str | None = None,
    auto: models.Auto | None = None,
    numero_apolice: str | None = None,
    assunto_customizado: str | None = None,
    corpo_html_customizado: str | None = None,
    corpo_email_id: int | None = None,
    assinatura_id: int | None = None,
    nome_arquivo_original: str | None = None,
    pdf_senha: str | None = None,
    usuario_envio: models.Usuario | None = None,
    arquivo_colocado_por: str | None = None,
    boleto_path: str | Path | None = None,
    boleto_nome_original: str | None = None,
) -> models.Envio:
    if soc_service.is_soc_locked(db):
        raise ValueError(soc_service.SOC_BLOCK_MSG)

    caminho_pdf = Path(caminho_pdf)
    boleto = Path(boleto_path) if boleto_path else None
    tipo_envio_normalizado = (tipo_envio or "").strip().upper()
    destinatario_email = (cliente.email or "").strip()
    if not destinatario_email:
        raise ValueError("Cliente sem e-mail de destinatário")
    arquivo_hash = _arquivo_sha256(caminho_pdf)
    boleto_hash = _arquivo_sha256(boleto) if boleto and boleto.is_file() else ""
    # Envios MANUAIS são uma ordem explícita do operador e nunca devem ser
    # suprimidos. A idempotência protege somente o watcher FULL.
    idempotency_key: str | None = None
    if tipo_envio_normalizado == "FULL":
        idempotency_key = _chave_idempotencia(
            arquivo_sha256=arquivo_hash,
            boleto_sha256=boleto_hash,
            cliente_id=cliente.id,
            destinatario_email=destinatario_email,
            tipo_envio=tipo_envio_normalizado,
            tipo_codigo=tipo_codigo,
        )
        existente = _envio_existente_idempotente(
            db,
            idempotency_key,
            destinatario_email=destinatario_email,
        )
        if existente:
            return existente

    temp_desbloqueio: Path | None = None
    temp_mesclado: Path | None = None
    pdf_uso, temp_desbloqueio = pdf_service.garantir_pdf_desbloqueado(
        caminho_pdf, senha=pdf_senha
    )
    pdf_final, nome_final, temp_mesclado = _preparar_pdf_final(pdf_uso)
    # Corpo de e-mail: override > tipo > template padrão
    corpo: models.CorpoEmail | None = None
    if corpo_email_id:
        corpo = db.get(models.CorpoEmail, corpo_email_id)
    if corpo is None:
        corpo = _resolver_corpo_email(db, tipo_codigo)

    assin = _resolver_assinatura(
        db, tipo_envio=tipo_envio_normalizado, override_id=assinatura_id
    )
    assin_path: Path | None = None
    cid: str | None = None
    if assin and assin.arquivo:
        p = settings.data_path(settings.assinaturas_folder) / assin.arquivo
        if p.is_file():
            assin_path = p
            cid = email_service.gerar_cid()

    if usuario_envio and getattr(usuario_envio, "id", None) not in (None, 0):
        enviado_por = file_provenance.rotulo_usuario(
            usuario_envio.nome, usuario_envio.username
        )
        uid = usuario_envio.id
    elif tipo_envio_normalizado == "FULL":
        enviado_por = "FULL (automático)"
        uid = None
    else:
        enviado_por = None
        uid = None

    envio = models.Envio(
        cliente_id=cliente.id,
        tipo_envio=tipo_envio_normalizado,
        tipo_codigo=tipo_codigo,
        nome_arquivo_original=nome_arquivo_original or caminho_pdf.name,
        nome_arquivo_final=nome_final,
        nome_boleto=(Path(boleto_nome_original).name if boleto_nome_original else None),
        numero_apolice=numero_apolice,
        destinatario_email=destinatario_email,
        status="pendente",
        arquivo_sha256=arquivo_hash,
        idempotency_key=idempotency_key,
        assinatura_id=assin.id if assin else None,
        usuario_envio_id=uid if uid else None,
        enviado_por=enviado_por,
        arquivo_colocado_por=(arquivo_colocado_por or "").strip() or None,
    )
    envio.deduplicado = False
    db.add(envio)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existente = _envio_existente_idempotente(
                db,
                idempotency_key,
                destinatario_email=destinatario_email,
            )
            if existente:
                if temp_mesclado is not None:
                    temp_mesclado.unlink(missing_ok=True)
                if temp_desbloqueio is not None:
                    temp_desbloqueio.unlink(missing_ok=True)
                return existente
        raise
    db.refresh(envio)

    etapa = "backup"
    try:
        # 1) backup
        destino = backup_service.copiar_para_backup(
            pdf_final, cliente.nome, nome_arquivo_destino=nome_final
        )
        envio.caminho_backup = str(destino)
        if boleto and boleto.is_file():
            destino_boleto = backup_service.copiar_para_backup(
                boleto,
                cliente.nome,
                nome_arquivo_destino=envio.nome_boleto or boleto.name,
            )
            envio.caminho_backup_boleto = str(destino_boleto)

        # 2) e-mail
        etapa = "smtp"
        ctx = _montar_contexto(
            cliente=cliente,
            auto=auto,
            numero_apolice=numero_apolice,
            tipo_envio=tipo_envio_normalizado,
            tipo_codigo=tipo_codigo,
        )
        assunto = assunto_customizado or email_service.formatar_assunto(
            numero_apolice, custom=(corpo.assunto if corpo else None)
        )
        corpo_html = email_service.renderizar_template(
            contexto=ctx,
            template_html=(
                corpo_html_customizado
                if corpo_html_customizado is not None
                else corpo.html if corpo and corpo.html else None
            ),
            assinatura_cid=cid,
        )
        anexos = [pdf_final]
        nomes_anexos: list[str | None] = [
            nome_final if temp_mesclado is not None else None
        ]
        if boleto and boleto.is_file():
            anexos.append(boleto)
            nomes_anexos.append(envio.nome_boleto or "boleto.pdf")
        message_id = email_service.enviar_email(
            destinatario=destinatario_email,
            assunto=assunto,
            corpo_html=corpo_html,
            anexos=anexos,
            nomes_anexos=nomes_anexos,
            assinatura_path=assin_path,
            assinatura_cid=cid,
            tracking_id=f"envio_id:{envio.id}",
        )

        envio.assunto_email = assunto
        envio.status = "enviado"
        envio.delivery_status = "accepted"
        envio.delivery_updated_at = datetime.utcnow()
        envio.provider_message_id = message_id
        envio.enviado_em = datetime.utcnow()
        envio.erro_msg = None
    except Exception as exc:
        envio.status = "erro"
        envio.erro_msg = str(exc)[:2000]
        envio._erro_etapa = etapa
        if etapa == "backup":
            # O backup principal é obrigatório antes do SMTP. Se ele falhar,
            # preserva os anexos numa área recuperável para permitir reenvio.
            if not envio.caminho_backup:
                recuperado = _copiar_para_recuperacao(
                    pdf_final, envio_id=envio.id, rotulo="apolice"
                )
                if recuperado:
                    envio.caminho_backup = str(recuperado)
                elif caminho_pdf.is_file():
                    envio.caminho_backup = str(caminho_pdf)
            if boleto and boleto.is_file() and not envio.caminho_backup_boleto:
                recuperado_boleto = _copiar_para_recuperacao(
                    boleto, envio_id=envio.id, rotulo="boleto"
                )
                envio.caminho_backup_boleto = str(recuperado_boleto or boleto)
    finally:
        if temp_mesclado is not None:
            temp_mesclado.unlink(missing_ok=True)
        if temp_desbloqueio is not None:
            temp_desbloqueio.unlink(missing_ok=True)
        db.commit()
        db.refresh(envio)

    return envio


def reenviar_envio(
    db: Session,
    envio_id: int,
    *,
    usuario_envio: models.Usuario | None = None,
) -> models.Envio:
    """Reenvia falha de processamento ou entrega usando o PDF preservado."""
    if soc_service.is_soc_locked(db):
        raise ValueError(soc_service.SOC_BLOCK_MSG)
    envio = db.get(models.Envio, envio_id)
    if not envio:
        raise ValueError("Envio não encontrado")
    if _bloqueio_de_reenvio(envio):
        raise ValueError("Reenvio bloqueado por reclamação ou descadastro do destinatário")
    if _possui_reenvio(db, envio.id):
        raise ValueError("Este envio já possui uma tentativa de reenvio")
    if not (envio.status == "erro" or _falha_de_entrega(envio)):
        raise ValueError("Só é possível reenviar envios com falha")

    cliente = db.get(models.Cliente, envio.cliente_id)
    if not cliente:
        raise ValueError("Cliente do envio não encontrado")
    destinatario_email = (cliente.email or "").strip()
    if not destinatario_email:
        raise ValueError("Cliente sem e-mail de destinatário")

    if not envio.caminho_backup:
        raise ValueError("Envio sem ficheiro de backup — não é possível reenviar")

    pdf = Path(envio.caminho_backup)
    if not pdf.is_file():
        raise ValueError(f"Backup não encontrado: {envio.caminho_backup}")

    boleto = Path(envio.caminho_backup_boleto) if envio.caminho_backup_boleto else None
    if boleto is not None and not boleto.is_file():
        raise ValueError(f"Backup do boleto não encontrado: {envio.caminho_backup_boleto}")

    arquivo_hash = envio.arquivo_sha256 or _arquivo_sha256(pdf)
    boleto_hash = _arquivo_sha256(boleto) if boleto else ""
    idempotency_key: str | None = None
    if (envio.tipo_envio or "").strip().upper() == "FULL":
        idempotency_key = _chave_idempotencia(
            arquivo_sha256=arquivo_hash,
            boleto_sha256=boleto_hash,
            cliente_id=envio.cliente_id,
            destinatario_email=destinatario_email,
            tipo_envio="FULL",
            tipo_codigo=envio.tipo_codigo,
        )
        dono_atual = (
            db.query(models.Envio)
            .filter(models.Envio.idempotency_key == idempotency_key)
            .first()
        )
        if dono_atual is not None:
            if _bloqueio_de_reenvio(_folha_da_cadeia(db, dono_atual)):
                raise ValueError(
                    "Reenvio bloqueado por reclamação ou descadastro do destinatário"
                )
            dono_atual.idempotency_key = _chave_idempotencia_retirada(
                idempotency_key, dono_atual.id
            )

    corpo = _resolver_corpo_email(db, envio.tipo_codigo)
    assin = None
    if envio.assinatura_id:
        assin = db.get(models.Assinatura, envio.assinatura_id)
    if assin is None:
        assin = _resolver_assinatura(db, tipo_envio=envio.tipo_envio)

    assin_path: Path | None = None
    cid: str | None = None
    if assin and assin.arquivo:
        p = settings.data_path(settings.assinaturas_folder) / assin.arquivo
        if p.is_file():
            assin_path = p
            cid = email_service.gerar_cid()

    if usuario_envio and getattr(usuario_envio, "id", None) not in (None, 0):
        usuario_envio_id = usuario_envio.id
        enviado_por = file_provenance.rotulo_usuario(
            usuario_envio.nome, usuario_envio.username
        )
    else:
        usuario_envio_id = None
        enviado_por = f"Reenvio do envio #{envio.id}"

    # Cada tentativa recebe uma linha e tracking próprios. Preservar a linha
    # anterior impede um webhook atrasado de sobrescrever o resultado atual.
    novo_envio = models.Envio(
        cliente_id=envio.cliente_id,
        tipo_envio=envio.tipo_envio,
        tipo_codigo=envio.tipo_codigo,
        nome_arquivo_original=envio.nome_arquivo_original,
        nome_arquivo_final=envio.nome_arquivo_final,
        nome_boleto=envio.nome_boleto,
        numero_apolice=envio.numero_apolice,
        destinatario_email=destinatario_email,
        status="pendente",
        caminho_backup=envio.caminho_backup,
        caminho_backup_boleto=envio.caminho_backup_boleto,
        arquivo_sha256=arquivo_hash,
        idempotency_key=idempotency_key,
        reenvio_de_id=envio.id,
        delivery_status="retrying",
        delivery_updated_at=datetime.utcnow(),
        assunto_email=envio.assunto_email,
        assinatura_id=assin.id if assin else envio.assinatura_id,
        usuario_envio_id=usuario_envio_id,
        enviado_por=enviado_por,
        arquivo_colocado_por=envio.arquivo_colocado_por,
    )
    novo_envio.deduplicado = False
    db.add(novo_envio)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _possui_reenvio(db, envio.id):
            raise ValueError("Este envio já possui uma tentativa de reenvio") from exc
        raise
    envio._tem_reenvio = True
    db.refresh(novo_envio)

    try:
        ctx = _montar_contexto(
            cliente=cliente,
            auto=None,
            numero_apolice=novo_envio.numero_apolice,
            tipo_envio=novo_envio.tipo_envio,
            tipo_codigo=novo_envio.tipo_codigo,
        )
        assunto = novo_envio.assunto_email or email_service.formatar_assunto(
            novo_envio.numero_apolice, custom=(corpo.assunto if corpo else None)
        )
        corpo_html = email_service.renderizar_template(
            contexto=ctx,
            template_html=(corpo.html if corpo and corpo.html else None),
            assinatura_cid=cid,
        )
        anexos = [pdf]
        nomes_anexos: list[str | None] = [novo_envio.nome_arquivo_final or pdf.name]
        if boleto:
            anexos.append(boleto)
            nomes_anexos.append(novo_envio.nome_boleto or boleto.name)
        message_id = email_service.enviar_email(
            destinatario=destinatario_email,
            assunto=assunto,
            corpo_html=corpo_html,
            anexos=anexos,
            nomes_anexos=nomes_anexos,
            assinatura_path=assin_path,
            assinatura_cid=cid,
            tracking_id=f"envio_id:{novo_envio.id}",
        )
        novo_envio.assunto_email = assunto
        novo_envio.status = "enviado"
        novo_envio.delivery_status = "accepted"
        novo_envio.delivery_updated_at = datetime.utcnow()
        novo_envio.provider_message_id = message_id
        novo_envio.enviado_em = datetime.utcnow()
    except Exception as exc:
        novo_envio.status = "erro"
        novo_envio.erro_msg = str(exc)[:2000]
        novo_envio.delivery_status = "smtp_error"
        novo_envio.delivery_updated_at = datetime.utcnow()
        novo_envio._erro_etapa = "smtp"
    finally:
        db.commit()
        db.refresh(novo_envio)

    return novo_envio


def reenviar_envios_com_erro(
    db: Session,
    *,
    dias: int = 30,
    tipo: str | None = None,
    usuario_envio: models.Usuario | None = None,
) -> dict:
    """Tenta reenviar falhas de processamento ou entrega dos últimos N dias."""
    from datetime import timedelta

    if soc_service.is_soc_locked(db):
        raise ValueError(soc_service.SOC_BLOCK_MSG)
    limite = datetime.utcnow() - timedelta(days=max(1, dias))
    filho = aliased(models.Envio)
    sem_reenvio = ~db.query(filho.id).filter(
        filho.reenvio_de_id == models.Envio.id
    ).exists()
    query = db.query(models.Envio).filter(
        or_(
            and_(
                models.Envio.status == "erro",
                func.lower(func.coalesce(models.Envio.delivery_status, "")).notin_(
                    FALHAS_ENTREGA_NAO_REENVIAVEIS
                ),
            ),
            func.lower(func.coalesce(models.Envio.delivery_status, "")).in_(
                FALHAS_ENTREGA_REENVIAVEIS
            ),
        ),
        models.Envio.criado_em >= limite,
        sem_reenvio,
    )
    if tipo:
        tipo_normalizado = tipo.strip().upper()
        if tipo_normalizado == "AVULSO":
            tipo_normalizado = "MANUAL"
        query = query.filter(models.Envio.tipo_envio == tipo_normalizado)
    envios = query.order_by(models.Envio.criado_em.asc()).all()
    itens = []
    sucesso = 0
    for e in envios:
        try:
            atualizado = reenviar_envio(
                db, e.id, usuario_envio=usuario_envio
            )
            ok = atualizado.status == "enviado"
            if ok:
                sucesso += 1
            itens.append(
                {
                    "envio_id": atualizado.id,
                    "ok": ok,
                    "status": atualizado.status,
                    "erro": atualizado.erro_msg if not ok else None,
                }
            )
        except Exception as ex:
            itens.append(
                {"envio_id": e.id, "ok": False, "status": "erro", "erro": str(ex)[:500]}
            )
    return {
        "total": len(envios),
        "sucesso": sucesso,
        "falha": len(envios) - sucesso,
        "itens": itens,
    }
