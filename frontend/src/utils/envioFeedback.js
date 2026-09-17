export const ANALISE_PDF_TIMEOUT_MS = 300_000
export const ENVIO_EMAIL_TIMEOUT_MS = 300_000

const DELIVERY_LABELS = {
  accepted: 'Aceito pelo SMTP',
  delivered: 'Entrega confirmada',
  deferred: 'Entrega adiada',
  retrying: 'Reenvio em andamento',
  smtp_error: 'SMTP recusou o envio',
  soft_bounce: 'Falha temporária',
  hard_bounce: 'Destinatário rejeitado',
  bounce: 'Destinatário rejeitado',
  blocked: 'Bloqueado pelo provedor',
  invalid: 'E-mail inválido',
  invalid_email: 'E-mail inválido',
  spam: 'Marcado como spam',
  unsubscribed: 'Destinatário descadastrado',
  error: 'Erro de entrega',
  opened: 'Aberto pelo destinatário',
  unique_opened: 'Aberto pelo destinatário',
  proxy_open: 'Abertura detectada',
  click: 'Link acessado',
}

const ENVIO_LABELS = {
  enviado: 'Aceito pelo SMTP',
  erro: 'Erro no envio',
  pendente: 'Pendente',
}

const DELIVERY_FAILURES = new Set([
  'smtp_error',
  'soft_bounce',
  'hard_bounce',
  'bounce',
  'blocked',
  'invalid',
  'invalid_email',
  'spam',
  'unsubscribed',
  'error',
])

export function destinatarioDoEnvio(envio, fallback = '') {
  return (
    envio?.destinatario_email ||
    envio?.cliente_email ||
    fallback ||
    (envio?.id ? 'não registrado (envio legado)' : 'destinatário não informado')
  )
}

export function destinatarioAtualDoCliente(envio) {
  if (Array.isArray(envio?.cliente_destinatarios_atuais)) {
    return envio.cliente_destinatarios_atuais.filter(Boolean).join(', ')
  }
  return String(envio?.cliente_email_atual || '').trim()
}

function conjuntoDestinatarios(valor) {
  const itens = Array.isArray(valor) ? valor : String(valor || '').split(/[;,]/)
  return [...new Set(itens.map((item) => String(item).trim().toLowerCase()).filter(Boolean))]
    .sort()
    .join(',')
}

export function destinatarioFoiAlterado(envio) {
  const snapshot = conjuntoDestinatarios(
    envio?.destinatarios || envio?.destinatario_email || envio?.cliente_email,
  )
  const atual = conjuntoDestinatarios(
    envio?.cliente_destinatarios_atuais || envio?.cliente_email_atual,
  )
  return Boolean(snapshot && atual && snapshot !== atual)
}

export function mensagemErroApi(erro, fallback) {
  const detail = erro?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (!detail || typeof detail !== 'object') return fallback

  const mensagem = detail.message || detail.detail || fallback
  if (!detail.envio_id) return mensagem

  const orientacao = detail.pode_reenviar
    ? `O envio #${detail.envio_id} ficou registrado no Histórico e pode ser reenviado por lá.`
    : `O envio #${detail.envio_id} ficou registrado no Histórico.`
  return `${mensagem} ${orientacao}`
}

export function rotuloDeliveryStatus(status) {
  const normalized = String(status || '').trim().toLowerCase()
  return DELIVERY_LABELS[normalized] || status || 'Sem confirmação'
}

export function rotuloStatusEnvio(status) {
  const normalized = String(status || '').trim().toLowerCase()
  return ENVIO_LABELS[normalized] || status || 'Desconhecido'
}

export function classeDeliveryStatus(status) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'delivered' || ['opened', 'unique_opened', 'proxy_open', 'click'].includes(normalized)) {
    return 'enviado'
  }
  if (DELIVERY_FAILURES.has(normalized)) return 'erro'
  return 'pendente'
}

export function feedbackDoEnvio(envio, { fallbackDestinatario = '', reenvio = false } = {}) {
  const destinatario = destinatarioDoEnvio(envio, fallbackDestinatario)
  const acao = reenvio ? 'reenvio' : 'envio'

  if (envio?.deduplicado) {
    return {
      tipo: 'aviso',
      texto:
        `Este arquivo já correspondia ao envio #${envio.id}. ` +
        `Nenhum novo e-mail foi enviado para ${destinatario} nesta tentativa.`,
    }
  }

  if (envio?.status !== 'enviado') {
    return {
      tipo: 'erro',
      texto: `O ${acao} não foi concluído: ${envio?.erro_msg || `status "${envio?.status || 'desconhecido'}"`}.`,
    }
  }

  const deliveryStatus = String(envio.delivery_status || '').toLowerCase()
  if (deliveryStatus === 'delivered') {
    return {
      tipo: 'sucesso',
      texto: `Entrega confirmada para ${destinatario}.`,
    }
  }

  if (DELIVERY_FAILURES.has(deliveryStatus)) {
    return {
      tipo: 'erro',
      texto: `${rotuloDeliveryStatus(deliveryStatus)} para ${destinatario}. Consulte os detalhes no Histórico.`,
    }
  }

  if (deliveryStatus === 'deferred') {
    return {
      tipo: 'aviso',
      texto:
        `A Brevo adiou temporariamente a entrega para ${destinatario}. ` +
        'Acompanhe o Histórico; isso ainda pode evoluir para entregue ou falha.',
    }
  }

  return {
    tipo: 'sucesso',
    texto:
      `O SMTP aceitou o ${acao} para ${destinatario}. ` +
      'Isso ainda não confirma a entrega; acompanhe o status no Histórico.',
  }
}
