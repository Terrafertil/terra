import DOMPurify from 'dompurify'

export function sanitizeEmailHtml(html) {
  return DOMPurify.sanitize(html || '', {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'input', 'button'],
    // Assinatura na demonstração chega como data URI (cid: não funciona no browser).
    ADD_DATA_URI_TAGS: ['img'],
  })
}
