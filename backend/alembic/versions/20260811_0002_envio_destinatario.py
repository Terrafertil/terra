"""Adiciona snapshot do destinatário aos envios.

Revision ID: 20260811_0002
Revises: 20260715_0001
"""
from alembic import op
import sqlalchemy as sa


revision = "20260811_0002"
down_revision = "20260715_0001"
branch_labels = None
depends_on = None


def _tem_coluna(nome: str) -> bool:
    bind = op.get_bind()
    return nome in {coluna["name"] for coluna in sa.inspect(bind).get_columns("envios")}


def upgrade() -> None:
    # init_db também faz esta migração em bancos SQLite legados. A checagem
    # mantém a revisão idempotente quando os dois caminhos rodam na mesma subida.
    if not _tem_coluna("destinatario_email"):
        op.add_column(
            "envios",
            sa.Column("destinatario_email", sa.String(length=1024), nullable=True),
        )
    if not _tem_coluna("reenvio_de_id"):
        op.add_column(
            "envios",
            sa.Column("reenvio_de_id", sa.Integer(), nullable=True),
        )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_envios_reenvio_de_id "
        "ON envios (reenvio_de_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_envios_reenvio_de_id")
    if _tem_coluna("reenvio_de_id"):
        op.drop_column("envios", "reenvio_de_id")
    if _tem_coluna("destinatario_email"):
        op.drop_column("envios", "destinatario_email")
