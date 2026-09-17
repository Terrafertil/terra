import DOMPurify from 'dompurify'

export function sanitizeEmailHtml(html, { wholeDocument = false } = {}) {
  return DOMPurify.sanitize(html || '', {
    USE_PROFILES: { html: true },
    WHOLE_DOCUMENT: wholeDocument,
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'input', 'button'],
    // Assinatura na demonstração chega como data URI (cid: não funciona no browser).
    ADD_DATA_URI_TAGS: ['img'],
  })
}
