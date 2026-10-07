const CARACTERES_INVALIDOS = /[<>:"/\\|?*\u0000-\u001f]/
const CARACTERES_INVALIDOS_GLOBAIS = /[<>:"/\\|?*\u0000-\u001f]/g

function limparParte(valor) {
  return String(valor || '')
    .normalize('NFKC')
    .replace(CARACTERES_INVALIDOS_GLOBAIS, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function montarNomeAnexoPdf(nomeCliente, tipoDocumento, numeroApolice) {
  const cliente = limparParte(nomeCliente)
  const documento = limparParte(tipoDocumento) || 'Documento'
  const numero = limparParte(numeroApolice)
  const prefixo = cliente ? `${cliente} - ` : ''
  const sufixo = numero ? ` ${numero}` : ''
  const nome = `${prefixo}${documento}${sufixo}`.slice(0, 176).trimEnd()
  return `${nome}.pdf`
}

export function normalizarExtensaoPdf(valor) {
  const nome = String(valor || '').normalize('NFKC').trim()
  if (!nome || nome.toLocaleLowerCase().endsWith('.pdf')) return nome
  return `${nome}.pdf`
}

export function erroNomeAnexoPdf(valor) {
  const nome = String(valor || '').normalize('NFKC').trim()
  if (!nome) return 'Informe o nome do arquivo'
  if (CARACTERES_INVALIDOS.test(nome)) {
    return 'O nome não pode conter < > : " / \\ | ? * nem caracteres de controle'
  }
  if (nome === '.' || nome === '..') return 'Informe um nome de arquivo válido'
  if (normalizarExtensaoPdf(nome).length > 180) {
    return 'Use no máximo 180 caracteres no nome do arquivo'
  }
  return ''
}
