<script setup>
import { ref, onMounted, computed } from 'vue'
import { api, API_BASE_URL } from '../api'

const info = ref(null)
const erro = ref('')
const ok = ref('')
const carregando = ref(false)
const enviando = ref(false)
const arquivo = ref(null)
const previewUrl = ref('')

const urlVisualizar = computed(() => {
  if (!info.value?.existe) return ''
  return `${API_BASE_URL}/api/capa/visualizar?_=${Date.now()}`
})

function fmtBytes(n) {
  if (!n) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

function fmtData(d) {
  return d ? new Date(d).toLocaleString() : '—'
}

async function carregar() {
  carregando.value = true; erro.value = ''
  try {
    const { data } = await api.get('/api/capa')
    info.value = data
    if (data.existe) previewUrl.value = urlVisualizar.value
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao carregar info da capa'
  } finally {
    carregando.value = false
  }
}

function onArquivo(e) {
  arquivo.value = e.target.files[0] || null
}

async function enviar() {
  erro.value = ''; ok.value = ''
  if (!arquivo.value) { erro.value = 'Selecione um PDF'; return }
  const fd = new FormData()
  fd.append('arquivo', arquivo.value)
  enviando.value = true
  try {
    const { data } = await api.post('/api/capa', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    info.value = data
    ok.value = `Capa atualizada como ${data.nome}.`
    arquivo.value = null
    previewUrl.value = `${API_BASE_URL}/api/capa/visualizar?_=${Date.now()}`
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro no upload'
  } finally {
    enviando.value = false
  }
}

async function remover() {
  if (!confirm('Remover a capa atual?')) return
  erro.value = ''; ok.value = ''
  try {
    await api.delete('/api/capa')
    ok.value = 'Capa removida.'
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao remover'
  }
}

onMounted(carregar)
</script>

<template>
  <div>
    <h2>Capa</h2>
    <p class="text-muted">
      A capa é um PDF que vai antes da apólice em todos os envios. Faça o upload de qualquer PDF —
      o sistema renomeia automaticamente para <code>{{ info?.nome || 'capa.pdf' }}</code> conforme o <code>.env</code>.
    </p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok"   class="alert alert-ok">{{ ok }}</div>

    <div class="card">
      <h3>Capa atual</h3>
      <div v-if="carregando" class="text-muted">Carregando...</div>
      <div v-else-if="info && info.existe">
        <p><strong>Nome:</strong> {{ info.nome }}</p>
        <p><strong>Caminho:</strong> <code>{{ info.caminho }}</code></p>
        <p><strong>Tamanho:</strong> {{ fmtBytes(info.tamanho_bytes) }} · <strong>Páginas:</strong> {{ info.paginas }}</p>
        <p><strong>Atualizada em:</strong> {{ fmtData(info.atualizado_em) }}</p>
        <div class="flex gap-2 mt-2">
          <a class="btn btn-ghost btn-sm" :href="urlVisualizar" target="_blank" rel="noopener">Visualizar PDF</a>
          <button class="btn btn-danger btn-sm" @click="remover">Remover capa</button>
        </div>
        <iframe
          v-if="previewUrl"
          :src="previewUrl"
          class="capa-preview mt-4"
          title="Pré-visualização da capa"
        ></iframe>
      </div>
      <p v-else class="text-muted">Nenhuma capa configurada no momento.</p>
    </div>

    <div class="card">
      <h3>Substituir capa</h3>
      <p class="text-muted">Qualquer PDF serve — o sistema renomeia para <code>{{ info?.nome || 'capa.pdf' }}</code>.</p>
      <input type="file" accept="application/pdf" @change="onArquivo" />
      <div class="mt-2">
        <button class="btn btn-accent" :disabled="enviando" @click="enviar">
          {{ enviando ? 'Enviando...' : 'Substituir capa' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.capa-preview {
  width: 100%;
  height: 500px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
}
</style>
