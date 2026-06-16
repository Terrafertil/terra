# Instalador — Windows Server

## Pré-requisitos
- Windows Server 2019 / 2022
- Acesso como **Administrador**
- Conexão com a internet (para baixar Python, Node e NSSM)

## Instalação

Abra o **PowerShell como Administrador** na pasta `installer/` e rode:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\install.ps1
```

Opcionais:

```powershell
.\install.ps1 -InstallDir "D:\apps\envio" -ServicePort 8000 -FrontPort 5173
.\install.ps1 -SkipFrontend        # só o backend
.\install.ps1 -SkipServices        # não registra serviços, só prepara
```

O script faz automaticamente:
1. Instala Python 3.11+ (via winget ou download direto)
2. Instala Node.js LTS
3. Baixa e instala **NSSM** em `C:\tools\nssm\` e adiciona ao PATH
4. Copia os fontes para `C:\envio-sistema\`
5. Cria o venv Python, instala `requirements.txt`
6. Faz `npm install` + `npm run build` no frontend
7. Registra os serviços Windows `EnvioApolices-API` e `EnvioApolices-Front`
8. Libera as portas no firewall

## Gerenciar serviços no servidor

Depois da instalação, use PowerShell como administrador:

```powershell
Start-Service EnvioApolices-API
Start-Service EnvioApolices-Front
Get-Service EnvioApolices-*
Stop-Service EnvioApolices-Front -ErrorAction SilentlyContinue
Stop-Service EnvioApolices-API -ErrorAction SilentlyContinue
```

## Após instalar

Edite o arquivo de configuração do backend:
```
C:\envio-sistema\backend\.env
```
Ajuste principalmente:
- `SMTP_*` (credenciais do e-mail)
- `FULL_WATCH_FOLDER` (pasta que o watcher vai varrer)
- `ADMIN_PASSWORD` (senha inicial do admin)

Reinicie o serviço:
```powershell
Restart-Service EnvioApolices-API
```

Ver status:
```powershell
Get-Service EnvioApolices-*
```

## Operação recomendada no servidor

### Pastas que devem ter backup externo

Tudo abaixo é relativo à pasta `backend/` da instalação:

| Pasta / ficheiro | Função |
|------------------|--------|
| `data/envio.db` | Base de dados (clientes, envios) |
| `backup/` | Cópia de cada apólice enviada |
| `entrada/` | PDFs à espera do modo FULL |
| `processados/` | PDFs já tratados pelo FULL |
| `capas/capa.pdf` | Capa junta a cada envio |

Configure caminhos absolutos no `.env` se preferir outro disco (ex.: `D:\envio\backup`).

### Tesseract OCR (PDFs só imagem)

1. Instale: [Tesseract para Windows](https://github.com/UB-Mannheim/tesseract/wiki)
2. No `backend/.env`:
   ```
   OCR_ENABLED=true
   TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
   ```
3. `Restart-Service EnvioApolices-API`
4. No painel, o menu mostra **OCR ativo** quando o motor está disponível.

### PDF protegido por senha (modo FULL)

Na mesma pasta do PDF em `entrada/<tipo>/`, crie um ficheiro com a senha numa linha:

- `documento.pdf.senha`, ou
- `documento.senha.txt`

Exemplo: `entrada/auto/55207_apolice.pdf` + `entrada/auto/55207_apolice.pdf.senha`

A senha **não** é guardada na base de dados.

### Após alterar `.env` ou dependências Python

```powershell
cd C:\envio-sistema\backend
.\.venv\Scripts\pip install -r requirements.txt
Restart-Service EnvioApolices-API
Restart-Service EnvioApolices-Front
```

## Usar o front em outra máquina da rede

**Cenário recomendado:** backend e frontend no **mesmo servidor**; os outros PCs só abrem o browser.

| O quê | URL nos outros PCs |
|-------|-------------------|
| Interface (Vue) | `http://IP-DO-SERVIDOR:5173` |
| API (teste) | `http://IP-DO-SERVIDOR:8000/docs` |

**Nunca** use `localhost` no browser de outro PC — `localhost` é sempre a máquina local.

### Erro comum: página abre mas não carrega / login falha

O Vite grava `VITE_API_URL` **no momento do build**. Se o build foi feito com
`http://localhost:8000`, o browser de outro PC tenta falar com a API **dele**, não do servidor.

**Correção no servidor** (PowerShell como administrador):

```powershell
cd C:\envio-sistema\installer   # ou a pasta installer do projeto
.\rebuild-frontend.ps1 -ServerIp 192.168.1.50
```

Substitua pelo IPv4 real (`ipconfig` no servidor). Depois, nos outros PCs: `http://192.168.1.50:5173`.

Confirme também:

1. Serviços a correr: `Get-Service EnvioApolices-*`
2. Firewall: portas **8000** e **5173** liberadas (o `install.ps1` cria as regras)
3. `frontend/.env`: `VITE_BACKEND_ACCESS_KEY` igual a `BACKEND_ACCESS_KEY` no `backend/.env`
4. Teste a API primeiro: `http://IP:8000/docs` — se isto não abrir, o problema é rede/firewall/serviço API

### Front instalado em cada PC cliente (opcional)

1. Copie a pasta `frontend/` para a máquina cliente
2. Edite `frontend/.env`:
   ```
   VITE_API_URL=http://IP-DO-SERVIDOR:8000
   VITE_BACKEND_ACCESS_KEY=<mesma chave do backend>
   ```
3. `npm install && npm run build && npm run preview -- --host 0.0.0.0`

## Desinstalação

```powershell
.\uninstall.ps1                 # remove tudo
.\uninstall.ps1 -KeepData       # remove serviços, mantém arquivos/backup
```
