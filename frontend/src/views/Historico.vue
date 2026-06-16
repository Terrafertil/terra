<script setup>
import { ref, onMounted, reactive, computed } from 'vue'
import { api } from '../api'

const envios = ref([])
const filtros = reactive({ tipo: '', status: '', dias: 30 })
const erro = ref('')
const ok = ref('')
const reenviando = ref(false)
const reenviandoId = ref(null)

const errosCount = computed(() => envios.value.filter((e) => e.status === 'erro').length)

async function carregar() {
  erro.value = ''
  try {
    const params = {}
    if (filtros.tipo) params.tipo = filtros.tipo
    if (filtros.status) params.status = filtros.status
    if (filtros.dias) params.dias = filtros.dias
    const { data } = await api.get('/api/envios', { params })
    envios.value = data
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao carregar'
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
  if (!confirm(`Reenviar envio #${e.id} para ${e.cliente_email || 'cliente'}?`)) return
  reenviandoId.value = e.id
  erro.value = ''
  ok.value = ''
  try {
    const { data } = await api.post(`/api/envios/${e.id}/reenviar`)
    if (data.status === 'enviado') ok.value = `Envio #${e.id} reenviado com sucesso`
    else erro.value = data.erro_msg || 'Reenvio falhou'
    await carregar()
  } catch (ex) {
    erro.value = ex.response?.data?.detail || 'Falha no reenvio'
  } finally {
    reenviandoId.value = null
  }
}

async function reenviarErrosLote() {
  if (!errosCount.value) {
    erro.value = 'Não há envios com erro na lista atual'
    return
  }
  if (
    !confirm(
      `Reenviar todos os ${errosCount.value} envio(s) com erro dos últimos ${filtros.dias} dias?`
    )
  )
    return
  reenviando.value = true
  erro.value = ''
  ok.value = ''
  try {
    const { data } = await api.post('/api/envios/reenviar-erros', null, {
      params: { dias: filtros.dias || 30 },
    })
    ok.value = `Lote: ${data.sucesso} sucesso, ${data.falha} falha(s) de ${data.total}`
    await carregar()
  } catch (ex) {
    erro.value = ex.response?.data?.detail || 'Falha no reenvio em lote'
  } finally {
    reenviando.value = false
  }
}

onMounted(carregar)
</script>

<template>
  <div>
    <h2>Histórico de envios</h2>
    <p class="text-muted">
      Exporte para auditoria ou reenvie envios que falharam (usa o PDF guardado em backup).
    </p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok" class="alert alert-ok">{{ ok }}</div>

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
            :disabled="reenviando || !errosCount"
            @click="reenviarErrosLote"
          >
            {{ reenviando ? 'Reenviando…' : `Reenviar erros (${errosCount})` }}
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
            <th>E-mail</th>
            <th>Arquivo</th>
            <th>Apólice</th>
            <th>Status</th>
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
            <td style="font-size: 0.85rem">{{ e.cliente_email || '—' }}</td>
            <td>{{ e.nome_arquivo_original || '—' }}</td>
            <td>{{ e.numero_apolice || '—' }}</td>
            <td>
              <span class="badge" :class="e.status">{{ e.status }}</span>
              <div v-if="e.erro_msg" class="text-muted" style="font-size: 0.75rem">
                {{ e.erro_msg }}
              </div>
            </td>
            <td style="font-size: 0.85rem">{{ e.enviado_por || '—' }}</td>
            <td style="font-size: 0.85rem">{{ e.arquivo_colocado_por || '—' }}</td>
            <td>{{ new Date(e.criado_em).toLocaleString() }}</td>
            <td>
              <button
                v-if="e.status === 'erro' && e.caminho_backup"
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
