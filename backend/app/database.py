"""Setup do SQLAlchemy + SQLite."""
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
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
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine = create_engine(_db_url, **engine_kwargs)


if _db_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()
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
    # Estas colunas precisam existir antes de qualquer consulta ORM: os models
    # consolidados ja as selecionam mesmo em bancos legados.
    _migrate_clientes_crypto_columns()
    _migrate_envios_columns()
    _migrate_tipos_envio_columns()
    _migrate_assuntos_email()
    _migrate_runtime_config_columns()
    _migrate_avulso_para_manual()
    _migrate_usuarios_columns()
    _migrate_diretor_protegido()
    _seed_runtime_config()
    _import_crypto_events()
    _migrate_clientes_encryption_data()
    _migrate_envios_encryption_data()
    _seed_diretor_conta()
    _run_alembic_migrations()


def _migrate_assuntos_email() -> None:
    """Adiciona o vinculo de assunto e importa assuntos legados dos corpos."""
    # Alguns testes, scripts de manutencao e instalacoes antigas executam esta
    # migracao diretamente. Garanta antes as demais colunas do model
    # ``TipoEnvio`` para que a consulta ORM abaixo tambem funcione nesses casos.
    _migrate_tipos_envio_columns()
    insp = inspect(engine)
    if "tipos_envio" not in insp.get_table_names():
        return
    colunas = {c["name"] for c in insp.get_columns("tipos_envio")}
    if "assunto_email_id" not in colunas:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE tipos_envio ADD COLUMN assunto_email_id INTEGER")
            )

    from . import models

    s = sessionmaker(bind=engine, future=True)()
    try:
        tipos = (
            s.query(models.TipoEnvio)
            .join(
                models.CorpoEmail,
                models.TipoEnvio.corpo_email_id == models.CorpoEmail.id,
            )
            .filter(models.TipoEnvio.assunto_email_id.is_(None))
            .all()
        )
        por_corpo: dict[int, models.AssuntoEmail] = {}
        for tipo in tipos:
            corpo = tipo.corpo_email
            texto = (corpo.assunto or "").strip() if corpo else ""
            if not corpo or not texto:
                continue
            assunto = por_corpo.get(corpo.id)
            if assunto is None:
                nome_base = f"Assunto - {corpo.nome}"[:120]
                nome = nome_base
                sufixo = 2
                existente = s.query(models.AssuntoEmail).filter(
                    models.AssuntoEmail.nome == nome
                ).first()
                if existente and (existente.assunto or "").strip() == texto:
                    assunto = existente
                while assunto is None and existente:
                    marcador = f" ({sufixo})"
                    nome = f"{nome_base[:120 - len(marcador)]}{marcador}"
                    sufixo += 1
                    existente = s.query(models.AssuntoEmail).filter(
                        models.AssuntoEmail.nome == nome
                    ).first()
                    if existente and (existente.assunto or "").strip() == texto:
                        assunto = existente
                if assunto is None:
                    assunto = models.AssuntoEmail(
                        nome=nome,
                        descricao=f"Importado do corpo de e-mail {corpo.nome}"[:255],
                        assunto=texto,
                        ativo=corpo.ativo,
                    )
                    s.add(assunto)
                    s.flush()
                por_corpo[corpo.id] = assunto
            tipo.assunto_email_id = assunto.id
        s.commit()
    finally:
        s.close()


def _run_alembic_migrations() -> None:
    """Registra o schema atual como baseline e aplica revisÃµes futuras."""
    from alembic import command
    from alembic.config import Config

    config_path = BASE_DIR / "alembic.ini"
    if not config_path.is_file():
        return
    cfg = Config(str(config_path))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _db_url)
    command.upgrade(cfg, "head")


def _seed_diretor_conta() -> None:
    from .services.diretor_service import seed_diretor

    s = SessionLocal()
    try:
        seed_diretor(s)
    finally:
        s.close()


def _import_crypto_events() -> None:
    from .events import cliente_crypto_events  # noqa: F401
    from .events import envio_crypto_events  # noqa: F401


def _migrate_envios_encryption_data() -> None:
    from .services import envio_crypto

    s = SessionLocal()
    try:
        envio_crypto.migrate_plaintext_envios(s)
    finally:
        s.close()


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
        if "destinatarios_adicionais_json" not in cols:
            conn.execute(
                text("ALTER TABLE clientes ADD COLUMN destinatarios_adicionais_json TEXT")
            )


def _migrate_tipos_envio_columns() -> None:
    insp = inspect(engine)
    if "tipos_envio" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("tipos_envio")}
    with engine.begin() as conn:
        if "capas_iniciais_json" not in cols:
            conn.execute(text("ALTER TABLE tipos_envio ADD COLUMN capas_iniciais_json TEXT"))
        if "capas_finais_json" not in cols:
            conn.execute(text("ALTER TABLE tipos_envio ADD COLUMN capas_finais_json TEXT"))


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
        if "session_version" not in cols:
            conn.execute(
                text("ALTER TABLE usuarios ADD COLUMN session_version INTEGER DEFAULT 1 NOT NULL")
            )


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
    indexes = {idx["name"]: idx for idx in insp.get_indexes("envios")}
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
        if "nome_boleto" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN nome_boleto VARCHAR(500)"))
        if "caminho_backup_boleto" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN caminho_backup_boleto VARCHAR(500)"))
        if "arquivo_sha256" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN arquivo_sha256 VARCHAR(64)"))
        if "idempotency_key" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN idempotency_key VARCHAR(64)"))
        if "provider_message_id" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN provider_message_id VARCHAR(255)"))
        if "delivery_status" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN delivery_status VARCHAR(40)"))
        if "delivery_updated_at" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN delivery_updated_at DATETIME"))
        if "destinatario_email" not in cols:
            conn.execute(
                text("ALTER TABLE envios ADD COLUMN destinatario_email VARCHAR(1024)")
            )
        if "destinatarios_manuais_qtd" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE envios ADD COLUMN "
                    "destinatarios_manuais_qtd INTEGER DEFAULT 0"
                )
            )
        if "reenvio_de_id" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN reenvio_de_id INTEGER"))
        if "forma_pagamento" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN forma_pagamento VARCHAR(40)"))
        if "parcelamento" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN parcelamento INTEGER"))
        if "numero_proposta" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN numero_proposta VARCHAR(100)"))
        if "item_segurado" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN item_segurado VARCHAR(150)"))
        if "capas_iniciais_json" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN capas_iniciais_json TEXT"))
        if "capas_finais_json" not in cols:
            conn.execute(text("ALTER TABLE envios ADD COLUMN capas_finais_json TEXT"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_envios_numero_proposta "
                "ON envios (numero_proposta)"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_envios_idempotency_key "
                "ON envios (idempotency_key)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_envios_provider_message_id "
                "ON envios (provider_message_id)"
            )
        )
        # Uma tentativa só pode originar um filho direto; novos retries formam
        # uma cadeia. Isso também fecha a corrida de duplo clique concorrente.
        reenvio_index = indexes.get("ix_envios_reenvio_de_id")
        if not reenvio_index or not reenvio_index.get("unique"):
            conn.execute(text("DROP INDEX IF EXISTS ix_envios_reenvio_de_id"))
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_envios_reenvio_de_id "
                    "ON envios (reenvio_de_id)"
                )
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
