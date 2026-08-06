"""Envio MANUAL (upload manual + e-mail imediato), demonstração e histórico."""
from __future__ import annotations

import csv
import io
import json
import uuid
from functools import partial
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..database import get_db
from .. import models, schemas
from ..auth import require_user
from ..services import envio_service, ocr_service, pdf_service, cliente_crypto, file_provenance
from ..services.pdf_service import PdfRequerSenhaError, PdfSenhaInvalidaError
from ..services.upload_service import save_upload


router = APIRouter(prefix="/api/envios", tags=["envios"])


def _envio_out(envio: models.Envio) -> schemas.EnvioOut:
    out = schemas.EnvioOut.model_validate(envio)
    out.pode_reenviar = bool(envio.caminho_backup)
    if envio.cliente:
        out.cliente_nome = envio.cliente.nome
        out.cliente_email = envio.cliente.email
    return out


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
            "cliente_id",
            "cliente_nome",
            "cliente_email",
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
                e.cliente_id,
                e.cliente.nome if e.cliente else "",
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
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    """Reenvia em lote envios com status erro (últimos N dias)."""
    resultado = envio_service.reenviar_envios_com_erro(db, dias=dias)
    return schemas.EnvioReenvioLoteOut(**resultado)


@router.post("/{eid}/reenviar", response_model=schemas.EnvioOut)
def reenviar_um(
    eid: int,
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    try:
        envio = envio_service.reenviar_envio(db, eid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.refresh(envio)
    envio = (
        db.query(models.Envio)
        .options(joinedload(models.Envio.cliente))
        .filter(models.Envio.id == eid)
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
    db: Session, cliente_id: int | None, cliente_novo_json: str | None
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
        cli = models.Cliente(**dados.model_dump())
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
):
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
        except Exception:
            pass

    auto: models.Auto | None = None
    if auto_id:
        auto = db.get(models.Auto, auto_id)
        if auto and auto.cliente_id != cliente.id:
            auto = None

    try:
        rotulo = file_provenance.rotulo_usuario(usuario.nome, usuario.username)
        envio = await run_in_threadpool(
            partial(
                envio_service.processar_envio,
                db,
                cliente=cliente,
                caminho_pdf=destino_up,
                tipo_envio="MANUAL",
                tipo_codigo=tipo_codigo,
                auto=auto,
                numero_apolice=numero_apolice,
                assunto_customizado=assunto,
                corpo_html_customizado=mensagem,
                corpo_email_id=corpo_email_id,
                assinatura_id=assinatura_id,
                nome_arquivo_original=nome_original,
                pdf_senha=pdf_senha,
                usuario_envio=usuario if usuario.id else None,
                arquivo_colocado_por=rotulo,
                boleto_path=destino_boleto,
                boleto_nome_original=boleto_nome_original,
            )
        )
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
        destino_up.unlink(missing_ok=True)
        if destino_boleto:
            destino_boleto.unlink(missing_ok=True)
        raise

    proc = settings.data_path(settings.processed_folder)
    proc.mkdir(parents=True, exist_ok=True)
    for origem in (destino_up, destino_boleto):
        if origem and origem.exists():
            try:
                origem.replace(proc / origem.name)
            except Exception:
                origem.unlink(missing_ok=True)

    return envio


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
    db: Session = Depends(get_db),
    _=Depends(require_user),
):
    """Não envia: só renderiza assunto/corpo do e-mail com os dados informados."""
    cliente = _resolver_cliente(db, cliente_id, cliente_novo)

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
            except Exception:
                pass
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
    )
    return out
