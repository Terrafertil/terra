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
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from . import email_service, backup_service, pdf_service, soc_service, file_provenance


log = logging.getLogger(__name__)


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
    corpo_email_id: int | None = None,
    assinatura_id: int | None = None,
    nome_arquivo_original: str | None = None,
    pdf_senha: str | None = None,
    usuario_envio: models.Usuario | None = None,
    arquivo_colocado_por: str | None = None,
) -> models.Envio:
    if soc_service.is_soc_locked(db):
        raise ValueError(soc_service.SOC_BLOCK_MSG)

    caminho_pdf = Path(caminho_pdf)
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

    assin = _resolver_assinatura(db, tipo_envio=tipo_envio, override_id=assinatura_id)
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
    elif (tipo_envio or "").upper() == "FULL":
        enviado_por = "FULL (automático)"
        uid = None
    else:
        enviado_por = None
        uid = None

    envio = models.Envio(
        cliente_id=cliente.id,
        tipo_envio=tipo_envio,
        tipo_codigo=tipo_codigo,
        nome_arquivo_original=nome_arquivo_original or caminho_pdf.name,
        nome_arquivo_final=nome_final,
        numero_apolice=numero_apolice,
        status="pendente",
        assinatura_id=assin.id if assin else None,
        usuario_envio_id=uid if uid else None,
        enviado_por=enviado_por,
        arquivo_colocado_por=(arquivo_colocado_por or "").strip() or None,
    )
    db.add(envio)
    db.commit()
    db.refresh(envio)

    try:
        # 1) backup
        destino = backup_service.copiar_para_backup(
            pdf_final, cliente.nome, nome_arquivo_destino=nome_final
        )
        envio.caminho_backup = str(destino)

        # 2) e-mail
        ctx = _montar_contexto(
            cliente=cliente,
            auto=auto,
            numero_apolice=numero_apolice,
            tipo_envio=tipo_envio,
            tipo_codigo=tipo_codigo,
        )
        assunto = assunto_customizado or email_service.formatar_assunto(
            numero_apolice, custom=(corpo.assunto if corpo else None)
        )
        corpo_html = email_service.renderizar_template(
            contexto=ctx,
            template_html=(corpo.html if corpo and corpo.html else None),
            assinatura_cid=cid,
        )
        email_service.enviar_email(
            destinatario=cliente.email,
            assunto=assunto,
            corpo_html=corpo_html,
            anexos=[pdf_final],
            nome_anexo_pdf=nome_final if temp_mesclado is not None else None,
            assinatura_path=assin_path,
            assinatura_cid=cid,
        )

        envio.assunto_email = assunto
        envio.status = "enviado"
        envio.enviado_em = datetime.utcnow()
    except Exception as exc:
        envio.status = "erro"
        envio.erro_msg = str(exc)[:2000]
    finally:
        if temp_mesclado is not None:
            temp_mesclado.unlink(missing_ok=True)
        if temp_desbloqueio is not None:
            temp_desbloqueio.unlink(missing_ok=True)
        db.commit()
        db.refresh(envio)

    return envio


def reenviar_envio(db: Session, envio_id: int) -> models.Envio:
    """Reenvia e-mail de um envio com erro, usando o PDF em backup."""
    envio = db.get(models.Envio, envio_id)
    if not envio:
        raise ValueError("Envio não encontrado")
    if envio.status != "erro":
        raise ValueError("Só é possível reenviar envios com status erro")

    cliente = db.get(models.Cliente, envio.cliente_id)
    if not cliente:
        raise ValueError("Cliente do envio não encontrado")

    if not envio.caminho_backup:
        raise ValueError("Envio sem ficheiro de backup — não é possível reenviar")

    pdf = Path(envio.caminho_backup)
    if not pdf.is_file():
        raise ValueError(f"Backup não encontrado: {envio.caminho_backup}")

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

    envio.status = "pendente"
    envio.erro_msg = None
    db.commit()

    try:
        ctx = _montar_contexto(
            cliente=cliente,
            auto=None,
            numero_apolice=envio.numero_apolice,
            tipo_envio=envio.tipo_envio,
            tipo_codigo=envio.tipo_codigo,
        )
        assunto = envio.assunto_email or email_service.formatar_assunto(
            envio.numero_apolice, custom=(corpo.assunto if corpo else None)
        )
        corpo_html = email_service.renderizar_template(
            contexto=ctx,
            template_html=(corpo.html if corpo and corpo.html else None),
            assinatura_cid=cid,
        )
        email_service.enviar_email(
            destinatario=cliente.email,
            assunto=assunto,
            corpo_html=corpo_html,
            anexos=[pdf],
            nome_anexo_pdf=envio.nome_arquivo_final or pdf.name,
            assinatura_path=assin_path,
            assinatura_cid=cid,
        )
        envio.assunto_email = assunto
        envio.status = "enviado"
        envio.enviado_em = datetime.utcnow()
    except Exception as exc:
        envio.status = "erro"
        envio.erro_msg = str(exc)[:2000]
    finally:
        db.commit()
        db.refresh(envio)

    return envio


def reenviar_envios_com_erro(db: Session, *, dias: int = 30) -> dict:
    """Tenta reenviar todos os envios com erro nos últimos N dias."""
    from datetime import timedelta

    limite = datetime.utcnow() - timedelta(days=max(1, dias))
    envios = (
        db.query(models.Envio)
        .filter(models.Envio.status == "erro", models.Envio.criado_em >= limite)
        .order_by(models.Envio.criado_em.asc())
        .all()
    )
    itens = []
    sucesso = 0
    for e in envios:
        try:
            atualizado = reenviar_envio(db, e.id)
            ok = atualizado.status == "enviado"
            if ok:
                sucesso += 1
            itens.append(
                {
                    "envio_id": e.id,
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
