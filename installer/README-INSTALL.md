# Instalação no Windows Server

## Pré-requisitos

- Windows Server 2019/2022 ou Windows 10/11.
- PowerShell aberto como administrador.
- Internet para instalar Python, Node.js e NSSM.
- IP fixo ou nome DNS reservado para o servidor.

## Instalar ou atualizar

Na pasta `installer/`:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\install.ps1 -InstallDir "C:\envio-sistema" -ServicePort 8000 -ServerIp 192.168.1.50
```

Opções úteis:

```powershell
.\install.ps1 -SkipFrontend    # instala somente a API
.\install.ps1 -SkipServices    # prepara arquivos sem registrar/iniciar serviço
```

O instalador:

1. valida Python 3.11+ e Node.js 20+;
2. valida assinatura digital dos instaladores baixados diretamente;
3. baixa o NSSM e valida seu SHA-256 antes de extrair;
4. copia apenas fontes e manifestos permitidos;
5. preserva `.env`, banco, salt, PDFs, backups e logs existentes;
6. gera segredos e senhas fortes somente em instalação nova;
7. instala dependências Python pelo `requirements.lock` com hashes;
8. executa `npm ci` e compila o frontend;
9. registra somente `EnvioApolices-API`, que também serve o painel;
10. abre somente a porta configurada, executa health check e restaura o código anterior
    se o deploy falhar.

Não há serviço `EnvioApolices-Front` nem porta 5173 em produção. O parâmetro legado
`-FrontPort` é aceito apenas para compatibilidade e não abre uma porta.

## Primeiro acesso

O instalador mostra as senhas iniciais aleatórias de `admin` e `admindiretor` uma única
vez. Guarde-as em um cofre e troque-as no primeiro login.

Edite:

```text
C:\envio-sistema\backend\.env
```

Configure no mínimo:

- `BREVO_SMTP_LOGIN`, `BREVO_SMTP_KEY` e `BREVO_SENDER_*`;
- `BREVO_WEBHOOK_TOKEN` no sistema e na autenticação Bearer do webhook Brevo;
- `FULL_WATCH_FOLDER`, de preferência em disco persistente;
- `CORS_ORIGINS`, com a URL real do painel;
- `AUTH_COOKIE_SECURE=true` assim que o endereço estiver sob HTTPS.

Depois:

```powershell
Restart-Service EnvioApolices-API
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Nos outros computadores, abra `http://192.168.1.50:8000`. Nunca use `localhost` em
uma máquina cliente.

## Serviço e logs

```powershell
Get-Service EnvioApolices-API
Restart-Service EnvioApolices-API
Stop-Service EnvioApolices-API
Start-Service EnvioApolices-API
```

Logs:

```text
C:\envio-sistema\backend\logs\api.out.log
C:\envio-sistema\backend\logs\api.err.log
```

Swagger fica desativado por padrão. Para diagnóstico em ambiente restrito, defina
`DOCS_ENABLED=true`, reinicie o serviço e use `/docs`; desative novamente depois.

## HTTPS

O instalador não pode emitir um certificado sem domínio e controle DNS. Em produção,
publique o serviço atrás de IIS, Caddy, nginx ou outro proxy reverso com certificado
válido. Encaminhe para `http://127.0.0.1:8000` e configure:

```dotenv
AUTH_COOKIE_SECURE=true
CORS_ORIGINS=https://painel.seu-dominio.com.br
```

Restrinja a regra de firewall da porta 8000 à rede/proxy quando o painel for exposto.
HSTS é enviado automaticamente nas requisições HTTPS.

## Brevo e confirmação de entrega

Use uma chave SMTP, não a API key da conta. Cadastre o webhook transacional:

```text
https://painel.seu-dominio.com.br/api/webhooks/brevo
Authorization: Bearer <BREVO_WEBHOOK_TOKEN>
```

Selecione os eventos de entrega, abertura, clique, soft/hard bounce, bloqueio e erro.
O histórico correlaciona os eventos pelo identificador da mensagem e pelo campo de
rastreamento enviado pelo sistema.

## Dados persistentes e backup externo

Inclua em backup externo/imutável:

| Caminho relativo a `backend/` | Conteúdo |
|---|---|
| `.env` | segredos e configurações |
| `data/envio.db` | clientes, histórico e configurações |
| `data/.crypto_salt` | salt necessário para decifrar dados |
| `backup/` | apólices e boletos enviados |
| `entrada/` | fila FULL |
| `processados/` | arquivos tratados |
| `capas/` e `assinaturas/` | conteúdo de e-mail |

Não armazene a única cópia das chaves no mesmo servidor do banco. A retenção automática
vem desativada; habilite apenas depois de definir a política legal e validar o backup.

## Rotação da chave de dados

Pare a API antes de executar:

```powershell
Stop-Service EnvioApolices-API
cd C:\envio-sistema\backend
.\.venv\Scripts\python scripts\rotate_encryption_key.py --confirm-api-offline
Start-Service EnvioApolices-API
```

O script cria backup nativo do SQLite e cópias de `.env`/salt antes da recifragem. Não
execute durante modo SOC.

## OCR e PDF protegido

Instale Tesseract e configure, se necessário:

```dotenv
OCR_ENABLED=true
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Para PDF protegido no FULL, coloque ao lado dele `documento.pdf.senha` ou
`documento.senha.txt`, com a senha em uma linha. Essa senha não é salva no banco.

## Atualizar dependências ou reconstruir o painel

Preferencialmente rode novamente `install.ps1`; ele mantém dados e possui rollback.
Para reconstruir somente o frontend:

```powershell
.\rebuild-frontend.ps1 -InstallDir "C:\envio-sistema" -ServerIp 192.168.1.50
```

O build usa mesma origem e não contém `BACKEND_ACCESS_KEY`.

## Desinstalação

Por segurança, a desinstalação padrão remove serviço e firewall, mas preserva a pasta:

```powershell
.\uninstall.ps1
```

Para apagar também banco, documentos, backups e segredos, confirme uma cópia externa e
use explicitamente:

```powershell
.\uninstall.ps1 -RemoveData
```
