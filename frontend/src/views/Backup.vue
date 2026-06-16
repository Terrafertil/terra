<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import BackupAcessoNegado from './BackupAcessoNegado.vue'

const auth = useAuthStore()
const pronto = ref(false)
const bloqueado = computed(
  () => pronto.value && auth.authEnabled && auth.token && !auth.podeAcessarBackup
)

const caminhoAtual = ref('')
const parentRel = ref(null)
const itens = ref([])
const carregando = ref(false)
const erro = ref('')
const selecionados = ref(new Set())

async function listar(relPath = '') {
  carregando.value = true
  erro.value = ''
  try {
    const { data } = await api.get('/api/backup/listar', {
      params: { caminho: relPath },
    })
    caminhoAtual.value = data.caminho_atual || ''
    parentRel.value = data.parent_relativo ?? null
    itens.value = data.itens || []
    selecionados.value = new Set()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao listar pasta'
  } finally {
    carregando.value = false
  }
}

function entrar(item) {
  if (!item.eh_pasta) return
  listar(item.caminho_relativo)
}

function voltar() {
  if (parentRel.value != null) listar(parentRel.value)
}

function fmtBytes(n) {
  if (!n) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

function fmtData(d) {
  return d ? new Date(d).toLocaleString() : '—'
}

function alternarSel(item) {
  if (item.eh_pasta) return
  const s = new Set(selecionados.value)
  const k = item.caminho_relativo
  if (s.has(k)) s.delete(k)
  else s.add(k)
  selecionados.value = s
}

async function baixarUm(item) {
  if (item.eh_pasta) return
  try {
    const res = await api.get('/api/backup/download', {
      params: { caminho: item.caminho_relativo },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = item.nome
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Falha no download'
  }
}

function qsZip(caminhos) {
  const p = new URLSearchParams()
  for (const c of caminhos) p.append('caminhos', c)
  return p.toString()
}

async function baixarSelecionados() {
  const arr = [...selecionados.value]
  if (!arr.length) {
    erro.value = 'Marque pelo menos um arquivo'
    return
  }
  erro.value = ''
  try {
    const q = qsZip(arr)
    const res = await api.get(`/api/backup/download-zip?${q}`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `backup_${Date.now()}.zip`
    a.click()
    URL.revokeObjectURL(url)
    selecionados.value = new Set()
  } catch (e) {
    erro.value = 'Falha ao gerar ZIP'
  }
}

onMounted(async () => {
  if (auth.authEnabled && auth.token) {
    await auth.carregarUsuario()
  }
  pronto.value = true
  if (!bloqueado.value) listar('')
})
</script>

<template>
  <BackupAcessoNegado v-if="bloqueado" />
  <div v-else-if="pronto">
    <h2>Backup</h2>
    <p class="text-muted">
      Navegue pelas pastas de backup como em um explorador de arquivos. Baixe um arquivo ou selecione vários
      para receber um ZIP.
    </p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>

    <div class="card backup-toolbar">
      <div class="breadcrumbs">
        <button
          v-if="parentRel != null"
          type="button"
          class="btn btn-ghost btn-sm"
          :disabled="carregando"
          @click="voltar"
        >
          ↑ Voltar
        </button>
        <code class="path-label">{{ caminhoAtual || '(raiz)' }}</code>
      </div>
      <button
        type="button"
        class="btn btn-accent btn-sm"
        :disabled="!selecionados.size"
        @click="baixarSelecionados"
      >
        Baixar selecionados (ZIP)
      </button>
    </div>

    <div class="card">
      <p v-if="carregando" class="text-muted m-0">Carregando…</p>
      <table v-else-if="itens.length" class="table backup-table">
        <thead>
          <tr>
            <th style="width: 2.5rem"></th>
            <th>Nome</th>
            <th>Tipo</th>
            <th>Tamanho</th>
            <th>Atualizado</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in itens"
            :key="item.caminho_relativo"
            :class="{ 'row-folder': item.eh_pasta, 'row-sel': !item.eh_pasta && selecionados.has(item.caminho_relativo) }"
            @click="item.eh_pasta ? entrar(item) : alternarSel(item)"
          >
            <td>
              <input
                v-if="!item.eh_pasta"
                type="checkbox"
                :checked="selecionados.has(item.caminho_relativo)"
                @click.stop
                @change="alternarSel(item)"
              />
            </td>
            <td>
              <span class="nome-item" :class="{ linkish: item.eh_pasta }">{{ item.nome }}</span>
            </td>
            <td>{{ item.eh_pasta ? 'Pasta' : 'Arquivo' }}</td>
            <td>{{ item.eh_pasta ? '—' : fmtBytes(item.tamanho_bytes) }}</td>
            <td>{{ fmtData(item.atualizado_em) }}</td>
            <td>
              <button
                v-if="!item.eh_pasta"
                type="button"
                class="btn btn-ghost btn-sm"
                @click.stop="baixarUm(item)"
              >
                Baixar
              </button>
              <button
                v-else
                type="button"
                class="btn btn-ghost btn-sm"
                @click.stop="entrar(item)"
              >
                Abrir
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-muted m-0">Pasta vazia.</p>
    </div>
  </div>
</template>

<style scoped>
.backup-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.path-label {
  font-size: 0.88rem;
  word-break: break-all;
}
.backup-table tbody tr {
  cursor: pointer;
}
.row-folder:hover {
  background: var(--terra-50, #faf6f3);
}
.row-sel {
  background: #fff8f1;
}
.nome-item.linkish {
  color: var(--accent, #c67b4a);
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
}
</style>
