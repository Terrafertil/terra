<script setup>
import { ref, onMounted, reactive, computed } from 'vue'
import { api, API_BASE_URL } from '../api'

const lista = ref([])
const carregando = ref(false)
const erro = ref('')
const ok = ref('')

const form = reactive({
  nome: '',
  pessoa: '',
  cargo: '',
  email_contato: '',
  telefone: '',
  ativo: true,
})
const editandoId = ref(null)
const arquivo = ref(null)

const titulo = computed(() => (editandoId.value ? 'Editar assinatura' : 'Nova assinatura'))

function urlImagem(id) {
  return `${API_BASE_URL}/api/assinaturas/${id}/imagem`
}

function vazio() {
  return {
    nome: '',
    pessoa: '',
    cargo: '',
    email_contato: '',
    telefone: '',
    ativo: true,
  }
}

async function carregar() {
  carregando.value = true
  erro.value = ''
  try {
    const { data } = await api.get('/api/assinaturas')
    lista.value = data
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao carregar assinaturas'
  } finally {
    carregando.value = false
  }
}

function onArquivo(e) {
  arquivo.value = e.target.files[0] || null
}

function editar(row) {
  editandoId.value = row.id
  form.nome = row.nome
  form.pessoa = row.pessoa || ''
  form.cargo = row.cargo || ''
  form.email_contato = row.email_contato || ''
  form.telefone = row.telefone || ''
  form.ativo = row.ativo
  arquivo.value = null
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function cancelar() {
  editandoId.value = null
  arquivo.value = null
  Object.assign(form, vazio())
}

function montarFormData() {
  const fd = new FormData()
  fd.append('nome', form.nome.trim())
  if (form.pessoa) fd.append('pessoa', form.pessoa)
  if (form.cargo) fd.append('cargo', form.cargo)
  if (form.email_contato) fd.append('email_contato', form.email_contato)
  if (form.telefone) fd.append('telefone', form.telefone)
  if (arquivo.value) fd.append('arquivo', arquivo.value)
  return fd
}

async function salvar() {
  erro.value = ''
  ok.value = ''
  if (!form.nome.trim()) {
    erro.value = 'Nome identificador é obrigatório'
    return
  }
  if (!editandoId.value && !arquivo.value) {
    erro.value = 'Envie a imagem da assinatura (PNG, JPG, …)'
    return
  }
  try {
    if (editandoId.value) {
      const fd = new FormData()
      if (form.nome.trim()) fd.append('nome', form.nome.trim())
      fd.append('pessoa', form.pessoa || '')
      fd.append('cargo', form.cargo || '')
      fd.append('email_contato', form.email_contato || '')
      fd.append('telefone', form.telefone || '')
      fd.append('ativo', form.ativo ? 'true' : 'false')
      if (arquivo.value) fd.append('arquivo', arquivo.value)
      await api.put(`/api/assinaturas/${editandoId.value}`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      ok.value = 'Assinatura atualizada'
    } else {
      await api.post('/api/assinaturas', montarFormData(), {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      ok.value = 'Assinatura criada. Ela poderá ser usada no envio manual e no FULL.'
    }
    cancelar()
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao salvar'
  }
}

async function remover(row) {
  if (!confirm(`Remover a assinatura "${row.nome}"?`)) return
  try {
    await api.delete(`/api/assinaturas/${row.id}`)
    ok.value = 'Removida'
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao remover'
  }
}

onMounted(carregar)
</script>

<template>
  <div>
    <h2>Assinaturas</h2>
    <p class="text-muted">
      Cadastre fotos de assinatura com os dados de quem assina. A imagem é embutida no corpo do e-mail (inline)
      quando você escolhe esta assinatura no envio manual ou na configuração do FULL.
    </p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok"   class="alert alert-ok">{{ ok }}</div>

    <div class="card">
      <h3>{{ titulo }}</h3>
      <form @submit.prevent="salvar">
        <div class="row">
          <div><label>Nome (identificador) *</label><input v-model="form.nome" maxlength="120" /></div>
          <div><label>Pessoa / Responsável</label><input v-model="form.pessoa" maxlength="120" /></div>
          <div><label>Cargo</label><input v-model="form.cargo" maxlength="120" /></div>
          <div><label>E-mail de contato</label><input v-model="form.email_contato" type="email" maxlength="150" /></div>
          <div><label>Telefone</label><input v-model="form.telefone" maxlength="40" /></div>
        </div>
        <div class="mt-2">
          <label>Imagem da assinatura {{ editandoId ? '(opcional — mantém a atual se vazio)' : '*' }}</label>
          <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="onArquivo" />
        </div>
        <div class="mt-2">
          <label class="m-0"><input type="checkbox" v-model="form.ativo" /> Ativo</label>
        </div>
        <div class="flex gap-2 mt-2">
          <button type="submit" class="btn btn-accent">{{ editandoId ? 'Salvar' : 'Cadastrar' }}</button>
          <button v-if="editandoId" type="button" class="btn btn-ghost" @click="cancelar">Cancelar</button>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="flex gap-2 items-center mb-2">
        <h3 class="m-0">Cadastradas</h3>
        <span class="spacer"></span>
        <button class="btn btn-ghost btn-sm" :disabled="carregando" @click="carregar">Atualizar</button>
      </div>
      <div v-if="lista.length" class="grid-assinaturas">
        <div v-for="a in lista" :key="a.id" class="assin-card">
          <div class="assin-thumb">
            <img v-if="a.arquivo" :src="urlImagem(a.id)" :alt="a.nome" />
            <span v-else class="text-muted">Sem imagem</span>
          </div>
          <div>
            <strong>{{ a.nome }}</strong>
            <div class="text-muted small">{{ a.pessoa || '—' }} · {{ a.cargo || '—' }}</div>
            <div class="small">{{ a.email_contato || '' }} {{ a.telefone || '' }}</div>
            <div class="mt-1 flex gap-1">
              <button class="btn btn-ghost btn-sm" @click="editar(a)">Editar</button>
              <button class="btn btn-danger btn-sm" @click="remover(a)">Remover</button>
            </div>
          </div>
        </div>
      </div>
      <p v-else class="text-muted">Nenhuma assinatura.</p>
    </div>
  </div>
</template>

<style scoped>
.grid-assinaturas {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.assin-card {
  display: flex;
  gap: 1rem;
  padding: 0.75rem;
  border: 1px solid var(--border, #e0d8d0);
  border-radius: var(--radius, 8px);
  background: #fff;
}
.assin-thumb {
  width: 160px;
  min-height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--terra-50, #faf6f3);
  border-radius: var(--radius, 8px);
  overflow: hidden;
}
.assin-thumb img {
  max-width: 100%;
  max-height: 120px;
  object-fit: contain;
}
.small { font-size: 0.88rem; }
</style>
