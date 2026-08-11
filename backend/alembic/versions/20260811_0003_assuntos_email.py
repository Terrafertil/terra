"""Cria assuntos salvos e vincula cada assunto ao tipo de envio.

Revision ID: 20260811_0003
Revises: 20260811_0002
"""
from alembic import op
import sqlalchemy as sa


revision = "20260811_0003"
down_revision = "20260811_0002"
branch_labels = None
depends_on = None


def _tabelas() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _colunas(tabela: str) -> set[str]:
    return {
        coluna["name"]
        for coluna in sa.inspect(op.get_bind()).get_columns(tabela)
    }


def _nome_disponivel(bind, nome_base: str, texto: str) -> tuple[str, int | None]:
    nome_base = nome_base[:120]
    nome = nome_base
    sufixo = 2
    while True:
        existente = bind.execute(
            sa.text("SELECT id, assunto FROM assuntos_email WHERE nome = :nome"),
            {"nome": nome},
        ).mappings().first()
        if not existente:
            return nome, None
        if existente["assunto"] == texto:
            return nome, int(existente["id"])
        marcador = f" ({sufixo})"
        nome = f"{nome_base[:120 - len(marcador)]}{marcador}"
        sufixo += 1


def _backfill_legado() -> None:
    bind = op.get_bind()
    linhas = bind.execute(
        sa.text(
            "SELECT t.id AS tipo_id, c.id AS corpo_id, c.nome AS corpo_nome, "
            "c.assunto AS assunto, c.ativo AS ativo "
            "FROM tipos_envio t JOIN corpos_email c ON c.id = t.corpo_email_id "
            "WHERE t.assunto_email_id IS NULL AND c.assunto IS NOT NULL "
            "AND TRIM(c.assunto) <> '' ORDER BY c.id, t.id"
        )
    ).mappings().all()
    por_corpo: dict[int, int] = {}
    for linha in linhas:
        corpo_id = int(linha["corpo_id"])
        assunto_id = por_corpo.get(corpo_id)
        if assunto_id is None:
            texto = str(linha["assunto"]).strip()
            nome, assunto_id = _nome_disponivel(
                bind, f"Assunto - {linha['corpo_nome']}", texto
            )
            if assunto_id is None:
                bind.execute(
                    sa.text(
                        "INSERT INTO assuntos_email "
                        "(nome, descricao, assunto, ativo, created_at, updated_at) "
                        "VALUES (:nome, :descricao, :assunto, :ativo, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "nome": nome,
                        "descricao": (
                            f"Importado do corpo de e-mail {linha['corpo_nome']}"[:255]
                        ),
                        "assunto": texto,
                        "ativo": bool(linha["ativo"]),
                    },
                )
                assunto_id = int(
                    bind.execute(
                        sa.text("SELECT id FROM assuntos_email WHERE nome = :nome"),
                        {"nome": nome},
                    ).scalar_one()
                )
            por_corpo[corpo_id] = assunto_id
        bind.execute(
            sa.text(
                "UPDATE tipos_envio SET assunto_email_id = :assunto_id "
                "WHERE id = :tipo_id AND assunto_email_id IS NULL"
            ),
            {"assunto_id": assunto_id, "tipo_id": int(linha["tipo_id"])},
        )


def upgrade() -> None:
    tabelas = _tabelas()
    if "assuntos_email" not in tabelas:
        op.create_table(
            "assuntos_email",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("nome", sa.String(length=120), nullable=False, unique=True),
            sa.Column("descricao", sa.String(length=255), nullable=True),
            sa.Column("assunto", sa.String(length=500), nullable=False),
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
    if "assunto_email_id" not in _colunas("tipos_envio"):
        # SQLite nao suporta adicionar uma FK por ALTER TABLE. O vinculo e
        # validado pelos endpoints e pelo ORM, como na migracao runtime usada
        # por instalacoes existentes.
        op.add_column(
            "tipos_envio",
            sa.Column(
                "assunto_email_id",
                sa.Integer(),
                nullable=True,
            ),
        )
    _backfill_legado()


def downgrade() -> None:
    if "assunto_email_id" in _colunas("tipos_envio"):
        op.drop_column("tipos_envio", "assunto_email_id")
    if "assuntos_email" in _tabelas():
        op.drop_table("assuntos_email")
