const VARIAVEL_ASSUNTO = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}/g

export function renderizarAssunto(template, contexto = {}) {
  return String(template || '').replace(VARIAVEL_ASSUNTO, (token, dupla, simples) => {
    const chave = dupla || simples
    if (!Object.prototype.hasOwnProperty.call(contexto, chave)) return token
    const valor = contexto[chave]
    return valor === null || valor === undefined ? '' : String(valor)
  })
}

export function rotuloParcelamento(parcelamento) {
  const quantidade = Number(parcelamento)
  if (!quantidade) return ''
  return quantidade === 1 ? '1 vez' : `${quantidade} vezes`
}
