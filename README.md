# Sistema de Envio de Apólices

Solução completa para automatizar o envio de apólices em PDF por e-mail, com
painel administrativo web e modo de envio automático.

## Arquitetura

```
envio-sistema/
├── backend/              FastAPI + SQLite + watcher FULL
├── frontend/             Vue 3 + Vite (identidade Terra Fértil — verde)
├── installer/            Instalador PowerShell p/ Windows Server
└── README.md
```

### Stack
- **Backend**: Python 3.11 · FastAPI · SQLAlchemy · SQLite · pdfplumber · smtplib
- **Frontend**: Vue 3 · Vite · Pinia · vue-router · axios
- **Servidor**: Windows Server 2019/2022, serviços gerenciados via NSSM

### Fluxos suportados

**FULL (automático)** — watcher varre pasta, extrai CPF/CNPJ/apólice do PDF,
identifica o cliente cadastrado, envia por e-mail, faz backup e move o arquivo
para `processados/`.

**AVULSO (manual, via front)** — operador escolhe cliente (ou cadastra na
hora), sobe o PDF, envia imediatamente. Backup e log idênticos ao FULL.

## Banco de dados

- `clientes` — id, nome, email (editável), cpf, cnpj, telefone, observações
- `envios` — id, cliente_id, tipo_envio (FULL/AVULSO), arquivo original/final,
  numero_apolice, status (pendente/enviado/erro), timestamps
- `usuarios` — id, username, nome, senha_hash, is_admin, ativo

## Backup

Todo envio bem-sucedido é copiado para (sempre relativos à pasta **`backend/`**, não ao diretório de onde arranca o processo):
```
backend/backup/<YYYY-MM>/<nome_cliente>/<arquivo.pdf>
```

**Capa:** coloque `capa.pdf` em **`backend/capas/`** (ou ajuste `CAPA_*` no `backend/.env`).
Se existir, o sistema junta **capa + apólice** num único PDF antes do backup e do e-mail; veja `backend/capas/README.txt`.

## Login

Estrutura pronta, **desativada por padrão** (`AUTH_ENABLED=false`).
Para ativar, troque no `.env` e reinicie. Enquanto desativado, toda a rede
interna acessa o painel direto sem login — como pedido.

---

## Instalação (Windows Server)

Ver [installer/README-INSTALL.md](installer/README-INSTALL.md).

TL;DR: PowerShell como admin, `cd installer`, `.\install.ps1`. Instala tudo
(Python, Node, NSSM), cria venv, compila o front, registra os serviços.

Após instalar no servidor, gerencie os serviços com PowerShell (`Start-Service`,
`Stop-Service`, `Restart-Service`) ou pelo painel de serviços do Windows.

---

## Inicialização rápida (Windows, duplo clique)

Foram simplificados os inicializadores para apenas dois scripts, cada um dentro
da sua pasta:

| Componente | Script |
|--------|--------|
| Backend | `backend/iniciar-backend.bat` |
| Frontend | `frontend/iniciar-frontend.bat` |

---

## Rodar em modo desenvolvimento (Linux/Mac/Windows)

**Backend:**
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
cp .env.example .env          # edite SMTP_*
python run.py
```
API em http://localhost:8000/docs

**Frontend:**
```bash
cd frontend
npm install
cp .env.example .env          # VITE_API_URL=http://localhost:8000
npm run dev
```
Front em http://localhost:5173

---

## Usar o front em outra máquina

1. Copie a pasta `frontend/` para o PC do usuário.
2. Edite `frontend/.env`:
   ```
   VITE_API_URL=http://<IP-DO-SERVIDOR-WINDOWS>:8000
   ```
3. `npm install && npm run build && npm run preview` ou `npm run dev`.

O backend roda no Windows Server, o front pode rodar em qualquer máquina da
rede apontando para a API.

---

## Ativando login (quando precisar de ramificação de usuários)

1. `backend/.env` → `AUTH_ENABLED=true`, defina uma `SECRET_KEY` forte e uma
   `ADMIN_PASSWORD` segura.
2. Reinicie: `Restart-Service EnvioApolices-API`.
3. Primeiro login: `admin` / valor de `ADMIN_PASSWORD`.
4. Entre em **Usuários** no painel para criar/remover/editar contas.

---

## Endpoints principais (API)

| Método | Rota                         | Descrição                                |
|--------|------------------------------|------------------------------------------|
| GET    | `/api/status`                | Status geral do sistema                  |
| POST   | `/api/auth/login`            | Login (JWT)                              |
| GET    | `/api/clientes`              | Listar/buscar                            |
| POST   | `/api/clientes`              | Criar                                    |
| PUT    | `/api/clientes/{id}`         | Editar                                   |
| DELETE | `/api/clientes/{id}`         | Remover                                  |
| POST   | `/api/envios/avulso`         | Upload + envio imediato (multipart)      |
| GET    | `/api/envios`                | Histórico (filtros: tipo, status, dias)  |
| GET    | `/api/envios/export.csv`     | Exportar histórico em CSV                  |
| POST   | `/api/envios/reenviar-erros` | Reenviar em lote envios com erro           |
| POST   | `/api/envios/{id}/reenviar`  | Reenviar um envio com erro (usa backup)    |
| GET    | `/api/clientes/duplicados`   | Grupos CPF/CNPJ/e-mail duplicados          |
| POST   | `/api/clientes/{id}/exclusao-lgpd` | Exclusão LGPD (cadastro + backups) |
| CRUD   | `/api/usuarios`              | Gestão de usuários (admin)               |

Documentação interativa: `/docs` (Swagger) e `/redoc`.
