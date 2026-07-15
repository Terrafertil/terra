"""Baseline do schema consolidado existente.

Revision ID: 20260715_0001
Revises: None
"""

revision = "20260715_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # O init_db consolida bancos legados antes de registrar esta baseline.
    pass


def downgrade() -> None:
    # Baseline nÃ£o remove tabelas de produÃ§Ã£o.
    pass
