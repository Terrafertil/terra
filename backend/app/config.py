"""Configurações carregadas do .env."""
from pathlib import Path
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Servidor
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    docs_enabled: bool = False

    # Banco
    database_url: str = "sqlite:///./data/envio.db"

    # Porta de acesso à API (cabeçalho X-Backend-Access-Key) — recomendado em produção
    backend_access_enabled: bool = False
    backend_access_key: str = ""

    # Criptografia dupla dos dados de clientes no SQLite (AES-256-GCM x2)
    data_encryption_enabled: bool = False
    data_encryption_password: str = ""
    # Opcional: salt fixo (senão usa ficheiro backend/data/.crypto_salt)
    data_encryption_salt: str = ""

    # Auth
    auth_enabled: bool = False
    secret_key: str = "troque-essa-chave"
    access_token_expire_minutes: int = 480
    auth_cookie_name: str = "tf_session"
    auth_cookie_secure: bool = False
    backend_access_cookie_name: str = "tf_backend_access"
    jwt_issuer: str = "terra-fertil-envios"
    jwt_audience: str = "terra-fertil-painel"
    admin_username: str = "admin"
    admin_password: str = "admin"
    diretor_username: str = "admindiretor"
    diretor_password: str = "TfD1r3t0r2026"
    # Se vazio, é gerado no primeiro seed (letras e números) e guardado cifrado na BD
    diretor_recovery_token: str = ""

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # SMTP transacional (Brevo — relay SMTP com anexo PDF)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_USER", "BREVO_SMTP_LOGIN"),
    )
    smtp_password: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_PASSWORD", "BREVO_SMTP_KEY"),
    )
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_from_email: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_FROM_EMAIL", "BREVO_SENDER_EMAIL"),
    )
    smtp_from_name: str = Field(
        default="Sistema de Envio",
        validation_alias=AliasChoices("SMTP_FROM_NAME", "BREVO_SENDER_NAME"),
    )
    use_brevo: bool = True
    brevo_max_message_mb: int = 20
    brevo_webhook_token: str = ""

    @model_validator(mode="after")
    def _defaults_brevo(self):
        if not self.use_brevo:
            return self

        host = (self.smtp_host or "").strip().lower()
        # Migração segura: um .env antigo do SES não pode continuar enviando pela AWS.
        if not host or host.endswith(".amazonaws.com"):
            self.smtp_host = "smtp-relay.brevo.com"

        # A porta 465 usa TLS implícito; 587/2525 usam STARTTLS.
        if self.smtp_port == 465:
            self.smtp_use_ssl = True
            self.smtp_use_tls = False
        elif self.smtp_port in (587, 2525):
            self.smtp_use_ssl = False
            self.smtp_use_tls = True
        return self

    @property
    def email_provider(self) -> str:
        return "brevo" if self.use_brevo else "smtp"

    @property
    def email_configured(self) -> bool:
        obrigatorios = (
            self.smtp_host,
            self.smtp_user,
            self.smtp_password,
            self.smtp_from_email,
        )
        return all(bool((valor or "").strip()) for valor in obrigatorios)

    email_subject_default: str = "Envio de Apolice - {numero_apolice}"
    email_template_default: str = "templates/email_padrao.html"

    # FULL
    full_enabled: bool = True
    full_watch_folder: str = "./entrada"
    full_scan_interval_seconds: int = 30
    full_lote_size: int = 5
    full_intervalo_lote_min: int = 5
    full_rescan_horas: int = 1

    # Backup/pastas
    backup_folder: str = "./backup"
    # Política interna: após N meses a equipe pode apagar pastas antigas em backup/ (ver Tutorial)
    backup_retention_months: int = 24
    backup_retention_auto: bool = False
    max_backup_zip_mb: int = 2048
    upload_folder: str = "./uploads"
    processed_folder: str = "./processados"
    max_upload_mb: int = 25
    max_pdf_pages: int = 300

    # Capa
    capa_enabled: bool = True
    capa_folder: str = "./capas"
    capa_arquivo_padrao: str = "capa.pdf"

    # Assinaturas e corpos de e-mail
    assinaturas_folder: str = "./assinaturas"

    # OCR (PDFs só imagem) — requer Tesseract instalado no servidor
    ocr_enabled: bool = True
    ocr_max_pages: int = 5
    ocr_lang: str = "por"
    tesseract_cmd: str = ""

    @property
    def cors_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def data_path(self, configured: str) -> Path:
        """Caminhos relativos no .env são sempre em relação à pasta backend/, não ao cwd."""
        p = Path(configured)
        if p.is_absolute():
            return p.resolve()
        return (BASE_DIR / p).resolve()

    def ensure_dirs(self) -> None:
        for rel in (
            self.backup_folder,
            self.upload_folder,
            self.processed_folder,
            self.full_watch_folder,
            self.capa_folder,
            self.assinaturas_folder,
        ):
            self.data_path(rel).mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.replace("sqlite:///", "", 1))
            if not db_path.is_absolute():
                db_path = (BASE_DIR / db_path).resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
