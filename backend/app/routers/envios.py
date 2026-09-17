"""Envio MANUAL (upload manual + e-mail imediato), demonstração e histórico."""
from __future__ import annotations

import csv
import io
import json
import logging
import time
import uuid
from functools import partial
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..database import SessionLocal, get_db
from .. import models, schemas
from ..auth import require_user
from ..services import (
    envio_service,
    ocr_service,
    pdf_service,
    cliente_crypto,
    file_provenance,
    destinatarios_service,
    capa_service,
)
from ..services.pdf_service import PdfRequerSenhaError, PdfSenhaInvalidaError
from ..services.upload_service import save_upload

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/envios", tags=["envios"])

# Pré-visualização same-origin (blob: costuma ser bloqueado pelo browser/CSP).
_PREVIEW_TTL_S = 30 * 60
_preview_pdfs: dict[str, tuple[Path, float]] = {}


def _limpar_previews_expiradas() -> None:
    agora = time.time()
    vencidos = [k for k, (_, exp) in _preview_pdfs.items() if exp <= agora]
    for k in vencidos:
        path, _ = _preview_pdfs.pop(k)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _guardar_preview(path: Path) -> str:
    _limpar_previews_expiradas()
    token = uuid.uuid4().hex
    _preview_pdfs[token] = (path, time.time() + _PREVIEW_TTL_S)
    return token


def _envio_out(envio: models.Envio) -> schemas.EnvioOut:
    out = schemas.EnvioOut.model_validate(envio)
    out.pode_reenviar = envio_service.envio_pode_reenviar(envio)
    out.deduplicado = bool(getattr(envio, "deduplicado", False))
    if envio.cliente:
        out.cliente_nome = envio.cliente.nome
        out.cliente_email_atual = envio.cliente.email
        try:
            out.cliente_destinatarios_atuais = destinatarios_service.do_cliente(
                envio.cliente
            )
        except ValueError:
            out.cliente_destinatarios_atuais = [envio.cliente.email]
    destinatario = envio.destinatario_email
    out.destinatario_email = destinatario
    out.destinatarios = destinatarios_service.do_snapshot(destinatario)
    qtd_manuais = max(0, int(getattr(envio, "destinatarios_manuais_qtd", 0) or 0))
    out.destinatarios_manuais = (
        out.destinatarios[-qtd_manuais:] if qtd_manuais else []
    )
    for campo in ("capas_iniciais", "capas_finais"):
        bruto = getattr(envio, f"{campo}_json", None)
        try:
            itens = json.loads(bruto or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            itens = []
        snapshots_validos = []
        if isinstance(itens, list):
            for item in itens:
                if not isinstance(item, dict):
                    continue
                try:
                    snapshots_validos.append(schemas.CapaSnapshotOut(**item))
                except (TypeError, ValueError):
                    continue
        setattr(out, campo, snapshots_validos)
    # Compatibilidade com clientes antigos da API: agora este campo também
    # representa somente o snapshot. Registros legados ficam nulos para não
    # atribuir retroativamente um destinatário que pode ter sido alterado.
    out.cliente_email = destinatario
    return out


def _marcar_envios_com_reenvio(db: Session, envios: list[models.Envio]) -> None:
    ids = [envio.id for envio in envios if envio.id is not None]
    if not ids:
        return
    pais = {
        row[0]
        for row in db.query(models.Envio.reenvio_de_id)
        .filter(models.Envio.reenvio_de_id.in_(ids))
        .all()
        if row[0] is not None
    }
    for envio in envios:
        envio._tem_reenvio = envio.id in pais


def _falha_envio_http(envio: models.Envio, etapa: str | None) -> HTTPException:
    smtp = etapa == "smtp" or envio.delivery_status == "smtp_error"
    if smtp:
        status_code = 502
        code = "smtp_send_failed"
        mensagem = "O provedor de e-mail não aceitou o envio."
    else:
        status_code = 500
        code = "email_processing_failed"
        mensagem = "O envio não foi concluído durante o processamento dos anexos."
    if envio.erro_msg:
        mensagem = f"{mensagem} {envio.erro_msg}"
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": mensagem,
            "envio_id": envio.id,
            "pode_reenviar": envio_service.envio_pode_reenviar(envio),
        },
    )


@router.get("", response_model=list[schemas.EnvioOut])
def listar(
    cliente_id: int | None = None,
    status: str | None = None,
    tipo: str | None = None,
    tipo_codigo: str | None = None,
    dias: int | None = Query(None, description="Filtrar envios dos últimos N dias"),
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    q = db.query(models.Envio).options(joinedload(models.Envio.cliente))
    if cliente_id:
        q = q.filter(models.Envio.cliente_id == cliente_id)
    if status:
        q = q.filter(models.Envio.status == status)
    if tipo:
        # aceita FULL, MANUAL e o legado AVULSO (sinônimo de MANUAL)
        t = tipo.upper()
        if t == "AVULSO":
            t = "MANUAL"
        q = q.filter(models.Envio.tipo_envio == t)
    if tipo_codigo:
        q = q.filter(models.Envio.tipo_codigo == tipo_codigo)
    if dias:
        limite = datetime.utcnow() - timedelta(days=dias)
        q = q.filter(models.Envio.criado_em >= limite)

    rows = q.order_by(models.Envio.criado_em.desc()).limit(500).all()
    _marcar_envios_com_reenvio(db, rows)
    return [_envio_out(e) for e in rows]


@router.get("/export.csv")
def exportar_csv(
    cliente_id: int | None = None,
    status: str | None = None,
    tipo: str | None = None,
    tipo_codigo: str | None = None,
    dias: int | None = Query(30, ge=1, le=3650),
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    """Exporta histórico filtrado em CSV (auditoria)."""
    q = db.query(models.Envio).options(joinedload(models.Envio.cliente))
    if cliente_id:
        q = q.filter(models.Envio.cliente_id == cliente_id)
    if status:
        q = q.filter(models.Envio.status == status)
    if tipo:
        t = tipo.upper()
        if t == "AVULSO":
            t = "MANUAL"
        q = q.filter(models.Envio.tipo_envio == t)
    if tipo_codigo:
        q = q.filter(models.Envio.tipo_codigo == tipo_codigo)
    if dias:
        limite = datetime.utcnow() - timedelta(days=dias)
        q = q.filter(models.Envio.criado_em >= limite)

    rows = q.order_by(models.Envio.criado_em.desc()).limit(10000).all()

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(
        [
            "id",
            "criado_em",
            "enviado_em",
            "tipo_envio",
            "tipo_codigo",
            "status",
            "reenvio_de_id",
            "cliente_id",
            "cliente_nome",
            "cliente_email",
            "cliente_email_atual",
            "numero_apolice",
            "arquivo",
            "enviado_por",
            "arquivo_colocado_por",
            "assunto",
            "erro",
        ]
    )
    for e in rows:
        w.writerow(
            [
                e.id,
                e.criado_em.isoformat(sep=" ") if e.criado_em else "",
                e.enviado_em.isoformat(sep=" ") if e.enviado_em else "",
                e.tipo_envio,
                e.tipo_codigo or "",
                e.status,
                e.reenvio_de_id or "",
                e.cliente_id,
                e.cliente.nome if e.cliente else "",
                e.destinatario_email or "",
                e.cliente.email if e.cliente else "",
                e.numero_apolice or "",
                e.nome_arquivo_original or "",
                e.enviado_por or "",
                e.arquivo_colocado_por or "",
                e.assunto_email or "",
                (e.erro_msg or "").replace("\n", " "),
            ]
        )

    nome = f"envios_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("/reenviar-erros", response_model=schemas.EnvioReenvioLoteOut)
def reenviar_erros_lote(
    dias: int = Query(30, ge=1, le=365),
    tipo: str | None = Query(None, description="Filtrar FULL ou MANUAL"),
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(require_user),
):
    """Reenvia em lote envios com status erro (últimos N dias)."""
    resultado = envio_service.reenviar_envios_com_erro(
        db, dias=dias, tipo=tipo, usuario_envio=usuario
    )
    return schemas.EnvioReenvioLoteOut(**resultado)


@router.post("/{eid}/reenviar", response_model=schemas.EnvioOut)
def reenviar_um(
    eid: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(require_user),
):
    try:
        envio = envio_service.reenviar_envio(
            db, eid, usuario_envio=usuario
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    etapa = getattr(envio, "_erro_etapa", None)
    db.refresh(envio)
    if envio.status != "enviado":
        raise _falha_envio_http(envio, etapa)
    envio = (
        db.query(models.Envio)
        .options(joinedload(models.Envio.cliente))
        .filter(models.Envio.id == envio.id)
        .first()
    )
    return _envio_out(envio)


@router.post("/analisar-pdf", response_model=schemas.PdfAnaliseOut)
async def analisar_pdf(
    arquivo: UploadFile = File(...),
    usar_ocr: bool = Form(True),
    pdf_senha: str | None = Form(None),
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    """Pré-visualização: layout, CPF, apólice e cliente sugerido (sem enviar)."""
    up = settings.data_path(settings.upload_folder)
    up.mkdir(parents=True, exist_ok=True)
    tmp = up / f"analise_{uuid.uuid4().hex}.pdf"
    preview_token: str | None = None
    try:
        await save_upload(arquivo, tmp, kind="pdf", allowed_suffixes={".pdf"})
        dados = await run_in_threadpool(
            partial(
                pdf_service.extrair_dados,
                tmp,
                usar_ocr=usar_ocr and settings.ocr_enabled,
                senha=pdf_senha,
            )
        )
        # Mantém cópia para iframe same-origin (evita bloqueio de blob:).
        preview_path = up / f"preview_{uuid.uuid4().hex}.pdf"
        preview_path.write_bytes(tmp.read_bytes())
        preview_token = _guardar_preview(preview_path)
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass

    cliente_id = None
    cliente_nome = None
    if dados.cpf:
        c = cliente_crypto.find_by_cpf(db, dados.cpf)
        if c:
            cliente_id, cliente_nome = c.id, c.nome
    if not cliente_id and dados.cnpj:
        c = cliente_crypto.find_by_cnpj(db, dados.cnpj)
        if c:
            cliente_id, cliente_nome = c.id, c.nome

    return schemas.PdfAnaliseOut(
        cpf=dados.cpf,
        cnpj=dados.cnpj,
        numero_apolice=dados.numero_apolice,
        nome=dados.nome,
        telefone=dados.telefone,
        layout=dados.layout,
        seguradora=dados.seguradora,
        produto=dados.produto,
        avisos=dados.avisos,
        extracao_automatica=dados.extracao_automatica,
        ocr_usado=dados.ocr_usado,
        ocr_disponivel=ocr_service.ocr_disponivel(),
        amostra_texto=dados.amostra_texto,
        cliente_sugerido_id=cliente_id,
        cliente_sugerido_nome=cliente_nome,
        requer_senha=dados.requer_senha,
        senha_invalida=dados.senha_invalida,
        preview_url=f"/api/envios/preview-pdf/{preview_token}" if preview_token else None,
    )


@router.get("/preview-pdf/{token}")
def preview_pdf(token: str, _=Depends(require_user)):
    """Serve o PDF analisado para o iframe de pré-visualização."""
    _limpar_previews_expiradas()
    item = _preview_pdfs.get(token)
    if not item:
        raise HTTPException(404, "Pré-visualização expirada ou inválida")
    path, _exp = item
    if not path.is_file():
        _preview_pdfs.pop(token, None)
        raise HTTPException(404, "Arquivo de pré-visualização não encontrado")
    return FileResponse(
        str(path),
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
    )


@router.get("/{eid}", response_model=schemas.EnvioOut)
def obter(eid: int, db: Session = Depends(get_db), _=Depends(require_user)):
    e = (
        db.query(models.Envio)
        .options(joinedload(models.Envio.cliente))
        .filter(models.Envio.id == eid)
        .first()
    )
    if not e:
        raise HTTPException(404, "Envio não encontrado")
    return _envio_out(e)


def _resolver_cliente(
    db: Session,
    cliente_id: int | None,
    cliente_novo_json: str | None,
    *,
    persistir: bool = True,
) -> models.Cliente:
    if cliente_id:
        cli = cliente_crypto.get_by_id(db, cliente_id)
        if not cli:
            raise HTTPException(404, "Cliente informado não existe")
        return cli
    if cliente_novo_json:
        try:
            dados = schemas.ClienteCreate(**json.loads(cliente_novo_json))
        except Exception as e:
            raise HTTPException(400, f"cliente_novo inválido: {e}")
        valores = dados.model_dump()
        principal = str(valores.get("email") or "").strip().casefold()
        valores["destinatarios_adicionais"] = [
            email
            for email in destinatarios_service.combinar(
                valores.get("destinatarios_adicionais") or []
            )
            if email.casefold() != principal
        ]
        cli = models.Cliente(**valores)
        if not persistir:
            # Demonstração: objeto efémero, sem commit na BD.
            return cli
        db.add(cli)
        db.commit()
        db.refresh(cli)
        return cli
    raise HTTPException(400, "Informe cliente_id OU cliente_novo")


async def _processar_request_manual(
    *,
    db: Session,
    usuario: models.Usuario,
    arquivo: UploadFile,
    boleto: UploadFile | None,
    cliente_id: int | None,
    cliente_novo: str | None,
    numero_apolice: str | None,
    assunto: str | None,
    mensagem: str | None,
    extrair_dados: bool,
    tipo_codigo: str | None,
    auto_id: int | None,
    corpo_email_id: int | None,
    assinatura_id: int | None,
    pdf_senha: str | None = None,
    destinatarios_adicionais: str | None = None,
    forma_pagamento: str | None = None,
    parcelamento: int | None = None,
    numero_proposta: str | None = None,
    item_segurado: str | None = None,
    seguradora: str | None = None,
    produto: str | None = None,
    layout_apolice: str | None = None,
    capas_iniciais_ids: str | None = None,
    capas_finais_ids: str | None = None,
):
    try:
        adicionais = destinatarios_service.parse_json(destinatarios_adicionais)
        ids_iniciais = (
            None
            if capas_iniciais_ids is None
            else capa_service.parse_ids_json(capas_iniciais_ids, "capas_iniciais_ids")
        )
        ids_finais = (
            None
            if capas_finais_ids is None
            else capa_service.parse_ids_json(capas_finais_ids, "capas_finais_ids")
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    pdf_senha = pdf_service.normalizar_senha_pdf(pdf_senha)
    cliente = _resolver_cliente(db, cliente_id, cliente_novo)

    up = settings.data_path(settings.upload_folder)
    up.mkdir(parents=True, exist_ok=True)
    nome_original = Path(arquivo.filename or "apolice.pdf").name
    nome_seguro = f"{uuid.uuid4().hex}_apolice.pdf"
    destino_up = up / nome_seguro
    await save_upload(
        arquivo,
        destino_up,
        kind="pdf",
        allowed_suffixes={".pdf"},
    )

    destino_boleto: Path | None = None
    boleto_nome_original: str | None = None
    if boleto and boleto.filename:
        boleto_nome_original = Path(boleto.filename).name
        destino_boleto = up / f"{uuid.uuid4().hex}_boleto.pdf"
        try:
            await save_upload(
                boleto,
                destino_boleto,
                kind="pdf",
                allowed_suffixes={".pdf"},
            )
        except Exception:
            destino_up.unlink(missing_ok=True)
            raise

    if extrair_dados:
        try:
            dados_pdf = await run_in_threadpool(
                partial(
                    pdf_service.extrair_dados,
                    destino_up,
                    usar_ocr=settings.ocr_enabled,
                    senha=pdf_senha,
                )
            )
            if not numero_apolice and dados_pdf.numero_apolice:
                numero_apolice = dados_pdf.numero_apolice
            seguradora = dados_pdf.seguradora or seguradora
            produto = dados_pdf.produto or produto
            layout_apolice = dados_pdf.layout or layout_apolice
            if not item_segurado:
                item_segurado = dados_pdf.produto
        except Exception as exc:
            log.warning("Falha ao extrair PDF no envio manual: %s", exc)

    auto_ok_id: int | None = None
    if auto_id:
        auto = db.get(models.Auto, auto_id)
        if auto and auto.cliente_id == cliente.id:
            auto_ok_id = auto.id

    # Sessão SQLAlchemy não é thread-safe: processar_envio abre Session própria.
    cliente_db_id = cliente.id
    usuario_db_id = usuario.id if getattr(usuario, "id", None) not in (None, 0) else None
    rotulo = file_provenance.rotulo_usuario(usuario.nome, usuario.username)

    def _processar_em_thread() -> tuple[int, str | None]:
        db_thread = SessionLocal()
        try:
            cli = cliente_crypto.get_by_id(db_thread, cliente_db_id)
            if not cli:
                raise ValueError("Cliente informado não existe")
            auto_obj = db_thread.get(models.Auto, auto_ok_id) if auto_ok_id else None
            usuario_obj = (
                db_thread.get(models.Usuario, usuario_db_id) if usuario_db_id else None
            )
            envio_thread = envio_service.processar_envio(
                db_thread,
                cliente=cli,
                caminho_pdf=destino_up,
                tipo_envio="MANUAL",
                tipo_codigo=tipo_codigo,
                auto=auto_obj,
                numero_apolice=numero_apolice,
                assunto_customizado=assunto,
                corpo_html_customizado=mensagem,
                corpo_email_id=corpo_email_id,
                assinatura_id=assinatura_id,
                nome_arquivo_original=nome_original,
                pdf_senha=pdf_senha,
                usuario_envio=usuario_obj,
                arquivo_colocado_por=rotulo,
                boleto_path=destino_boleto,
                boleto_nome_original=boleto_nome_original,
                destinatarios_adicionais=adicionais,
                forma_pagamento=forma_pagamento,
                parcelamento=parcelamento,
                numero_proposta=numero_proposta,
                item_segurado=item_segurado,
                seguradora=seguradora,
                produto=produto,
                layout_apolice=layout_apolice,
                capas_iniciais_ids=ids_iniciais,
                capas_finais_ids=ids_finais,
            )
            return int(envio_thread.id), getattr(envio_thread, "_erro_etapa", None)
        finally:
            db_thread.close()

    try:
        envio_id, erro_etapa = await run_in_threadpool(_processar_em_thread)
    except PdfRequerSenhaError as e:
        destino_up.unlink(missing_ok=True)
        if destino_boleto:
            destino_boleto.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    except PdfSenhaInvalidaError as e:
        destino_up.unlink(missing_ok=True)
        if destino_boleto:
            destino_boleto.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    except ValueError as e:
        destino_up.unlink(missing_ok=True)
        if destino_boleto:
            destino_boleto.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    except Exception:
        # Falhas inesperadas podem ocorrer antes de existir um backup. Mantém
        # o upload no disco para investigação/recuperação operacional.
        log.exception("Falha inesperada ao processar envio manual")
        raise

    envio = (
        db.query(models.Envio)
        .options(joinedload(models.Envio.cliente))
        .filter(models.Envio.id == envio_id)
        .first()
    )
    if not envio:
        raise HTTPException(500, "Envio processado mas não encontrado no histórico")
    if envio.cliente:
        cliente_crypto.decrypt_cliente_fields(envio.cliente)
    if envio.status != "enviado":
        raise _falha_envio_http(envio, erro_etapa)

    proc = settings.data_path(settings.processed_folder)
    proc.mkdir(parents=True, exist_ok=True)
    for origem in (destino_up, destino_boleto):
        if origem and origem.exists():
            try:
                origem.replace(proc / origem.name)
            except Exception as exc:
                # O backup já foi confirmado; ainda assim, não apaga o upload
                # se a organização na pasta de processados falhar.
                log.warning("Não foi possível mover upload processado %s: %s", origem, exc)
    return _envio_out(envio)


@router.post("/manual", response_model=schemas.EnvioOut, status_code=201)
async def envio_manual(
    arquivo: UploadFile = File(..., description="PDF da apólice"),
    boleto: UploadFile | None = File(None, description="PDF de boleto opcional"),
    cliente_id: int | None = Form(None),
    cliente_novo: str | None = Form(None),
    numero_apolice: str | None = Form(None),
    assunto: str | None = Form(None),
    extrair_dados: bool = Form(True),
    tipo_codigo: str | None = Form(None),
    auto_id: int | None = Form(None),
    corpo_email_id: int | None = Form(None),
    assinatura_id: int | None = Form(None),
    pdf_senha: str | None = Form(None),
    destinatarios_adicionais: str | None = Form(None),
    forma_pagamento: str | None = Form(None, max_length=40),
    parcelamento: int | None = Form(None, ge=1, le=12),
    numero_proposta: str | None = Form(None, max_length=100),
    item_segurado: str | None = Form(None, max_length=150),
    seguradora: str | None = Form(None),
    produto: str | None = Form(None),
    layout_apolice: str | None = Form(None),
    capas_iniciais_ids: str | None = Form(None),
    capas_finais_ids: str | None = Form(None),
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(require_user),
):
    return await _processar_request_manual(
        db=db,
        usuario=usuario,
        arquivo=arquivo,
        boleto=boleto,
        cliente_id=cliente_id,
        cliente_novo=cliente_novo,
        numero_apolice=numero_apolice,
        assunto=assunto,
        mensagem=None,
        extrair_dados=extrair_dados,
        tipo_codigo=tipo_codigo,
        auto_id=auto_id,
        corpo_email_id=corpo_email_id,
        assinatura_id=assinatura_id,
        pdf_senha=pdf_senha,
        destinatarios_adicionais=destinatarios_adicionais,
        forma_pagamento=forma_pagamento,
        parcelamento=parcelamento,
        numero_proposta=numero_proposta,
        item_segurado=item_segurado,
        seguradora=seguradora,
        produto=produto,
        layout_apolice=layout_apolice,
        capas_iniciais_ids=capas_iniciais_ids,
        capas_finais_ids=capas_finais_ids,
    )


@router.post("/avulso", response_model=schemas.EnvioOut, status_code=201)
async def envio_avulso_legado(
    arquivo: UploadFile = File(...),
    cliente_id: int | None = Form(None),
    cliente_novo: str | None = Form(None),
    numero_apolice: str | None = Form(None),
    assunto: str | None = Form(None),
    mensagem: str | None = Form(None),
    extrair_dados: bool = Form(False),
    tipo_codigo: str | None = Form(None),
    auto_id: int | None = Form(None),
    corpo_email_id: int | None = Form(None),
    assinatura_id: int | None = Form(None),
    destinatarios_adicionais: str | None = Form(None),
    forma_pagamento: str | None = Form(None, max_length=40),
    parcelamento: int | None = Form(None, ge=1, le=12),
    numero_proposta: str | None = Form(None, max_length=100),
    item_segurado: str | None = Form(None, max_length=150),
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(require_user),
):
    """Alias legado da rota /manual — mantido para compat com clientes antigos."""
    return await _processar_request_manual(
        db=db,
        usuario=usuario,
        arquivo=arquivo,
        boleto=None,
        cliente_id=cliente_id,
        cliente_novo=cliente_novo,
        numero_apolice=numero_apolice,
        assunto=assunto,
        mensagem=mensagem,
        extrair_dados=extrair_dados,
        tipo_codigo=tipo_codigo,
        auto_id=auto_id,
        corpo_email_id=corpo_email_id,
        assinatura_id=assinatura_id,
        destinatarios_adicionais=destinatarios_adicionais,
        forma_pagamento=forma_pagamento,
        parcelamento=parcelamento,
        numero_proposta=numero_proposta,
        item_segurado=item_segurado,
    )


@router.post("/demonstrar", response_model=schemas.EnvioDemoOut)
async def demonstrar_email(
    arquivo: UploadFile | None = File(None),
    cliente_id: int | None = Form(None),
    cliente_novo: str | None = Form(None),
    numero_apolice: str | None = Form(None),
    extrair_dados: bool = Form(True),
    tipo_codigo: str | None = Form(None),
    auto_id: int | None = Form(None),
    corpo_email_id: int | None = Form(None),
    assinatura_id: int | None = Form(None),
    pdf_senha: str | None = Form(None),
    destinatarios_adicionais: str | None = Form(None),
    forma_pagamento: str | None = Form(None, max_length=40),
    parcelamento: int | None = Form(None, ge=1, le=12),
    numero_proposta: str | None = Form(None, max_length=100),
    item_segurado: str | None = Form(None, max_length=150),
    seguradora: str | None = Form(None),
    produto: str | None = Form(None),
    layout_apolice: str | None = Form(None),
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    """Não envia: só renderiza assunto/corpo do e-mail com os dados informados."""
    try:
        adicionais = destinatarios_service.parse_json(destinatarios_adicionais)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    pdf_senha = pdf_service.normalizar_senha_pdf(pdf_senha)
    cliente = _resolver_cliente(db, cliente_id, cliente_novo, persistir=False)

    if arquivo and arquivo.filename and extrair_dados:
        up = settings.data_path(settings.upload_folder)
        up.mkdir(parents=True, exist_ok=True)
        tmp = up / f"demo_{uuid.uuid4().hex}.pdf"
        try:
            await save_upload(arquivo, tmp, kind="pdf", allowed_suffixes={".pdf"})
            try:
                d = await run_in_threadpool(
                    partial(
                        pdf_service.extrair_dados,
                        tmp,
                        usar_ocr=settings.ocr_enabled,
                        senha=pdf_senha,
                    )
                )
                if not numero_apolice and d.numero_apolice:
                    numero_apolice = d.numero_apolice
                seguradora = d.seguradora or seguradora
                produto = d.produto or produto
                layout_apolice = d.layout or layout_apolice
                if not item_segurado:
                    item_segurado = d.produto
            except Exception as exc:
                log.warning("Falha ao extrair PDF na demonstração: %s", exc)
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass

    auto: models.Auto | None = None
    if auto_id:
        auto = db.get(models.Auto, auto_id)
        if auto and auto.cliente_id != cliente.id:
            auto = None

    out = envio_service.renderizar_demonstracao(
        db,
        cliente=cliente,
        auto=auto,
        numero_apolice=numero_apolice,
        tipo_envio="MANUAL",
        tipo_codigo=tipo_codigo,
        assinatura_id=assinatura_id,
        corpo_email_id=corpo_email_id,
        destinatarios_adicionais=adicionais,
        forma_pagamento=forma_pagamento,
        parcelamento=parcelamento,
        numero_proposta=numero_proposta,
        item_segurado=item_segurado,
        seguradora=seguradora,
        produto=produto,
        layout_apolice=layout_apolice,
    )
    return out
