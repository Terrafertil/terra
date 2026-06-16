"""Setup do SQLAlchemy + SQLite."""
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from typing import Generator

from .config import BASE_DIR, settings


class Base(DeclarativeBase):
    pass


def _database_url_resolvida() -> str:
    """SQLite relativo ao cwd passa a ser relativo à pasta backend/."""
    u = settings.database_url
    if not u.startswith("sqlite:///"):
        return u
    rest = u.replace("sqlite:///", "", 1)
    p = Path(rest)
    if p.is_absolute():
        return u
    abs_p = (BASE_DIR / p).resolve()
    return f"sqlite:///{abs_p.as_posix()}"


# SQLite precisa de connect_args={"check_same_thread": False}
engine_kwargs = {"future": True}
_db_url = _database_url_resolvida()
if _db_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(_db_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Cria tabelas se não existirem."""
    from . import models  # noqa: F401  (garante registro dos models)

    Base.metadata.create_all(bind=engine)
    _migrate_runtime_config_columns()
    _migrate_envios_columns()
    _migrate_avulso_para_manual()
    _migrate_clientes_crypto_columns()
    _migrate_usuarios_columns()
    _migrate_diretor_protegido()
    _seed_runtime_config()
    _import_crypto_events()
    _migrate_clientes_encryption_data()
    _seed_diretor_conta()


def _seed_diretor_conta() -> None:
    from .services.diretor_service import seed_diretor

    s = SessionLocal()
    try:
        seed_diretor(s)
    finally:
        s.close()


def _import_crypto_events() -> None:
    from .events import cliente_crypto_events  # noqa: F401


def _migrate_clientes_encryption_data() -> None:
    from .services import cliente_crypto
    from .services.data_crypto_service import encryption_enabled, validate_security_config

    if not encryption_enabled():
        return
    validate_security_config()
    s = SessionLocal()
    try:
        cliente_crypto.migrate_plaintext_clientes(s)
    finally:
        s.close()


def _migrate_clientes_crypto_columns() -> None:
    insp = inspect(engine)
    if "clientes" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("clientes")}
    with engine.begin() as conn:
        if "cpf_hash" not in cols:
            conn.execute(text("ALTER TABLE clientes ADD COLUMN cpf_hash VARCHAR(64)"))
        if "cnpj_hash" not in cols:
            conn.execute(text("ALTER TABLE clientes ADD COLUMN cnpj_hash VARCHAR(64)"))
        if "email_hash" not in cols:
            conn.execute(text("ALTER TABLE clientes ADD COLUMN email_hash VARCHAR(64)"))


def _migrate_runtime_config_columns() -> None:
    """SQLite: adiciona colunas novas a runtime_config sem Alembic."""
    insp = inspect(engine)
    if "runtime_config" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("runtime_config")}
    with engine.begin() as conn:
        if "email_frases_dashboard" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN email_frases_dashboard TEXT")
            )
        if "full_scan_exec_time" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN full_scan_exec_time VARCHAR(5)")
            )
        if "full_lote_size" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN full_lote_size INTEGER DEFAULT 5")
            )
        if "full_intervalo_lote_min" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN full_intervalo_lote_min INTEGER DEFAULT 5")
            )
        if "full_rescan_horas" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN full_rescan_horas INTEGER DEFAULT 1")
            )
        if "full_modo_ativo" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN full_modo_ativo BOOLEAN DEFAULT 1")
            )
        if "full_assinatura_id" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN full_assinatura_id INTEGER")
            )
        if "atalhos_email_json" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN atalhos_email_json TEXT")
            )
        if "soc_mode_active" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN soc_mode_active BOOLEAN DEFAULT 0")
            )
        if "soc_encryption_active" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE runtime_config ADD COLUMN soc_encryption_active BOOLEAN DEFAULT 0"
                )
            )
        if "soc_key_verifier" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN soc_key_verifier VARCHAR(64)")
            )
        if "soc_motivo" not in cols:
            conn.execute(text("ALTER TABLE runtime_config ADD COLUMN soc_motivo TEXT"))
        if "soc_ativado_em" not in cols:
            conn.execute(text("ALTER TABLE runtime_config ADD COLUMN soc_ativado_em DATETIME"))
        if "soc_ativado_por_id" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN soc_ativado_por_id INTEGER")
            )
        if "soc_ativado_por_nome" not in cols:
            conn.execute(
                text("ALTER TABLE runtime_config ADD COLUMN soc_ativado_por_nome VARCHAR(150)")
            )


def _migrate_usuarios_columns() -> None:
    """SQLite: troca obrigatória de senha no primeiro acesso."""
    from .config import settings

    insp = inspect(engine)
    if "usuarios" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("usuarios")}
    with engine.begin() as conn:
        if "must_change_password" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE usuarios ADD COLUMN must_change_password BOOLEAN DEFAULT 0"
                )
            )
            conn.execute(
                text(
                    "UPDATE usuarios SET must_change_password = 1 "
                    "WHERE username = :u AND must_change_password = 0"
                ),
                {"u": settings.admin_username},
            )
        if "acesso_backup" not in cols:
            conn.execute(
                text("ALTER TABLE usuarios ADD COLUMN acesso_backup BOOLEAN DEFAULT 0")
            )
            conn.execute(
                text("UPDATE usuarios SET acesso_backup = 1 WHERE is_admin = 1")
            )
        if "is_diretor" not in cols:
            conn.execute(
                text("ALTER TABLE usuarios ADD COLUMN is_diretor BOOLEAN DEFAULT 0")
            )
        if "recovery_token_enc" not in cols:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN recovery_token_enc TEXT"))


def _migrate_diretor_protegido() -> None:
    """Marca admindiretor como conta protegida (visível só ao próprio diretor)."""
    from .config import settings

    insp = inspect(engine)
    if "usuarios" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("usuarios")}
    if "is_diretor" not in cols:
        return
    un = (settings.diretor_username or "admindiretor").strip().lower()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE usuarios SET is_diretor = 1, is_admin = 1, acesso_backup = 1 "
                "WHERE lower(trim(username)) = :u"
            ),
            {"u": un},
        )


def _migrate_envios_columns() -> None:
    """SQLite: adiciona colunas novas a envios."""
    insp = inspect(engine)
    if "envios" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("envios")}
    with engine.begin() as conn:
        if "tipo_codigo" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN tipo_codigo VARCHAR(60)"))
        if "assinatura_id" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN assinatura_id INTEGER"))
        if "usuario_envio_id" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN usuario_envio_id INTEGER"))
        if "enviado_por" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN enviado_por VARCHAR(150)"))
        if "arquivo_colocado_por" not in cols:
            conn.execute(
                text("ALTER TABLE envios ADD COLUMN arquivo_colocado_por VARCHAR(150)")
            )


def _migrate_avulso_para_manual() -> None:
    """Renomeia tipo_envio AVULSO -> MANUAL nos envios já existentes."""
    insp = inspect(engine)
    if "envios" not in insp.get_table_names():
        return
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE envios SET tipo_envio='MANUAL' WHERE tipo_envio='AVULSO'")
        )


def _seed_runtime_config() -> None:
    """Garante linha única de configuração runtime (FULL pelo painel)."""
    from . import models

    s = SessionLocal()
    try:
        row = s.get(models.RuntimeConfig, 1)
        if row is None:
            s.add(
                models.RuntimeConfig(
                    id=1,
                    full_scan_active=True,
                    full_scan_interval_seconds=settings.full_scan_interval_seconds,
                    full_scan_exec_time="08:00",
                    full_lote_size=5,
                    full_intervalo_lote_min=5,
                    full_rescan_horas=1,
                    full_modo_ativo=True,
                )
            )
            s.commit()
    finally:
        s.close()
