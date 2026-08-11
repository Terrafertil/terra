import { describe, expect, it } from 'vitest'
import {
  assuntoVinculado,
  mesmoId,
  textoAssuntoVinculado,
  tiposVinculados,
} from './assuntoEmail'

const assuntos = [
  { id: 1, nome: 'Apólice Auto', assunto: 'Sua apólice {numero_apolice}' },
  { id: 2, nome: 'Renovação', assunto: 'Renovação disponível' },
]

describe('assuntos vinculados aos tipos de envio', () => {
  it('aceita ids vindos do select como string', () => {
    expect(mesmoId(1, '1')).toBe(true)
    expect(assuntoVinculado({ assunto_email_id: '1' }, assuntos)).toEqual(assuntos[0])
  })

  it('não associa assunto quando o tipo não possui vínculo', () => {
    expect(assuntoVinculado({ assunto_email_id: null }, assuntos)).toBeNull()
    expect(textoAssuntoVinculado({ assunto_email_id: null }, assuntos)).toBe('Padrão do sistema')
  })

  it('lista todos os tipos que usam o assunto', () => {
    const tipos = [
      { id: 10, codigo: 'auto', assunto_email_id: 1 },
      { id: 11, codigo: 'moto', assunto_email_id: '1' },
      { id: 12, codigo: 'residencial', assunto_email_id: 2 },
    ]
    expect(tiposVinculados(1, tipos).map((tipo) => tipo.codigo)).toEqual(['auto', 'moto'])
  })
})
