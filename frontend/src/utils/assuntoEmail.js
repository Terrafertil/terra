export function mesmoId(a, b) {
  if (a === null || a === undefined || b === null || b === undefined) return false
  return String(a) === String(b)
}

export function assuntoVinculado(tipo, assuntos = []) {
  if (!tipo?.assunto_email_id) return null
  return assuntos.find((assunto) => mesmoId(assunto.id, tipo.assunto_email_id)) || null
}

export function tiposVinculados(assuntoId, tipos = []) {
  return tipos.filter((tipo) => mesmoId(tipo.assunto_email_id, assuntoId))
}

export function textoAssuntoVinculado(tipo, assuntos = [], fallback = 'Padrão do sistema') {
  const assunto = assuntoVinculado(tipo, assuntos)
  return assunto?.assunto?.trim() || fallback
}
