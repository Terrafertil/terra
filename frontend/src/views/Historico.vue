<script setup>
import { ref, onMounted, reactive, computed } from 'vue'
import { api } from '../api'
import {
  ENVIO_EMAIL_TIMEOUT_MS,
  classeDeliveryStatus,
  destinatarioAtualDoCliente,
  destinatarioDoEnvio,
  destinatarioFoiAlterado,
  feedbackDoEnvio,
  mensagemErroApi,
  rotuloDeliveryStatus,
  rotuloStatusEnvio,
} from '../utils/envioFeedback'

const envios = ref([])
const filtros = reactive({ tipo: '', status: '', dias: 30 })
const erro = ref('')
const ok = ref('')
const aviso = ref('')
const reenviando = ref(false)
const reenviandoId = ref(null)

const reenviaveisCount = computed(() => envios.value.filter((e) => e.pode_reenviar).length)

function parametrosAtuais() {
  const params = {}
  if (filtros.tipo) params.tipo = filtros.tipo
  if (filtros.status) params.status = filtros.status
  if (filtros.dias) params.dias = filtros.dias
  return params
}

async function buscarEnvios() {
  const { data } = await api.get('/api/envios', { params: parametrosAtuais() })
  envios.value = data
}

async function carregar() {
  erro.value = ''
  aviso.value = ''
  try {
    await buscarEnvios()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao carregar'
  }
}

async function atualizarListaAposAcao() {
  try {
    await buscarEnvios()
  } catch {
    aviso.value =
      'O resultado da operação acima é válido, mas não foi possível atualizar a lista. Use Filtrar para tentar novamente.'
  }
}

async function exportarCsv() {
  erro.value = ''
  try {
    const params = { dias: filtros.dias || 30 }
    if (filtros.tipo) params.tipo = filtros.tipo
    if (filtros.status) params.status = filtros.status
    const { data } = await api.get('/api/envios/export.csv', {
      params,
      responseType: 'blob',
    })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = `envios_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ok.value = 'CSV exportado'
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao exportar'
  }
}

async function reenviarUm(e) {
  const destinatarioAnterior = destinatarioDoEnvio(e)
  const destinatarioAtual = destinatarioAtualDoCliente(e)
  if (!destinatarioAtual) {
    erro.value = 'O cliente não possui um e-mail atual válido para o reenvio.'
    return
  }
  const pergunta = destinatarioFoiAlterado(e)
    ? `O envio #${e.id} usou ${destinatarioAnterior}. O reenvio será feito para o endereço atual ${destinatarioAtual}. Continuar?`
    : `Reenviar envio #${e.id} para ${destinatarioAtual}?`
  if (!confirm(pergunta)) return
  reenviandoId.value = e.id
  erro.value = ''
  ok.value = ''
  aviso.value = ''
  let recebeuResposta = false
  try {
    const { data } = await api.post(`/api/envios/${e.id}/reenviar`, null, {
      timeout: ENVIO_EMAIL_TIMEOUT_MS,
    })
    recebeuResposta = true
    const feedback = feedbackDoEnvio(data, {
      fallbackDestinatario: destinatarioAtual,
      reenvio: true,
    })
    if (feedback.tipo === 'erro') erro.value = feedback.texto
    else if (feedback.tipo === 'aviso') aviso.value = feedback.texto
    else ok.value = feedback.texto
  } catch (ex) {
    recebeuResposta = Boolean(ex.response?.data?.detail?.envio_id)
    erro.value =
      ex.code === 'ECONNABORTED'
        ? 'O servidor não confirmou o reenvio em 5 minutos. Atualize o Histórico antes de tentar novamente.'
        : mensagemErroApi(ex, 'Falha no reenvio')
  } finally {
    reenviandoId.value = null
  }
  if (recebeuResposta) await atualizarListaAposAcao()
}

async function reenviarErrosLote() {
  if (!reenviaveisCount.value) {
    erro.value = 'Não há envios liberados para reenvio na lista atual'
    return
  }
  if (
    !confirm(
      `Reenviar todos os ${reenviaveisCount.value} envio(s) com falha dos últimos ${filtros.dias} dias?`
    )
  )
    return
  reenviando.value = true
  erro.value = ''
  ok.value = ''
  aviso.value = ''
  let recebeuResposta = false
  try {
    const { data } = await api.post('/api/envios/reenviar-erros', null, {
      params: {
        dias: filtros.dias || 30,
        ...(filtros.tipo ? { tipo: filtros.tipo } : {}),
      },
      timeout: ENVIO_EMAIL_TIMEOUT_MS,
    })
    recebeuResposta = true
    const resumo =
      `Lote concluído: o SMTP aceitou ${data.sucesso} reenvio(s) e ${data.falha} falharam, de ${data.total}. ` +
      'Aceite SMTP ainda não confirma a entrega.'
    if (data.falha === 0) ok.value = resumo
    else if (data.sucesso > 0) aviso.value = resumo
    else erro.value = resumo
  } catch (ex) {
    erro.value =
      ex.code === 'ECONNABORTED'
        ? 'O servidor não confirmou o lote em 5 minutos. Atualize o Histórico antes de repetir a operação.'
        : mensagemErroApi(ex, 'Falha no reenvio em lote')
  } finally {
    reenviando.value = false
  }
  if (recebeuResposta) await atualizarListaAposAcao()
}

onMounted(carregar)
</script>

<template>
  <div>
    <h2>Histórico de envios</h2>
    <p class="text-muted">
      Exporte para auditoria ou reenvie itens que o servidor marcou como recuperáveis (usa o PDF guardado em backup).
    </p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok" class="alert alert-ok">{{ ok }}</div>
    <div v-if="aviso" class="alert alert-warn">{{ aviso }}</div>

    <div class="card">
      <div class="row">
        <div>
          <label>Tipo</label>
          <select v-model="filtros.tipo">
            <option value="">Todos</option>
            <option value="FULL">FULL</option>
            <option value="MANUAL">MANUAL</option>
            <option value="AVULSO">AVULSO (legado)</option>
          </select>
        </div>
        <div>
          <label>Status</label>
          <select v-model="filtros.status">
            <option value="">Todos</option>
            <option value="enviado">Enviado</option>
            <option value="erro">Erro</option>
            <option value="pendente">Pendente</option>
          </select>
        </div>
        <div>
          <label>Últimos N dias</label>
          <input type="number" min="1" v-model.number="filtros.dias" />
        </div>
        <div style="display: flex; align-items: flex-end; gap: 0.5rem; flex-wrap: wrap">
          <button class="btn btn-primary" @click="carregar">Filtrar</button>
          <button class="btn btn-ghost" type="button" @click="exportarCsv">Exportar CSV</button>
          <button
            class="btn btn-accent"
            type="button"
            :disabled="reenviando || !reenviaveisCount"
            @click="reenviarErrosLote"
          >
            {{ reenviando ? 'Reenviando…' : `Reenviar falhas (${reenviaveisCount})` }}
          </button>
        </div>
      </div>
    </div>

    <div class="card">
      <table class="table" v-if="envios.length">
        <thead>
          <tr>
            <th>ID</th>
            <th>Tipo</th>
            <th>Cliente</th>
            <th>Destinatário do envio</th>
            <th>Anexos enviados</th>
            <th>Apólice</th>
            <th>Envio SMTP</th>
            <th>Entrega</th>
            <th>Envio por</th>
            <th>Arquivo por</th>
            <th>Criado</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in envios" :key="e.id">
            <td>{{ e.id }}</td>
            <td><span class="badge" :class="e.tipo_envio">{{ e.tipo_envio }}</span></td>
            <td>{{ e.cliente_nome || `#${e.cliente_id}` }}</td>
            <td style="font-size: 0.85rem">
              {{ destinatarioDoEnvio(e) }}
              <div v-if="destinatarioFoiAlterado(e)" class="text-muted" style="font-size: 0.75rem">
                Atual: {{ destinatarioAtualDoCliente(e) }}
              </div>
            </td>
            <td style="font-size: 0.85rem">
              <strong>{{ e.nome_arquivo_final || e.nome_arquivo_original || '—' }}</strong>
              <div v-if="e.nome_boleto">{{ e.nome_boleto }}</div>
              <div
                v-if="e.nome_arquivo_original && e.nome_arquivo_original !== e.nome_arquivo_final"
                class="text-muted"
                style="font-size: 0.75rem"
              >
                Original: {{ e.nome_arquivo_original }}
              </div>
            </td>
            <td>{{ e.numero_apolice || '—' }}</td>
            <td>
              <span class="badge" :class="e.status">{{ rotuloStatusEnvio(e.status) }}</span>
              <div v-if="e.erro_msg" class="text-muted" style="font-size: 0.75rem">
                {{ e.erro_msg }}
              </div>
            </td>
            <td>
              <span class="badge" :class="classeDeliveryStatus(e.delivery_status)">
                {{ rotuloDeliveryStatus(e.delivery_status) }}
              </span>
              <div v-if="e.delivery_updated_at" class="text-muted" style="font-size: 0.75rem">
                {{ new Date(e.delivery_updated_at).toLocaleString() }}
              </div>
            </td>
            <td style="font-size: 0.85rem">{{ e.enviado_por || '—' }}</td>
            <td style="font-size: 0.85rem">{{ e.arquivo_colocado_por || '—' }}</td>
            <td>{{ new Date(e.criado_em).toLocaleString() }}</td>
            <td>
              <button
                v-if="e.pode_reenviar"
                class="btn btn-sm btn-ghost"
                :disabled="reenviandoId === e.id"
                @click="reenviarUm(e)"
              >
                {{ reenviandoId === e.id ? '…' : 'Reenviar' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-muted">Nenhum envio encontrado.</p>
    </div>
  </div>
</template>
