"""Validacao e composicao de destinatarios de e-mail."""
from __future__ import annotations

import json
from collections.abc import Iterable

from pydantic import EmailStr, TypeAdapter, ValidationError


MAX_DESTINATARIOS = 20
_EMAIL = TypeAdapter(EmailStr)


def validar_email(valor: str) -> str:
    texto = str(valor or "").strip()
    if "\r" in texto or "\n" in texto:
        raise ValueError("Endereco de e-mail invalido")
    try:
        return str(_EMAIL.validate_python(texto))
    except ValidationError as exc:
        raise ValueError(f"Endereco de e-mail invalido: {texto or '(vazio)'}") from exc


def combinar(*grupos: Iterable[str] | None, limite: int = MAX_DESTINATARIOS) -> list[str]:
    resultado: list[str] = []
    vistos: set[str] = set()
    for grupo in grupos:
        for item in grupo or ():
            email = validar_email(str(item))
            chave = email.casefold()
            if chave in vistos:
                continue
            vistos.add(chave)
            resultado.append(email)
            if len(resultado) > limite:
                raise ValueError(f"Limite de {limite} destinatarios por envio excedido")
    return resultado


def do_cliente(cliente, adicionais: Iterable[str] | None = None) -> list[str]:
    fixos = getattr(cliente, "destinatarios_adicionais", []) or []
    principal = [getattr(cliente, "email", "")]
    return combinar(principal, fixos, adicionais)


def parse_json(valor: str | None, *, campo: str = "destinatarios_adicionais") -> list[str]:
    if valor is None or not str(valor).strip():
        return []
    try:
        itens = json.loads(valor)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{campo} deve ser uma lista JSON valida") from exc
    if not isinstance(itens, list):
        raise ValueError(f"{campo} deve ser uma lista JSON")
    if not all(isinstance(item, str) for item in itens):
        raise ValueError(f"{campo} deve conter apenas enderecos de e-mail")
    return combinar(itens)


def snapshot(destinatarios: Iterable[str]) -> str:
    return ", ".join(combinar(destinatarios))


def do_snapshot(valor: str | None) -> list[str]:
    if not valor:
        return []
    # O formato persistido e separado por virgula. O fallback por ponto e
    # virgula mantem compatibilidade com eventuais importacoes manuais.
    partes = str(valor).replace(";", ",").split(",")
    try:
        return combinar(partes)
    except ValueError:
        return [parte.strip() for parte in partes if parte.strip()]


def chave_canonica(destinatarios: Iterable[str]) -> str:
    return ",".join(sorted(email.casefold() for email in combinar(destinatarios)))
