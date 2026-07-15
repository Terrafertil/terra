# Análise técnica e migração AWS SES → Brevo

Data da revisão: 15/07/2026

## Resultado executivo

O projeto não dependia de serviços AWS além do relay SMTP do Amazon SES. Não foram
encontrados SDK AWS, S3, SQS, SNS, Lambda ou infraestrutura como código. A migração foi
feita no único limite necessário: configuração e transporte de e-mail transacional.

O fluxo atual usa o relay `smtp-relay.brevo.com`, aceita as portas 587/2525 com STARTTLS
e 465 com TLS implícito. A mensagem continua sendo produzida localmente pelo backend,
incluindo HTML, imagem de assinatura inline e PDF da apólice.

## Arquitetura revisada

- Backend: FastAPI, SQLAlchemy e SQLite.
- Frontend: Vue 3, Pinia, Vue Router, Axios e Vite.
- Processamento: watcher do modo FULL, extração de dados de PDF/OCR, capa, backup e
  histórico de envio.
- Segurança: autenticação JWT, chave adicional de acesso ao backend, criptografia dos
  dados de clientes e modo SOC.
- Operação: Windows Server com serviços geridos pelo NSSM.

Fluxo de envio:

1. O PDF entra pelo watcher FULL ou pelo envio manual.
2. O backend extrai CPF/CNPJ e número da apólice, resolve o cliente e aplica a capa.
3. O HTML e a assinatura inline são renderizados.
4. A mensagem MIME com o PDF é enviada ao relay transacional da Brevo.
5. O backend guarda backup e o aceite inicial do relay no SQLite.
6. O webhook autenticado da Brevo atualiza entrega, abertura, clique, bounce, bloqueio
   ou erro no histórico.

## Alterações da migração

- Remoção das variáveis e aliases operacionais do AWS SES.
- Brevo definida como provedor padrão.
- Compatibilidade com `BREVO_SMTP_LOGIN`, `BREVO_SMTP_KEY`, `BREVO_SENDER_EMAIL` e
  `BREVO_SENDER_NAME`.
- Proteção contra `.env` legado: um host `*.amazonaws.com` é substituído pelo relay
  Brevo quando `USE_BREVO=true`.
- Validação de credenciais antes de abrir conexão de rede.
- Suporte correto a STARTTLS e TLS implícito.
- Validação da mensagem MIME contra o limite transacional configurável de 20 MB.
- Estado técnico `email_configured` disponível no endpoint `/api/status`.
- Documentação e instalador atualizados.

## Achados adicionais corrigidos

- Dependências npm vulneráveis foram atualizadas; a auditoria terminou sem alertas.
- FastAPI/Starlette foram atualizados e `python-jose`/`ecdsa` foi substituído por PyJWT
  para remover vulnerabilidades conhecidas mantendo tokens HS256 compatíveis.
- O instalador agora gera chaves e senhas aleatórias em instalações novas. A chave de
  acesso não é embutida no frontend: a autorização temporária usa cookie HttpOnly.
- Uploads são transmitidos em blocos, têm limite de tamanho e validação estrutural.
- O SQLite usa WAL e migrações Alembic; deploys usam lockfile com hashes e rollback.
- O painel e a API usam a mesma origem e o mesmo serviço Windows.
- O desinstalador voltou a ser compatível com Windows PowerShell 5.1 e bloqueia remoção
  recursiva da raiz de uma unidade.

## Dependências externas ainda necessárias

O código não pode criar nem adivinhar credenciais da conta Brevo. Antes do primeiro envio
real, é necessário:

1. Autenticar o domínio remetente (DKIM/DMARC) na Brevo.
2. Configurar um remetente transacional válido.
3. Gerar uma chave **SMTP** (não API key e não senha da conta).
4. Preencher `backend/.env` e reiniciar o backend.
5. Configurar o webhook transacional com Bearer em `/api/webhooks/brevo`.
6. Confirmar `email_configured: true` em `GET /api/status` com uma sessão autenticada.
7. Fazer um envio para uma caixa controlada e conferir também o log transacional da Brevo.

Referências oficiais:

- [Integração do relay SMTP](https://developers.brevo.com/docs/smtp-integration)
- [Configuração de e-mails transacionais por SMTP](https://help.brevo.com/hc/en-us/articles/7924908994450-Send-transactional-emails-using-Brevo-SMTP)
- [Autenticação do domínio](https://help.brevo.com/hc/en-us/articles/12163873383186-Authenticate-your-domain-with-Brevo-Brevo-code-DKIM-DMARC)
- [Limites de anexos transacionais](https://help.brevo.com/hc/en-us/articles/4402811730962-Add-an-attachment-to-a-transactional-email)
- [Payloads de webhooks transacionais](https://developers.brevo.com/docs/transactional-webhooks)
- [Autenticação Bearer de webhooks](https://developers.brevo.com/docs/secured-webhooks)

## Estado de entrega

O status `enviado` significa que o relay SMTP aceitou a mensagem. A confirmação posterior
é registrada separadamente em `delivery_status` pelo webhook transacional. Se o webhook
não for configurado na conta Brevo, o histórico continuará mostrando somente o aceite
SMTP, sem afirmar que a caixa do destinatário recebeu a mensagem.

## Validação executada

- Testes unitários de configuração, migração de host SES, STARTTLS, PDF anexo, limite de
  mensagem e JWT.
- Compilação Python e verificação de dependências.
- Build de produção do frontend.
- Auditorias `pip-audit` e `npm audit` sem vulnerabilidades conhecidas.
- Análise sintática dos scripts PowerShell.
- Smoke test real da API, OpenAPI, frontend e conectividade TCP com
  `smtp-relay.brevo.com:587`.
