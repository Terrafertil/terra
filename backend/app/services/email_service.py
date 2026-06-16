"""Envio de e-mail via SMTP (síncrono).

Produção com Brevo: configure USE_BREVO=true e o relay SMTP (smtp-relay.brevo.com),
SMTP_USER + SMTP_PASSWORD (chave SMTP do painel). A API de *campanhas* do SDK Brevo
não substitui este fluxo — ela não envia apólice em anexo para um destinatário por vez.

Suporta:
- Corpo HTML customizado por TipoEnvio (com placeholders {{ var }})
- Assinatura como imagem inline no rodapé do HTML (CID)
- Template padrão como fallback
"""
from __future__ import annotations

import smtplib
import ssl
import mimetypes
import uuid
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, Mapping, Any

from jinja2 import Template

from ..config import settings


TEMPLATE_PADRAO = """
<html>
  <body style="font-family: Arial, sans-serif; color:#333;">
    <p>Prezado(a) <strong>{{ nome }}</strong>,</p>
    <p>Segue em anexo sua apólice{% if numero_apolice %} de número
       <strong>{{ numero_apolice }}</strong>{% endif %}.</p>
    <p>Em caso de dúvidas, responda este e-mail.</p>
    <p>Atenciosamente,<br/>{{ from_name }}</p>
    {% if assinatura_cid %}
    <p><img src="cid:{{ assinatura_cid }}" alt="Assinatura" style="max-width:380px"/></p>
    {% endif %}
  </body>
</html>
"""


PLACEHOLDERS_DISPONIVEIS = [
    # Cliente
    {"chave": "nome", "label": "Nome do cliente", "grupo": "Cliente"},
    {"chave": "email", "label": "E-mail do cliente", "grupo": "Cliente"},
    {"chave": "cpf", "label": "CPF", "grupo": "Cliente"},
    {"chave": "cnpj", "label": "CNPJ", "grupo": "Cliente"},
    {"chave": "telefone", "label": "Telefone", "grupo": "Cliente"},
    # Apólice / envio
    {"chave": "numero_apolice", "label": "Nº da apólice", "grupo": "Apólice"},
    {"chave": "tipo_envio", "label": "Tipo de envio", "grupo": "Apólice"},
    {"chave": "tipo_codigo", "label": "Código do tipo (auto, moto…)", "grupo": "Apólice"},
    {"chave": "data_envio", "label": "Data do envio", "grupo": "Apólice"},
    {"chave": "seguradora", "label": "Seguradora", "grupo": "Apólice"},
    {"chave": "produto", "label": "Produto (auto, moto, casco…)", "grupo": "Apólice"},
    {"chave": "layout_apolice", "label": "Layout detectado no PDF", "grupo": "Apólice"},
    # Auto
    {"chave": "placa", "label": "Placa do veículo", "grupo": "Auto"},
    {"chave": "marca", "label": "Marca", "grupo": "Auto"},
    {"chave": "modelo", "label": "Modelo", "grupo": "Auto"},
    {"chave": "ano", "label": "Ano", "grupo": "Auto"},
    # Outros
    {"chave": "from_name", "label": "Remetente (nome)", "grupo": "Outros"},
]

# Blocos HTML sugeridos por modelo de apólice (pasta Modelos/)
ATALHOS_MODELOS = [
    {
        "id": "tokio_auto",
        "label": "Tokio Marine — Auto",
        "layout": "tokio_marine",
        "produto": "auto",
        "tipo_codigo_sugerido": "auto",
        "full_automatico": True,
        "descricao": "CPF e nº da apólice extraídos automaticamente no modo FULL.",
        "html": (
            "<p>Prezado(a) <strong>{{ nome }}</strong>,</p>\n"
            "<p>Segue em anexo sua apólice Tokio Marine <strong>Auto</strong>"
            "{% if numero_apolice %} nº <strong>{{ numero_apolice }}</strong>{% endif %}.</p>\n"
            "<p>Em caso de dúvidas, responda este e-mail.</p>\n"
            "<p>Atenciosamente,<br/>{{ from_name }}</p>"
        ),
    },
    {
        "id": "tokio_moto",
        "label": "Tokio Marine — Moto",
        "layout": "tokio_marine",
        "produto": "moto",
        "tipo_codigo_sugerido": "moto",
        "full_automatico": True,
        "descricao": "Mesmo layout Tokio; pasta FULL sugerida: moto/.",
        "html": (
            "<p>Prezado(a) <strong>{{ nome }}</strong>,</p>\n"
            "<p>Segue em anexo sua apólice Tokio Marine <strong>Moto</strong>"
            "{% if numero_apolice %} nº <strong>{{ numero_apolice }}</strong>{% endif %}.</p>\n"
            "<p>Atenciosamente,<br/>{{ from_name }}</p>"
        ),
    },
    {
        "id": "yelum_casco",
        "label": "Yelum — Auto Casco (Ramo 31)",
        "layout": "yelum_casco",
        "produto": "auto_casco",
        "tipo_codigo_sugerido": "auto_casco",
        "full_automatico": True,
        "descricao": "Apólice no formato 31.09.2026.0907318; CPF na ficha do segurado.",
        "html": (
            "<p>Prezado(a) <strong>{{ nome }}</strong>,</p>\n"
            "<p>Segue sua apólice Yelum (Automóvel Casco)"
            "{% if numero_apolice %} — <strong>{{ numero_apolice }}</strong>{% endif %}.</p>\n"
            "{% if placa %}<p>Veículo: placa <strong>{{ placa }}</strong>"
            "{% if marca %} — {{ marca }} {{ modelo }}{% endif %}.</p>{% endif %}\n"
            "<p>Atenciosamente,<br/>{{ from_name }}</p>"
        ),
    },
    {
        "id": "porto_criptografado",
        "label": "Porto / SulAmérica — PDF protegido",
        "layout": "porto_sulamerica_criptografado",
        "produto": None,
        "tipo_codigo_sugerido": None,
        "full_automatico": False,
        "descricao": "Informe a senha do PDF no envio manual ou use ficheiro .pdf.senha no FULL.",
        "html": (
            "<p>Prezado(a) <strong>{{ nome }}</strong>,</p>\n"
            "<p>Segue em anexo sua apólice de seguro"
            "{% if numero_apolice %} nº <strong>{{ numero_apolice }}</strong>{% endif %}.</p>\n"
            "<p>Atenciosamente,<br/>{{ from_name }}</p>"
        ),
    },
    {
        "id": "sem_texto",
        "label": "PDF só imagem / impressão",
        "layout": "sem_texto",
        "produto": None,
        "tipo_codigo_sugerido": None,
        "full_automatico": False,
        "descricao": "PDF sem texto selecionável; cadastre cliente e apólice manualmente.",
        "html": (
            "<p>Prezado(a) <strong>{{ nome }}</strong>,</p>\n"
            "<p>Segue em anexo o documento da sua apólice"
            "{% if numero_apolice %} (<strong>{{ numero_apolice }}</strong>){% endif %}.</p>\n"
            "<p>Atenciosamente,<br/>{{ from_name }}</p>"
        ),
    },
    {
        "id": "generico",
        "label": "Genérico — qualquer seguradora",
        "layout": None,
        "produto": None,
        "tipo_codigo_sugerido": None,
        "full_automatico": None,
        "descricao": "Modelo padrão com variáveis do cliente e da apólice.",
        "html": TEMPLATE_PADRAO.strip(),
    },
]


def renderizar_template(
    *,
    contexto: Mapping[str, Any] | None = None,
    cliente_nome: str | None = None,
    numero_apolice: str | None = None,
    mensagem: str | None = None,
    template_html: str | None = None,
    template_path: str | None = None,
    assinatura_cid: str | None = None,
) -> str:
    """Renderiza o corpo HTML do e-mail.

    - `contexto`: dicionário com todas as variáveis (nome, cpf, placa, ...).
    - Se `template_html` for fornecido, usa-o como Jinja. Caso contrário,
      tenta `template_path`. Caso contrário, usa o TEMPLATE_PADRAO.
    """
    tpl_str = template_html if template_html is not None else None
    if tpl_str is None and template_path:
        p = Path(template_path)
        if p.exists():
            tpl_str = p.read_text(encoding="utf-8")
    if tpl_str is None:
        tpl_str = TEMPLATE_PADRAO

    ctx: dict[str, Any] = {}
    if contexto:
        ctx.update(dict(contexto))

    # Compatibilidade legado: cliente_nome/numero_apolice
    if cliente_nome and "nome" not in ctx:
        ctx["nome"] = cliente_nome
    if numero_apolice is not None and "numero_apolice" not in ctx:
        ctx["numero_apolice"] = numero_apolice

    ctx.setdefault("from_name", settings.smtp_from_name)
    ctx.setdefault("mensagem", mensagem)
    ctx["assinatura_cid"] = assinatura_cid

    # Garantir todas as chaves de PLACEHOLDERS_DISPONIVEIS existirem como ""
    for ph in PLACEHOLDERS_DISPONIVEIS:
        ctx.setdefault(ph["chave"], "")

    return Template(tpl_str).render(**ctx)


def formatar_assunto(numero_apolice: str | None, custom: str | None = None) -> str:
    tpl = custom or settings.email_subject_default or "Envio de Apolice"
    try:
        return tpl.format(numero_apolice=numero_apolice or "")
    except Exception:
        return tpl


def enviar_email(
    *,
    destinatario: str,
    assunto: str,
    corpo_html: str,
    anexos: Iterable[str | Path] = (),
    nome_anexo_pdf: str | None = None,
    assinatura_path: str | Path | None = None,
    assinatura_cid: str | None = None,
) -> None:
    if not settings.smtp_host:
        raise RuntimeError("SMTP não configurado (.env SMTP_HOST vazio)")

    msg = EmailMessage()
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.set_content("Sua apólice segue em anexo. (e-mail em HTML)")
    msg.add_alternative(corpo_html, subtype="html")

    # Imagem da assinatura como inline (CID)
    if assinatura_path and assinatura_cid:
        ap = Path(assinatura_path)
        if ap.is_file():
            ctype, _ = mimetypes.guess_type(ap.name)
            if not ctype or not ctype.startswith("image/"):
                ctype = "image/png"
            maintype, subtype = ctype.split("/", 1)
            with ap.open("rb") as fh:
                img_bytes = fh.read()
            html_part = msg.get_payload()[1]
            html_part.add_related(
                img_bytes,
                maintype=maintype,
                subtype=subtype,
                cid=f"<{assinatura_cid}>",
                filename=ap.name,
            )

    # PDFs / anexos
    for caminho in anexos:
        p = Path(caminho)
        if not p.is_file():
            raise FileNotFoundError(f"Anexo PDF em falta ou inválido: {p}")
        with p.open("rb") as fh:
            dados = fh.read()
        if not dados:
            raise ValueError(f"Anexo PDF vazio: {p}")
        msg.add_attachment(
            dados,
            maintype="application",
            subtype="pdf",
            filename=nome_anexo_pdf or p.name,
        )

    contexto = ssl.create_default_context()
    if settings.smtp_use_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=contexto)
            smtp.ehlo()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


def gerar_cid() -> str:
    return f"assinatura-{uuid.uuid4().hex}@envio"
