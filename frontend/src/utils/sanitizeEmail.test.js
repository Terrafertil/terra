// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { sanitizeEmailHtml } from './sanitizeEmail'

describe('sanitizeEmailHtml', () => {
  it('remove scripts e manipuladores de evento', () => {
    const html = '<p>Seguro</p><img src="x" onerror="alert(1)"><script>alert(2)</script>'
    const result = sanitizeEmailHtml(html)

    expect(result).toContain('<p>Seguro</p>')
    expect(result).not.toContain('onerror')
    expect(result).not.toContain('<script')
  })

  it('mantÃ©m a formataÃ§Ã£o bÃ¡sica usada nos e-mails', () => {
    const result = sanitizeEmailHtml('<strong>OlÃ¡</strong><br><em>Cliente</em>')
    expect(result).toBe('<strong>OlÃ¡</strong><br><em>Cliente</em>')
  })
})
