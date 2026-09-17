"""Envio de e-mail transacional via SMTP (síncrono).

Produção com Brevo: configure USE_BREVO=true, o login SMTP e uma chave SMTP.
O sistema envia cada apólice pelo relay transacional da Brevo, com PDF em anexo.

Suporta:
- Corpo HTML customizado por TipoEnvio (com placeholders {{ var }})
- Assinatura como imagem inline no rodapé do HTML (CID)
- Template padrão como fallback
"""
from __future__ import annotations

import logging
import smtplib
import ssl
import mimetypes
import re
import uuid
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Iterable, Mapping, Any

from jinja2.sandbox import SandboxedEnvironment

from ..config import settings
from . import destinatarios_service

log = logging.getLogger(__name__)
_JINJA_ENV = SandboxedEnvironment(autoescape=True)


def _adicionar_assinatura_ao_rodape(html: str, assinatura_cid: str | None) -> str:
    """Inclui a imagem inline depois de todo o conteudo do corpo.

    Corpos de e-mail personalizados normalmente contem apenas o texto que o
    usuario editou. A assinatura, por outro lado, e uma configuracao do envio e
    nao deve depender de o modelo conhecer ``assinatura_cid``. Se um modelo
    legado ja posiciona o mesmo CID, preservamos essa posicao sem duplicar a
    imagem.
    """
    if not assinatura_cid or f"cid:{assinatura_cid}".casefold() in html.casefold():
        return html

    assinatura_html = (
        '<div class="assinatura-email" style="margin-top:16px;">'
        f'<img src="cid:{assinatura_cid}" alt="Assinatura" '
        'style="display:block;max-width:380px;height:auto;border:0;" />'
        "</div>"
    )

    # Mantem um documento HTML completo valido; corpos que sao apenas um
    # fragmento recebem a assinatura ao final, igualmente abaixo do texto.
    fechamento_body = list(re.finditer(r"</body\s*>", html, flags=re.IGNORECASE))
    if fechamento_body:
        posicao = fechamento_body[-1].start()
        return f"{html[:posicao]}{assinatura_html}\n{html[posicao:]}"

    fechamento_html = list(re.finditer(r"</html\s*>", html, flags=re.IGNORECASE))
    if fechamento_html:
        posicao = fechamento_html[-1].start()
        return f"{html[:posicao]}{assinatura_html}\n{html[posicao:]}"

    separador = "\n" if html and not html.endswith("\n") else ""
    return f"{html}{separador}{assinatura_html}"


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
    # Proposta / pagamento
    {"chave": "forma_pagamento", "label": "Forma de pagamento", "grupo": "Proposta"},
    {"chave": "parcelamento", "label": "Parcelamento (1 a 12 vezes)", "grupo": "Proposta"},
    {"chave": "numero_proposta", "label": "Numero da proposta", "grupo": "Proposta"},
    {"chave": "item_segurado", "label": "Item segurado", "grupo": "Proposta"},
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

    html = _JINJA_ENV.from_string(tpl_str).render(**ctx)
    return _adicionar_assinatura_ao_rodape(html, assinatura_cid)


_ASSUNTO_VARIAVEL = re.compile(
    r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}"
)


def formatar_assunto(
    numero_apolice: str | None,
    custom: str | None = None,
    contexto: Mapping[str, Any] | None = None,
) -> str:
    """Renderiza variaveis simples sem expor o acesso a atributos do format()."""
    tpl = custom or settings.email_subject_default or "Envio de Apolice"
    ctx: dict[str, Any] = dict(contexto or {})
    ctx.setdefault("numero_apolice", numero_apolice or "")

    def substituir(match: re.Match[str]) -> str:
        chave = match.group(1) or match.group(2)
        if chave not in ctx:
            return match.group(0)
        valor = ctx.get(chave)
        return "" if valor is None else str(valor)

    return _ASSUNTO_VARIAVEL.sub(substituir, tpl)


def enviar_email(
    *,
    destinatario: str | Iterable[str],
    assunto: str,
    corpo_html: str,
    anexos: Iterable[str | Path] = (),
    nome_anexo_pdf: str | None = None,
    nomes_anexos: Iterable[str | None] = (),
    assinatura_path: str | Path | None = None,
    assinatura_cid: str | None = None,
    tracking_id: str | None = None,
) -> str:
    destinatarios = destinatarios_service.combinar(
        [destinatario] if isinstance(destinatario, str) else destinatario
    )
    if not destinatarios:
        raise ValueError("Informe ao menos um destinatario")
    faltantes = []
    if not (settings.smtp_host or "").strip():
        faltantes.append("SMTP_HOST")
    if not (settings.smtp_from_email or "").strip():
        faltantes.append("BREVO_SENDER_EMAIL/SMTP_FROM_EMAIL")
    if settings.use_brevo and not (settings.smtp_user or "").strip():
        faltantes.append("BREVO_SMTP_LOGIN/SMTP_USER")
    if settings.use_brevo and not (settings.smtp_password or "").strip():
        faltantes.append("BREVO_SMTP_KEY/SMTP_PASSWORD")
    if faltantes:
        raise RuntimeError(
            "Brevo SMTP não configurada; preencha no .env: " + ", ".join(faltantes)
        )

    msg = EmailMessage()
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto
    message_id = make_msgid(domain="terrafertil.local")
    msg["Message-ID"] = message_id
    if tracking_id:
        msg["X-Mailin-custom"] = tracking_id
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
                disposition="inline",
                filename=ap.name,
            )

    # PDFs / anexos
    nomes = list(nomes_anexos)
    for index, caminho in enumerate(anexos):
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
            filename=(
                nomes[index]
                if index < len(nomes) and nomes[index]
                else nome_anexo_pdf if index == 0 and nome_anexo_pdf else p.name
            ),
        )

    if settings.use_brevo:
        tamanho = len(msg.as_bytes())
        limite = max(1, settings.brevo_max_message_mb) * 1024 * 1024
        if tamanho > limite:
            raise ValueError(
                "E-mail com anexos excede o limite transacional da Brevo: "
                f"{tamanho / 1024 / 1024:.1f} MB (máximo {settings.brevo_max_message_mb} MB)."
            )

    contexto = ssl.create_default_context()
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=30,
            context=contexto,
        ) as smtp:
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg, to_addrs=destinatarios)
    elif settings.smtp_use_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=contexto)
            smtp.ehlo()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg, to_addrs=destinatarios)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg, to_addrs=destinatarios)

    log.info(
        "E-mail aceite pelo SMTP %s → %s (message_id=%s, tracking=%s)",
        settings.smtp_host,
        ", ".join(destinatarios),
        message_id,
        tracking_id or "-",
    )
    return message_id


def gerar_cid() -> str:
    return f"assinatura-{uuid.uuid4().hex}@envio"
