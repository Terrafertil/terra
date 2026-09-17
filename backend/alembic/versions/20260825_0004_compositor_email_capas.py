"""Destinatarios, variaveis do envio e biblioteca de capas.

Revision ID: 20260825_0004
Revises: 20260811_0003
"""
from alembic import op
import sqlalchemy as sa


revision = "20260825_0004"
down_revision = "20260811_0003"
branch_labels = None
depends_on = None


def _tabelas() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _colunas(tabela: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabela)}


def _adicionar_se_faltar(tabela: str, coluna: sa.Column) -> None:
    if coluna.name not in _colunas(tabela):
        op.add_column(tabela, coluna)


def upgrade() -> None:
    _adicionar_se_faltar(
        "clientes", sa.Column("destinatarios_adicionais_json", sa.Text(), nullable=True)
    )
    _adicionar_se_faltar(
        "tipos_envio", sa.Column("capas_iniciais_json", sa.Text(), nullable=True)
    )
    _adicionar_se_faltar(
        "tipos_envio", sa.Column("capas_finais_json", sa.Text(), nullable=True)
    )

    for coluna in (
        sa.Column("forma_pagamento", sa.String(length=40), nullable=True),
        sa.Column("parcelamento", sa.Integer(), nullable=True),
        sa.Column("numero_proposta", sa.String(length=100), nullable=True),
        sa.Column("item_segurado", sa.String(length=150), nullable=True),
        sa.Column("capas_iniciais_json", sa.Text(), nullable=True),
        sa.Column("capas_finais_json", sa.Text(), nullable=True),
        sa.Column(
            "destinatarios_manuais_qtd",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    ):
        _adicionar_se_faltar("envios", coluna)

    indices_envios = {
        indice["name"] for indice in sa.inspect(op.get_bind()).get_indexes("envios")
    }
    if "ix_envios_numero_proposta" not in indices_envios:
        op.create_index(
            "ix_envios_numero_proposta",
            "envios",
            ["numero_proposta"],
            unique=False,
        )

    if "capas_modelos" not in _tabelas():
        op.create_table(
            "capas_modelos",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("nome", sa.String(length=120), nullable=False, unique=True),
            sa.Column("descricao", sa.String(length=255), nullable=True),
            sa.Column("arquivo", sa.String(length=255), nullable=False, unique=True),
            sa.Column("nome_original", sa.String(length=255), nullable=True),
            sa.Column("tamanho_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("paginas", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sha256", sa.String(length=64), nullable=True),
            sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column(
                "created_at", sa.DateTime(), nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.Column(
                "updated_at", sa.DateTime(), nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
        )


def downgrade() -> None:
    if "capas_modelos" in _tabelas():
        op.drop_table("capas_modelos")
    indices_envios = {
        indice["name"] for indice in sa.inspect(op.get_bind()).get_indexes("envios")
    }
    if "ix_envios_numero_proposta" in indices_envios:
        op.drop_index("ix_envios_numero_proposta", table_name="envios")
    for nome in (
        "capas_finais_json",
        "capas_iniciais_json",
        "destinatarios_manuais_qtd",
        "item_segurado",
        "numero_proposta",
        "parcelamento",
        "forma_pagamento",
    ):
        if nome in _colunas("envios"):
            op.drop_column("envios", nome)
    for nome in ("capas_finais_json", "capas_iniciais_json"):
        if nome in _colunas("tipos_envio"):
            op.drop_column("tipos_envio", nome)
    if "destinatarios_adicionais_json" in _colunas("clientes"):
        op.drop_column("clientes", "destinatarios_adicionais_json")
