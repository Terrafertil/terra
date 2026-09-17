<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api } from '../api'

const capas = ref([])
const carregando = ref(false)
const enviando = ref(false)
const erro = ref('')
const ok = ref('')
const arquivo = ref(null)
const selecionada = ref(null)
const previewUrl = ref('')
const form = reactive({ nome: '', descricao: '' })

function fmtBytes(n) {
  if (!n) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

function revogarPreview() {
  if (previewUrl.value?.startsWith('blob:')) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

async function carregar() {
  carregando.value = true
  erro.value = ''
  try {
    const { data } = await api.get('/api/capas')
    capas.value = data
    if (selecionada.value) {
      selecionada.value = data.find((item) => item.id === selecionada.value.id) || null
    }
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao carregar os padrões de capa'
  } finally {
    carregando.value = false
  }
}

async function visualizar(capa) {
  revogarPreview()
  selecionada.value = capa
  try {
    const { data } = await api.get(`/api/capas/${capa.id}/arquivo`, { responseType: 'blob' })
    previewUrl.value = URL.createObjectURL(data)
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Não foi possível abrir a capa'
  }
}

function onArquivo(event) {
  arquivo.value = event.target.files?.[0] || null
  if (arquivo.value && !form.nome) form.nome = arquivo.value.name.replace(/\.pdf$/i, '')
}

async function criar() {
  erro.value = ''
  ok.value = ''
  if (!arquivo.value || !form.nome.trim()) {
    erro.value = 'Informe um nome e selecione o PDF da capa'
    return
  }
  const dados = new FormData()
  dados.append('arquivo', arquivo.value)
  dados.append('nome', form.nome.trim())
  if (form.descricao.trim()) dados.append('descricao', form.descricao.trim())
  enviando.value = true
  try {
    await api.post('/api/capas', dados, { headers: { 'Content-Type': 'multipart/form-data' } })
    ok.value = 'Padrão de capa adicionado à biblioteca.'
    form.nome = ''
    form.descricao = ''
    arquivo.value = null
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao guardar a capa'
  } finally {
    enviando.value = false
  }
}

async function alternar(capa) {
  erro.value = ''
  try {
    await api.put(`/api/capas/${capa.id}`, { ativo: !capa.ativo })
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Não foi possível alterar a capa'
  }
}

async function remover(capa) {
  if (!confirm(`Remover o padrão "${capa.nome}"?`)) return
  erro.value = ''
  try {
    await api.delete(`/api/capas/${capa.id}`)
    if (selecionada.value?.id === capa.id) {
      selecionada.value = null
      revogarPreview()
    }
    ok.value = 'Padrão removido.'
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Não foi possível remover; verifique se a capa está vinculada a um tipo.'
  }
}

onMounted(carregar)
onBeforeUnmount(revogarPreview)
</script>

<template>
  <div>
    <h2>Biblioteca de capas</h2>
    <p class="text-muted">
      Cadastre quantos padrões precisar. Em cada tipo ou envio manual, escolha a ordem das capas
      que ficam antes e depois da apólice; não existe mais uma capa global para todos os PDFs.
    </p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok" class="alert alert-ok">{{ ok }}</div>

    <div class="card">
      <h3>Novo padrão</h3>
      <div class="row">
        <div><label>Nome *</label><input v-model="form.nome" maxlength="120" /></div>
        <div><label>Descrição</label><input v-model="form.descricao" maxlength="255" /></div>
        <div><label>PDF *</label><input type="file" accept="application/pdf" @change="onArquivo" /></div>
      </div>
      <button type="button" class="btn btn-accent mt-2" :disabled="enviando" @click="criar">
        {{ enviando ? 'Guardando…' : 'Adicionar à biblioteca' }}
      </button>
    </div>

    <div class="capas-layout">
      <div class="card">
        <div class="flex items-center gap-2 mb-2">
          <h3 class="m-0">Padrões cadastrados</h3>
          <span class="spacer" />
          <button class="btn btn-ghost btn-sm" :disabled="carregando" @click="carregar">Atualizar</button>
        </div>
        <table v-if="capas.length" class="table">
          <thead><tr><th>Nome</th><th>PDF</th><th>Status</th><th></th></tr></thead>
          <tbody>
            <tr v-for="capa in capas" :key="capa.id">
              <td><strong>{{ capa.nome }}</strong><br /><small class="text-muted">{{ capa.descricao || 'Sem descrição' }}</small></td>
              <td>{{ capa.paginas }} pág. · {{ fmtBytes(capa.tamanho_bytes) }}</td>
              <td>{{ capa.ativo ? 'Ativa' : 'Inativa' }}</td>
              <td class="acoes">
                <button class="btn btn-ghost btn-sm" @click="visualizar(capa)">Visualizar</button>
                <button class="btn btn-ghost btn-sm" @click="alternar(capa)">{{ capa.ativo ? 'Desativar' : 'Ativar' }}</button>
                <button class="btn btn-danger btn-sm" @click="remover(capa)">Remover</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="!carregando" class="text-muted">Nenhum padrão cadastrado.</p>
      </div>

      <div v-if="selecionada" class="card preview-card">
        <h3>{{ selecionada.nome }}</h3>
        <iframe v-if="previewUrl" :src="previewUrl" title="Pré-visualização da capa" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.capas-layout { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(320px, 1fr); gap: 1rem; }
.acoes { text-align: right; white-space: nowrap; }
.preview-card iframe { width: 100%; min-height: 560px; border: 1px solid var(--border); border-radius: var(--radius); }
@media (max-width: 1050px) { .capas-layout { grid-template-columns: 1fr; } }
</style>
