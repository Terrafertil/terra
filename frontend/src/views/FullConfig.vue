<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import draggable from 'vuedraggable'

const status = ref(null)
const tipos = ref([])
const assinaturas = ref([])
const erro = ref('')
const ok = ref('')
const salvando = ref(false)
const horaExec = ref('08:00')
const lote = ref(5)
const intervaloLote = ref(5)
const rescanHoras = ref(1)
const modoAtivo = ref(true)
const assinaturaId = ref(null)

// Drag & drop: esquerda = fora da fila; direita = ordem do FULL (refs para o vuedraggable)
const disponiveis = ref([])
const fila = ref([])

async function carregar() {
  erro.value = ''
  try {
    const [s, t, a] = await Promise.all([
      api.get('/api/status'),
      api.get('/api/tipos-envio'),
      api.get('/api/assinaturas', { params: { ativo: true } }),
    ])
    status.value = s.data
    tipos.value = t.data
    assinaturas.value = a.data
    horaExec.value = s.data.full_scan_exec_time ?? '08:00'
    lote.value = s.data.full_lote_size ?? 5
    intervaloLote.value = s.data.full_intervalo_lote_min ?? 5
    rescanHoras.value = s.data.full_rescan_horas ?? 1
    modoAtivo.value = !!s.data.full_modo_ativo
    assinaturaId.value = s.data.full_assinatura_id ?? null
    disponiveis.value = tipos.value
      .filter((x) => !x.na_fila_full)
      .sort((x, y) => x.nome.localeCompare(y.nome))
    fila.value = tipos.value
      .filter((x) => x.na_fila_full)
      .sort((x, y) => x.ordem - y.ordem)
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao carregar configuração'
  }
}

async function salvarFull(payload) {
  salvando.value = true; erro.value = ''
  try {
    const { data } = await api.patch('/api/settings/full', payload)
    status.value = data
    ok.value = 'Configuração salva.'
    setTimeout(() => (ok.value = ''), 2500)
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao salvar'
  } finally {
    salvando.value = false
  }
}

async function salvarParametros() {
  await salvarFull({
    full_lote_size: Number(lote.value),
    full_intervalo_lote_min: Number(intervaloLote.value),
    full_rescan_horas: Number(rescanHoras.value),
    full_modo_ativo: modoAtivo.value,
  })
}

async function definirHora() {
  if (!/^\d{2}:\d{2}$/.test(horaExec.value || '')) {
    erro.value = 'Hora inválida (use HH:MM)'; return
  }
  await salvarFull({ full_scan_exec_time: horaExec.value })
}

async function definirAssinatura() {
  await salvarFull({ full_assinatura_id: assinaturaId.value || 0 })
}

// Drag & drop helpers
async function persistirOrdem() {
  // 1) Marca os "fora" como na_fila_full=false (caso tenham sido removidos da fila)
  // 2) Marca os "fila" como na_fila_full=true e envia ordem
  try {
    for (const t of tipos.value) {
      const naFila = fila.value.some((x) => x.codigo === t.codigo)
      if (t.na_fila_full !== naFila) {
        await api.put(`/api/tipos-envio/${t.id}`, { na_fila_full: naFila })
        t.na_fila_full = naFila
      }
    }
    const ordem = fila.value.map((t) => t.codigo)
    if (ordem.length) {
      await api.patch('/api/tipos-envio/ordem', { ordem })
    }
    await carregar()
    ok.value = 'Ordem atualizada.'
    setTimeout(() => (ok.value = ''), 2200)
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao atualizar ordem'
  }
}

async function moverParaFila(tipo) {
  if (!fila.value.find((t) => t.codigo === tipo.codigo)) {
    fila.value = [...fila.value, { ...tipo }]
    await persistirOrdem()
  }
}

async function tirarDaFila(idx) {
  fila.value.splice(idx, 1)
  await persistirOrdem()
}

onMounted(carregar)
</script>

<template>
  <div>
    <h2>Configuração do envio FULL</h2>
    <p class="text-muted">
      Defina a ordem em que os tipos de envio são processados, quantos PDFs são enviados por rajada e o intervalo entre rajadas.
      O watcher também pode re-varrer a pasta a cada N horas pra pegar PDFs novos adicionados depois do horário diário.
    </p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok"   class="alert alert-ok">{{ ok }}</div>

    <div class="grid-cards">
      <div class="card card-frases">
        <h3>Horário de execução do FULL</h3>
        <p class="text-muted" style="font-size:.9rem">A varredura começa neste horário, todo dia. Deixe vazio para modo contínuo (varre a cada 30s).</p>
        <label class="full-label">Hora (HH:MM)</label>
        <div class="full-time-row">
          <input v-model="horaExec" type="time" step="60" class="input-time" />
          <button class="btn btn-primary" :disabled="salvando" @click="definirHora">Definir hora</button>
        </div>
      </div>

      <div class="card card-frases">
        <h3>Assinatura padrão do FULL</h3>
        <p class="text-muted" style="font-size:.9rem">Assinatura usada automaticamente em todos os envios pelo modo FULL. Cadastre novas em <code>Assinaturas</code>.</p>
        <label class="full-label">Assinatura</label>
        <div class="full-time-row">
          <select v-model="assinaturaId">
            <option :value="null">— sem assinatura —</option>
            <option v-for="a in assinaturas" :key="a.id" :value="a.id">{{ a.nome }}{{ a.pessoa ? ' (' + a.pessoa + ')' : '' }}</option>
          </select>
          <button class="btn btn-primary" :disabled="salvando" @click="definirAssinatura">Definir assinatura</button>
        </div>
      </div>
    </div>

    <div class="card">
      <h3>Parâmetros</h3>
      <div class="row">
        <div>
          <label>Modo FULL</label>
          <select v-model="modoAtivo">
            <option :value="true">Ativo</option>
            <option :value="false">Pausado</option>
          </select>
        </div>
        <div>
          <label>Lote (envios por rajada)</label>
          <input type="number" min="1" max="200" v-model.number="lote" />
        </div>
        <div>
          <label>Intervalo entre lotes (min)</label>
          <input type="number" min="0" max="240" v-model.number="intervaloLote" />
        </div>
        <div>
          <label>Re-scan após o horário (horas, 0 = não)</label>
          <input type="number" min="0" max="72" v-model.number="rescanHoras" />
        </div>
      </div>
      <div class="mt-2">
        <button class="btn btn-accent" :disabled="salvando" @click="salvarParametros">Salvar parâmetros</button>
      </div>
      <p class="text-muted mt-2" style="font-size:.88rem">
        <strong>Como funciona:</strong> a varredura começa na <em>hora</em> marcada. Em cada tipo da fila (na ordem que você definiu) o
        watcher processa <strong>{{ lote }} envios</strong>, espera <strong>{{ intervaloLote }} min</strong>, manda mais um lote, até acabar
        os PDFs daquele tipo. Depois passa pro próximo tipo. Após a varredura, ele revisita a pasta a cada
        <strong>{{ rescanHoras }}h</strong> pra capturar PDFs novos adicionados no mesmo dia.
      </p>
    </div>

    <div class="card">
      <div class="full-dual-listas">
        <div>
          <h3>Tipos disponíveis</h3>
          <p class="text-muted" style="font-size:.88rem">Arraste para a fila à direita ou clique no botão "→".</p>
          <draggable
            v-model="disponiveis"
            :group="{ name: 'tipos', pull: 'clone', put: false }"
            item-key="codigo"
            :sort="false"
            class="lista-tipos"
            @change="persistirOrdem"
          >
            <template #item="{ element }">
              <div class="tipo-item">
                <span class="tipo-nome">{{ element.nome }}</span>
                <small class="text-muted">/{{ element.codigo }}</small>
                <button class="btn btn-ghost btn-sm tipo-acao" @click="moverParaFila(element)">→</button>
              </div>
            </template>
          </draggable>
        </div>
        <div>
          <h3>Fila de processamento ({{ fila.length }})</h3>
          <p class="text-muted" style="font-size:.88rem">Arraste para reordenar. O 1º é processado primeiro.</p>
          <draggable
            v-model="fila"
            :group="{ name: 'tipos' }"
            item-key="codigo"
            class="lista-tipos lista-fila"
            @change="persistirOrdem"
          >
            <template #item="{ element, index }">
              <div class="tipo-item tipo-item--fila">
                <span class="tipo-pos">{{ index + 1 }}.</span>
                <span class="tipo-nome">{{ element.nome }}</span>
                <small class="text-muted">/{{ element.codigo }}</small>
                <button class="btn btn-ghost btn-sm tipo-acao" @click="tirarDaFila(index)">×</button>
              </div>
            </template>
          </draggable>
          <p v-if="!fila.length" class="text-muted">Nenhum tipo na fila — o FULL não vai processar nada.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lista-tipos {
  min-height: 80px;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.6rem;
  background: var(--terra-50);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
}
.lista-fila { background: #f9f4f0; }
.tipo-item {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0.7rem;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: grab;
}
.tipo-item:active { cursor: grabbing; }
.tipo-item--fila { background: #fff8f1; }
.tipo-nome { font-weight: 600; color: var(--terra-800); }
.tipo-pos { color: var(--accent); font-weight: 700; min-width: 1.5rem; }
.tipo-acao { margin-left: auto; }
.full-dual-listas {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}
@media (max-width: 980px) {
  .full-dual-listas {
    grid-template-columns: 1fr;
  }
}
</style>
