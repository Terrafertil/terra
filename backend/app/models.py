"""Modelos ORM (SQLAlchemy)."""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(1024), nullable=False)
    email: Mapped[str] = mapped_column(String(1024), nullable=False)
    cpf: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cnpj: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cpf_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    cnpj_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    email_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    telefone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    envios: Mapped[list["Envio"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan"
    )
    autos: Mapped[list["Auto"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan"
    )


class Auto(Base):
    """Veiculos/autos vinculados a um cliente. Um cliente pode ter varios."""
    __tablename__ = "autos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    placa: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    marca: Mapped[str | None] = mapped_column(String(80), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ano: Mapped[str | None] = mapped_column(String(10), nullable=True)
    chassi: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    renavam: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cor: Mapped[str | None] = mapped_column(String(40), nullable=True)
    combustivel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    cliente: Mapped["Cliente"] = relationship(back_populates="autos")


class CorpoEmail(Base):
    """Corpo de e-mail (HTML) reutilizavel. Pode ser associado a um TipoEnvio."""
    __tablename__ = "corpos_email"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assunto: Mapped[str | None] = mapped_column(String(255), nullable=True)
    html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    tipos: Mapped[list["TipoEnvio"]] = relationship(back_populates="corpo_email")


class TipoEnvio(Base):
    """Tipo de envio (auto, residencial, teste...). Cria sub-pasta de mesmo nome
    em FULL_WATCH_FOLDER. Usa um corpo de e-mail e tem ordem para o FULL."""
    __tablename__ = "tipos_envio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0, index=True)
    na_fila_full: Mapped[bool] = mapped_column(Boolean, default=True)
    corpo_email_id: Mapped[int | None] = mapped_column(
        ForeignKey("corpos_email.id"), nullable=True
    )
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    corpo_email: Mapped["CorpoEmail | None"] = relationship(back_populates="tipos")


class Assinatura(Base):
    """Assinatura (foto + dados de quem assina). Usada como imagem inline no e-mail."""
    __tablename__ = "assinaturas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    pessoa: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email_contato: Mapped[str | None] = mapped_column(String(150), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    arquivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Envio(Base):
    __tablename__ = "envios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    # Modo: FULL ou MANUAL (antigamente AVULSO; migrado em init_db)
    tipo_envio: Mapped[str] = mapped_column(String(20), nullable=False)
    # Codigo do tipo (auto, residencial, teste...) — referencia tipos_envio.codigo
    tipo_codigo: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    nome_arquivo_original: Mapped[str | None] = mapped_column(String(500), nullable=True)
    nome_arquivo_final: Mapped[str | None] = mapped_column(String(500), nullable=True)
    numero_apolice: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pendente")
    erro_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    caminho_backup: Mapped[str | None] = mapped_column(String(500), nullable=True)
    assunto_email: Mapped[str | None] = mapped_column(String(500), nullable=True)
    assinatura_id: Mapped[int | None] = mapped_column(
        ForeignKey("assinaturas.id"), nullable=True
    )
    usuario_envio_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True, index=True
    )
    enviado_por: Mapped[str | None] = mapped_column(String(150), nullable=True)
    arquivo_colocado_por: Mapped[str | None] = mapped_column(String(150), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cliente: Mapped["Cliente"] = relationship(back_populates="envios")
    usuario_envio: Mapped["Usuario | None"] = relationship()


class NotificacaoFull(Base):
    """Alerta quando o FULL não processa um PDF (painel)."""

    __tablename__ = "notificacoes_full"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    layout: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tipo_codigo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    pasta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lida: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class RuntimeConfig(Base):
    """Configuracao em tempo de execucao (uma linha, id=1)."""

    __tablename__ = "runtime_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_scan_active: Mapped[bool] = mapped_column(Boolean, default=True)
    full_scan_interval_seconds: Mapped[int] = mapped_column(Integer, default=30)
    full_scan_exec_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    email_frases_dashboard: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON: lista de atalhos HTML personalizados no editor de corpos de e-mail
    atalhos_email_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # FULL — parametros do envio em lote
    full_lote_size: Mapped[int] = mapped_column(Integer, default=5)
    full_intervalo_lote_min: Mapped[int] = mapped_column(Integer, default=5)
    full_rescan_horas: Mapped[int] = mapped_column(Integer, default=1)
    full_modo_ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Assinatura padrao usada nos envios FULL
    full_assinatura_id: Mapped[int | None] = mapped_column(
        ForeignKey("assinaturas.id"), nullable=True
    )

    # Modo SOC (resposta a incidente)
    soc_mode_active: Mapped[bool] = mapped_column(Boolean, default=False)
    soc_encryption_active: Mapped[bool] = mapped_column(Boolean, default=False)
    soc_key_verifier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    soc_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    soc_ativado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    soc_ativado_por_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=True
    )
    soc_ativado_por_nome: Mapped[str | None] = mapped_column(String(150), nullable=True)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_diretor: Mapped[bool] = mapped_column(Boolean, default=False)
    recovery_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    acesso_backup: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
