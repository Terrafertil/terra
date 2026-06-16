"""LGPD: exclusão de dados do titular e deteção de duplicados."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from .. import models
from .cliente_crypto import decrypt_cliente_fields


def _so_digitos(val: str | None) -> str:
    if not val:
        return ""
    return re.sub(r"\D", "", val)


def listar_duplicados(db: Session) -> list[dict]:
    """Grupos de clientes com CPF, CNPJ ou e-mail repetido."""
    clientes = db.query(models.Cliente).order_by(models.Cliente.nome).all()
    por_cpf: dict[str, list[models.Cliente]] = defaultdict(list)
    por_cnpj: dict[str, list[models.Cliente]] = defaultdict(list)
    por_email: dict[str, list[models.Cliente]] = defaultdict(list)

    for c in clientes:
        cpf = _so_digitos(c.cpf)
        if len(cpf) >= 11:
            por_cpf[cpf].append(c)
        cnpj = _so_digitos(c.cnpj)
        if len(cnpj) >= 14:
            por_cnpj[cnpj].append(c)
        email = (c.email or "").strip().lower()
        if email:
            por_email[email].append(c)

    grupos: list[dict] = []
    vistos: set[frozenset[int]] = set()

    def _add(tipo: str, chave: str, lista: list[models.Cliente]) -> None:
        if len(lista) < 2:
            return
        ids = frozenset(c.id for c in lista)
        if ids in vistos:
            return
        vistos.add(ids)
        grupos.append(
            {
                "tipo": tipo,
                "chave": chave,
                "clientes": [
                    {
                        "id": c.id,
                        "nome": c.nome,
                        "email": c.email,
                        "cpf": c.cpf,
                        "cnpj": c.cnpj,
                        "ativo": c.ativo,
                    }
                    for c in sorted(lista, key=lambda x: x.nome)
                ],
            }
        )

    for k, lst in por_cpf.items():
        _add("cpf", k, lst)
    for k, lst in por_cnpj.items():
        _add("cnpj", k, lst)
    for k, lst in por_email.items():
        _add("email", k, lst)

    return sorted(grupos, key=lambda g: (g["tipo"], g["chave"]))


def _apagar_ficheiro(caminho: str | None) -> bool:
    if not caminho:
        return False
    p = Path(caminho)
    if p.is_file():
        try:
            p.unlink()
            return True
        except OSError:
            return False
    return False


def excluir_cliente_lgpd(
    db: Session,
    cliente_id: int,
    *,
    confirmar_nome: str,
    remover_backups: bool = True,
) -> dict:
    """Remove cliente, envios (cascade) e ficheiros de backup associados."""
    c = db.get(models.Cliente, cliente_id)
    if not c:
        raise ValueError("Cliente não encontrado")
    decrypt_cliente_fields(c)
    if confirmar_nome.strip().lower() != (c.nome or "").strip().lower():
        raise ValueError("Nome de confirmação não coincide com o cadastro")

    envios = db.query(models.Envio).filter(models.Envio.cliente_id == cliente_id).all()
    ficheiros_removidos = 0
    if remover_backups:
        for e in envios:
            if _apagar_ficheiro(e.caminho_backup):
                ficheiros_removidos += 1

    nome = c.nome
    n_envios = len(envios)
    db.delete(c)
    db.commit()

    return {
        "cliente_nome": nome,
        "envios_removidos": n_envios,
        "ficheiros_backup_removidos": ficheiros_removidos,
    }
