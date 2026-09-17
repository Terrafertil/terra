import { describe, expect, it } from 'vitest'
import { renderizarAssunto, rotuloParcelamento } from './templateEmail'

describe('variaveis do assunto', () => {
  it('renderiza sintaxe simples e a sintaxe do corpo', () => {
    expect(renderizarAssunto(
      'Proposta {numero_proposta} - {{ item_segurado }}',
      { numero_proposta: '42', item_segurado: 'Trator' },
    )).toBe('Proposta 42 - Trator')
  })

  it('mantem variavel desconhecida visivel', () => {
    expect(renderizarAssunto('{desconhecida}', {})).toBe('{desconhecida}')
  })

  it('formata a quantidade de parcelas', () => {
    expect(rotuloParcelamento(1)).toBe('1 vez')
    expect(rotuloParcelamento(12)).toBe('12 vezes')
  })
})
