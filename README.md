# Sistema de Envio de Apólices

Aplicação para envio manual e automático de apólices e boletos em PDF. O backend
FastAPI também serve o painel Vue compilado, registra histórico, mantém backups e
acompanha a entrega dos e-mails transacionais pela Brevo.

## Arquitetura

```text
terra/
├── backend/      FastAPI, SQLite, watcher FULL e migrações Alembic
├── frontend/     Vue 3, Vite, Pinia e vue-router
├── installer/    instalação e atualização no Windows Server
└── .github/      validações automáticas de backend e frontend
```

- Python 3.11+ e Node.js 20+.
- Um serviço Windows (`EnvioApolices-API`) e uma única porta, `8000` por padrão.
- SQLite em modo WAL, com `busy_timeout`, chaves estrangeiras e migrações versionadas.
- Sessão em cookie HttpOnly; o token de autenticação e a chave do backend não ficam no
  `localStorage` nem no bundle do frontend.
- Upload em streaming, limite configurável, validação estrutural de PDF/imagem e
  bloqueio de arquivos malformados.

## Fluxos

### Envio manual

O operador escolhe o cliente, envia a apólice e, opcionalmente, o boleto. O sistema
valida os arquivos, monta a mensagem, envia pela Brevo, registra a operação e guarda
os dois documentos no backup.

### FULL automático

O watcher varre `backend/entrada/`, identifica o tipo, extrai CPF/CNPJ e número da
apólice, localiza o cliente, envia a mensagem e move o PDF para `processados/`.
Trabalho pesado de PDF/OCR/SMTP é executado fora do loop assíncrono da API.

O envio é idempotente: o mesmo arquivo/contexto não é reenviado acidentalmente. Um
registro que ficou pendente após interrupção é marcado como incerto para revisão, em
vez de disparar uma duplicata automática.

## Brevo

Não existe dependência operacional da AWS. O envio usa o relay SMTP transacional da
Brevo em `smtp-relay.brevo.com`, normalmente na porta `587` com STARTTLS.

No painel Brevo:

1. Autentique o domínio e o remetente.
2. Em **SMTP & API → SMTP**, copie o login e gere uma chave SMTP.
3. Não use a API key nem a senha da conta como senha do relay.
4. Cadastre o webhook transacional apontando para
   `https://SEU-DOMINIO/api/webhooks/brevo` e configure a autenticação Bearer com o
   valor de `BREVO_WEBHOOK_TOKEN`.

Configuração mínima em `backend/.env`:

```dotenv
USE_BREVO=true
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USE_SSL=false
BREVO_SMTP_LOGIN=seu-login-smtp
BREVO_SMTP_KEY=sua-chave-smtp
BREVO_SENDER_EMAIL=remetente@seu-dominio.com.br
BREVO_SENDER_NAME=Sua Empresa
BREVO_MAX_MESSAGE_MB=20
BREVO_WEBHOOK_TOKEN=gere-um-token-aleatorio-longo
```

O backend mede a mensagem MIME completa antes do envio e registra o identificador do
provedor. O webhook atualiza o histórico com aceito, entregue, abertura, clique,
bounce, bloqueio ou erro. Remova variáveis antigas `USE_AWS_SES`, `AWS_SES_REGION` e
credenciais SES de instalações migradas.

## Segurança

Produção deve manter:

```dotenv
AUTH_ENABLED=true
BACKEND_ACCESS_ENABLED=true
DATA_ENCRYPTION_ENABLED=true
APP_DEBUG=false
DOCS_ENABLED=false
```

O instalador gera `SECRET_KEY`, `BACKEND_ACCESS_KEY`, `DATA_ENCRYPTION_PASSWORD`,
`BREVO_WEBHOOK_TOKEN` e senhas iniciais aleatórias em uma instalação nova. Arquivos
`.env`, banco, salt criptográfico, PDFs, backups e logs nunca são copiados do repositório
durante uma atualização.

Use HTTPS por meio de um proxy reverso/certificado válido e então defina
`AUTH_COOKIE_SECURE=true`. A aplicação envia HSTS quando acessada por HTTPS. Nunca
publique diretamente o SQLite, `.env`, `data/.crypto_salt` ou as pastas de documentos.

As páginas administrativas e as operações destrutivas exigem administrador. A API
tem limitação de tentativas para login, recuperação, chave de acesso e webhook. A
prévia de e-mail é sanitizada e a política CSP impede scripts, frames e conexões para
origens externas.

## Banco, backup e recuperação

Os arquivos persistentes ficam, por padrão, relativos a `backend/`:

```text
data/envio.db
data/.crypto_salt
backup/YYYY-MM/<cliente>/
entrada/
processados/
capas/
assinaturas/
```

Faça cópia externa e imutável de `data/`, `backup/`, `.env`, `capas/` e
`assinaturas/`. A retenção automática só é aplicada quando
`BACKUP_RETENTION_AUTO=true`; o padrão é não apagar.

Para rotacionar a chave de criptografia, pare o serviço e execute:

```powershell
cd C:\envio-sistema\backend
.\.venv\Scripts\python scripts\rotate_encryption_key.py --confirm-api-offline
```

O utilitário cria cópias de segurança do banco, `.env` e salt antes de recifrar. A
chave SOC de emergência não é armazenada no servidor e não pode ser rotacionada por
esse comando.

## Instalação no Windows Server

Consulte [installer/README-INSTALL.md](installer/README-INSTALL.md). Resumo:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
cd installer
.\install.ps1 -ServerIp 192.168.1.50
```

Ao final, acesse `http://192.168.1.50:8000`. Para produção exposta fora da rede
confiável, coloque essa origem atrás de HTTPS.

## Desenvolvimento

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install --require-hashes -r requirements.lock
Copy-Item .env.example .env
# Para desenvolvimento local isolado: APP_HOST=127.0.0.1 e AUTH_ENABLED=false
.\.venv\Scripts\python run.py
```

Frontend, em outro terminal:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

O Vite usa proxy para `/api`; não é necessário gravar uma chave no frontend. O painel
de desenvolvimento abre em `http://localhost:5173`. O build de produção é servido
pelo backend em `http://localhost:8000`.

Para habilitar Swagger somente no ambiente de desenvolvimento, defina
`DOCS_ENABLED=true` e abra `http://localhost:8000/docs`.

## Verificações

```powershell
cd backend
.\.venv\Scripts\python -m compileall -q app tests scripts
.\.venv\Scripts\python -m unittest discover -s tests -v

cd ..\frontend
npm run check
npm audit --audit-level=high
```

A integração contínua repete compilação, testes, lint, build e auditoria do frontend.

## Endpoints operacionais

| Método | Rota | Finalidade |
|---|---|---|
| GET | `/api/health` | verificação mínima, sem dados internos |
| GET | `/api/status` | estado do sistema para usuário autenticado |
| POST | `/api/auth/login` | cria sessão HttpOnly |
| POST | `/api/envios/manual` | envio de apólice e boleto |
| GET | `/api/envios` | histórico |
| POST | `/api/envios/{id}/reenviar` | reenvio a partir do backup |
| POST | `/api/webhooks/brevo` | atualização autenticada de entrega |
| GET | `/api/backup/download` | backup autorizado |

Veja [ANALISE-MIGRACAO-BREVO.md](ANALISE-MIGRACAO-BREVO.md) para o relatório da
migração e das validações do provedor.
