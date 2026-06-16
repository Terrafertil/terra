"""Schemas Pydantic (entrada/saída da API)."""
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ========= Cliente =========
class ClienteBase(BaseModel):
    nome: str
    email: EmailStr
    cpf: str | None = None
    cnpj: str | None = None
    telefone: str | None = None
    observacoes: str | None = None
    ativo: bool = True


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    nome: str | None = None
    email: EmailStr | None = None
    cpf: str | None = None
    cnpj: str | None = None
    telefone: str | None = None
    observacoes: str | None = None
    ativo: bool | None = None


class ClienteOut(ClienteBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ========= Auto =========
class AutoBase(BaseModel):
    placa: str
    marca: str | None = None
    modelo: str | None = None
    ano: str | None = None
    chassi: str | None = None
    renavam: str | None = None
    cor: str | None = None
    combustivel: str | None = None
    observacoes: str | None = None
    ativo: bool = True


class AutoCreate(AutoBase):
    cliente_id: int


class AutoUpdate(BaseModel):
    placa: str | None = None
    marca: str | None = None
    modelo: str | None = None
    ano: str | None = None
    chassi: str | None = None
    renavam: str | None = None
    cor: str | None = None
    combustivel: str | None = None
    observacoes: str | None = None
    ativo: bool | None = None
    cliente_id: int | None = None


class AutoOut(AutoBase):
    id: int
    cliente_id: int
    cliente_nome: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ========= Tipo de envio =========
class TipoEnvioBase(BaseModel):
    codigo: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_\-]+$")
    nome: str
    descricao: str | None = None
    ordem: int = 0
    na_fila_full: bool = True
    corpo_email_id: int | None = None
    ativo: bool = True


class TipoEnvioCreate(TipoEnvioBase):
    pass


class TipoEnvioUpdate(BaseModel):
    codigo: str | None = Field(None, min_length=1, max_length=60, pattern=r"^[a-z0-9_\-]+$")
    nome: str | None = None
    descricao: str | None = None
    ordem: int | None = None
    na_fila_full: bool | None = None
    corpo_email_id: int | None = None
    ativo: bool | None = None


class TipoEnvioOut(TipoEnvioBase):
    id: int
    created_at: datetime
    updated_at: datetime
    pasta: str | None = None  # caminho absoluto da subpasta
    model_config = ConfigDict(from_attributes=True)


class TipoEnvioOrdemPatch(BaseModel):
    """Payload para reordenar lista (drag&drop): lista de codigos na ordem."""
    ordem: list[str]


# ========= Corpo de e-mail =========
class CorpoEmailBase(BaseModel):
    nome: str
    descricao: str | None = None
    assunto: str | None = None
    html: str = ""
    ativo: bool = True


class CorpoEmailCreate(CorpoEmailBase):
    pass


class CorpoEmailUpdate(BaseModel):
    nome: str | None = None
    descricao: str | None = None
    assunto: str | None = None
    html: str | None = None
    ativo: bool | None = None


class CorpoEmailOut(CorpoEmailBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AtalhoPersonalizado(BaseModel):
    id: str
    nome: str = Field(..., min_length=1, max_length=120)
    html: str = Field(..., min_length=1)
    descricao: str | None = Field(None, max_length=255)


class AtalhosPersonalizadosPatch(BaseModel):
    atalhos: list[AtalhoPersonalizado]


# ========= Assinatura =========
class AssinaturaBase(BaseModel):
    nome: str
    pessoa: str | None = None
    cargo: str | None = None
    email_contato: str | None = None
    telefone: str | None = None
    ativo: bool = True


class AssinaturaCreate(AssinaturaBase):
    pass


class AssinaturaUpdate(BaseModel):
    nome: str | None = None
    pessoa: str | None = None
    cargo: str | None = None
    email_contato: str | None = None
    telefone: str | None = None
    ativo: bool | None = None


class AssinaturaOut(AssinaturaBase):
    id: int
    arquivo: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ========= Envio =========
class EnvioOut(BaseModel):
    id: int
    cliente_id: int
    cliente_nome: str | None = None
    cliente_email: str | None = None
    tipo_envio: str
    tipo_codigo: str | None = None
    nome_arquivo_original: str | None = None
    nome_arquivo_final: str | None = None
    numero_apolice: str | None = None
    status: str
    erro_msg: str | None = None
    caminho_backup: str | None = None
    assunto_email: str | None = None
    assinatura_id: int | None = None
    usuario_envio_id: int | None = None
    enviado_por: str | None = None
    arquivo_colocado_por: str | None = None
    criado_em: datetime
    enviado_em: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class EnvioReenvioItemOut(BaseModel):
    envio_id: int
    ok: bool
    status: str | None = None
    erro: str | None = None


class EnvioReenvioLoteOut(BaseModel):
    total: int
    sucesso: int
    falha: int
    itens: list[EnvioReenvioItemOut]


class ClienteDuplicadoResumo(BaseModel):
    id: int
    nome: str
    email: str
    cpf: str | None = None
    cnpj: str | None = None
    ativo: bool = True


class ClienteDuplicadoGrupoOut(BaseModel):
    tipo: str
    chave: str
    clientes: list[ClienteDuplicadoResumo]


class ClienteLgpdExclusaoIn(BaseModel):
    confirmar_nome: str = Field(min_length=1)
    remover_backups: bool = True


class ClienteLgpdExclusaoOut(BaseModel):
    cliente_nome: str
    envios_removidos: int
    ficheiros_backup_removidos: int


class EnvioAvulsoPayload(BaseModel):
    cliente_id: int | None = None
    cliente_novo: ClienteCreate | None = None
    numero_apolice: str | None = None
    assunto: str | None = None
    mensagem: str | None = None


class EnvioDemoOut(BaseModel):
    """Resposta da rota /demonstrar — devolve assunto e corpo já renderizados."""
    de: str
    para: str
    assunto: str
    html: str


# ========= Usuário =========
class UsuarioBase(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    nome: str
    email: str | None = None
    is_admin: bool = False
    acesso_backup: bool = False
    ativo: bool = True


class UsuarioCreate(UsuarioBase):
    senha: str = Field(min_length=8)


class UsuarioUpdate(BaseModel):
    nome: str | None = None
    email: str | None = None
    is_admin: bool | None = None
    acesso_backup: bool | None = None
    ativo: bool | None = None
    senha: str | None = None


class UsuarioOut(UsuarioBase):
    id: int
    must_change_password: bool = False
    is_diretor: bool = False
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ========= Auth =========
class LoginPayload(BaseModel):
    username: str
    senha: str


class TrocaSenhaIn(BaseModel):
    senha_atual: str = Field(min_length=1)
    senha_nova: str = Field(min_length=8)
    senha_nova_confirmacao: str = Field(min_length=8)


class TrocaSenhaOut(BaseModel):
    mensagem: str
    access_token: str
    token_type: str = "bearer"
    user: UsuarioOut


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UsuarioOut


# ========= Status =========
class StatusOut(BaseModel):
    status: str
    versao: str
    auth_enabled: bool
    full_enabled: bool
    full_env_enabled: bool
    full_scan_active: bool
    full_scan_interval_seconds: int
    full_scan_exec_time: str = "08:00"
    full_watch_folder: str
    full_lote_size: int = 5
    full_intervalo_lote_min: int = 5
    full_rescan_horas: int = 1
    full_modo_ativo: bool = True
    full_assinatura_id: int | None = None
    total_clientes: int
    total_envios: int
    notificacoes_nao_lidas: int = 0
    ocr_disponivel: bool = False
    backend_access_enabled: bool = False
    data_encryption_enabled: bool = False
    soc_mode_active: bool = False
    soc_encryption_active: bool = False
    soc_motivo: str = ""
    soc_ativado_em: str | None = None
    soc_ativado_por_nome: str = ""


class SocStatusOut(BaseModel):
    soc_mode_active: bool
    soc_encryption_active: bool
    soc_motivo: str = ""
    soc_ativado_em: str | None = None
    soc_ativado_por_nome: str = ""


class SocAtivarIn(BaseModel):
    chave_soc: str = Field(min_length=8)
    chave_soc_confirmacao: str = Field(min_length=8)
    motivo: str | None = None


class SocDesativarIn(BaseModel):
    chave_soc: str = Field(min_length=8)


class SocAcaoOut(BaseModel):
    soc_mode_active: bool
    mensagem: str
    clientes_recifrados: int | None = None
    clientes_restaurados: int | None = None


class DiretorTokenOut(BaseModel):
    token: str
    mensagem: str = (
        "Guarde este token num cofre seguro. Serve apenas para recuperar o acesso do Admin Diretor."
    )


class RecuperarDiretorIn(BaseModel):
    token: str = Field(min_length=8)
    senha_nova: str = Field(min_length=8)
    senha_nova_confirmacao: str = Field(min_length=8)


class BackendAccessVerifyIn(BaseModel):
    chave: str = Field(min_length=1)


class FullRuntimePatch(BaseModel):
    full_scan_active: bool | None = None
    full_scan_interval_seconds: int | None = Field(None, ge=10, le=3600)
    full_scan_exec_time: str | None = Field(
        None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$"
    )
    full_lote_size: int | None = Field(None, ge=1, le=200)
    full_intervalo_lote_min: int | None = Field(None, ge=0, le=240)
    full_rescan_horas: int | None = Field(None, ge=0, le=72)
    full_modo_ativo: bool | None = None
    full_assinatura_id: int | None = None


class NotificacaoFullOut(BaseModel):
    id: int
    arquivo: str
    motivo: str
    layout: str | None = None
    tipo_codigo: str | None = None
    pasta: str | None = None
    lida: bool
    criado_em: datetime
    model_config = ConfigDict(from_attributes=True)


class PdfAnaliseOut(BaseModel):
    cpf: str | None = None
    cnpj: str | None = None
    numero_apolice: str | None = None
    layout: str
    seguradora: str | None = None
    produto: str | None = None
    avisos: list[str] = []
    extracao_automatica: bool = True
    ocr_usado: bool = False
    ocr_disponivel: bool = False
    amostra_texto: str = ""
    cliente_sugerido_id: int | None = None
    cliente_sugerido_nome: str | None = None
    requer_senha: bool = False
    senha_invalida: bool = False


# ========= Capa =========
class CapaInfoOut(BaseModel):
    existe: bool
    nome: str
    caminho: str
    tamanho_bytes: int = 0
    paginas: int = 0
    atualizado_em: datetime | None = None


# ========= Backup (file explorer) =========
class BackupItemOut(BaseModel):
    nome: str
    caminho_relativo: str
    eh_pasta: bool
    tamanho_bytes: int = 0
    atualizado_em: datetime | None = None


class BackupListagemOut(BaseModel):
    caminho_atual: str
    parent_relativo: str | None = None
    itens: list[BackupItemOut]
