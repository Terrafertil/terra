import { describe, expect, it } from 'vitest'
import {
  ANALISE_PDF_TIMEOUT_MS,
  ENVIO_EMAIL_TIMEOUT_MS,
  classeDeliveryStatus,
  destinatarioAtualDoCliente,
  destinatarioDoEnvio,
  destinatarioFoiAlterado,
  feedbackDoEnvio,
  mensagemErroApi,
  rotuloDeliveryStatus,
  rotuloStatusEnvio,
} from './envioFeedback'

describe('feedback de envio', () => {
  it('prioriza o destinatário registrado no envio sobre o cadastro atual do cliente', () => {
    expect(
      destinatarioDoEnvio({
        destinatario_email: 'usado@exemplo.com',
        cliente_email: 'atual@exemplo.com',
      })
    ).toBe('usado@exemplo.com')
    expect(destinatarioDoEnvio({ id: 7, cliente_id: 3 })).toBe(
      'não registrado (envio legado)'
    )
    const alterado = {
      destinatario_email: 'antigo@exemplo.com',
      cliente_email_atual: 'novo@exemplo.com',
    }
    expect(destinatarioAtualDoCliente(alterado)).toBe('novo@exemplo.com')
    expect(destinatarioFoiAlterado(alterado)).toBe(true)
  })

  it('não anuncia um novo envio quando a resposta foi deduplicada', () => {
    const feedback = feedbackDoEnvio({
      id: 42,
      status: 'enviado',
      delivery_status: 'accepted',
      destinatario_email: 'cliente@exemplo.com',
      deduplicado: true,
    })

    expect(feedback.tipo).toBe('aviso')
    expect(feedback.texto).toContain('Nenhum novo e-mail foi enviado')
    expect(feedback.texto).toContain('#42')
  })

  it('distingue aceite SMTP de entrega confirmada', () => {
    const accepted = feedbackDoEnvio({
      status: 'enviado',
      delivery_status: 'accepted',
      destinatario_email: 'cliente@exemplo.com',
    })
    const delivered = feedbackDoEnvio({
      status: 'enviado',
      delivery_status: 'delivered',
      destinatario_email: 'cliente@exemplo.com',
    })

    expect(accepted.texto).toContain('ainda não confirma a entrega')
    expect(delivered.texto).toBe('Entrega confirmada para cliente@exemplo.com.')
  })

  it('traduz e classifica estados de entrega', () => {
    expect(rotuloStatusEnvio('enviado')).toBe('Aceito pelo SMTP')
    expect(rotuloDeliveryStatus('hard_bounce')).toBe('Destinatário rejeitado')
    expect(rotuloDeliveryStatus('smtp_error')).toBe('SMTP recusou o envio')
    expect(classeDeliveryStatus('hard_bounce')).toBe('erro')
    expect(classeDeliveryStatus('deferred')).toBe('pendente')
    expect(classeDeliveryStatus('accepted')).toBe('pendente')
    expect(classeDeliveryStatus('delivered')).toBe('enviado')
  })

  it('trata adiamento como transitório, não como falha definitiva', () => {
    const feedback = feedbackDoEnvio({
      status: 'enviado',
      delivery_status: 'deferred',
      destinatario_email: 'cliente@exemplo.com',
    })

    expect(feedback.tipo).toBe('aviso')
    expect(feedback.texto).toContain('adiou temporariamente')
  })

  it('usa timeouts específicos maiores que o timeout HTTP padrão', () => {
    expect(ANALISE_PDF_TIMEOUT_MS).toBeGreaterThan(60_000)
    expect(ENVIO_EMAIL_TIMEOUT_MS).toBeGreaterThan(60_000)
  })

  it('interpreta erro HTTP estruturado e aponta o registro no Histórico', () => {
    const erro = {
      response: {
        data: {
          detail: {
            code: 'smtp_error',
            message: 'O SMTP recusou a mensagem.',
            envio_id: 91,
            pode_reenviar: true,
          },
        },
      },
    }

    expect(mensagemErroApi(erro, 'Falha no envio')).toBe(
      'O SMTP recusou a mensagem. O envio #91 ficou registrado no Histórico e pode ser reenviado por lá.'
    )
    expect(mensagemErroApi({ response: { data: { detail: 'Erro simples' } } }, 'Falha')).toBe(
      'Erro simples'
    )
  })
})
