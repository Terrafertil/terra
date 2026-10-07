import { describe, expect, it } from 'vitest'
import {
  erroNomeAnexoPdf,
  montarNomeAnexoPdf,
  normalizarExtensaoPdf,
} from './nomeArquivoPdf'

describe('nomes dos anexos PDF', () => {
  it('monta o padrão com cliente e número da apólice', () => {
    expect(montarNomeAnexoPdf('Maria da Silva', 'Apólice', '12345')).toBe(
      'Maria da Silva - Apólice 12345.pdf',
    )
    expect(montarNomeAnexoPdf('Maria da Silva', 'Boleto', '12345')).toBe(
      'Maria da Silva - Boleto 12345.pdf',
    )
  })

  it('limpa caracteres inválidos apenas no nome sugerido', () => {
    expect(montarNomeAnexoPdf('Empresa / Filial', 'Apólice', '12:34')).toBe(
      'Empresa Filial - Apólice 12 34.pdf',
    )
  })

  it('adiciona a extensão e rejeita nomes manuais inseguros', () => {
    expect(normalizarExtensaoPdf('Documento final')).toBe('Documento final.pdf')
    expect(normalizarExtensaoPdf('Documento.PDF')).toBe('Documento.PDF')
    expect(erroNomeAnexoPdf('../segredo.pdf')).toContain('não pode conter')
    expect(erroNomeAnexoPdf('Apolice final.pdf')).toBe('')
  })
})
