<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { tiposVinculados } from '../utils/assuntoEmail'

const lista = ref([])
const tipos = ref([])
const carregando = ref(false)
const erro = ref('')
const ok = ref('')
const editandoId = ref(null)
const placeholders = ref([])
const assuntoRef = ref(null)

const form = reactive({
  nome: '',
  descricao: '',
  assunto: '',
  ativo: true,
})

const titulo = computed(() => (editandoId.value ? 'Editar assunto' : 'Novo assunto'))

function vazio() {
  return { nome: '', descricao: '', assunto: '', ativo: true }
}

function vinculados(row) {
  return tiposVinculados(row.id, tipos.value)
}

async function carregar() {
  carregando.value = true
  erro.value = ''
  try {
    const [assuntosResponse, tiposResponse, atalhosResponse] = await Promise.all([
      api.get('/api/assuntos-email'),
      api.get('/api/tipos-envio'),
      api.get('/api/corpos-email/atalhos'),
    ])
    lista.value = assuntosResponse.data
    tipos.value = tiposResponse.data
    placeholders.value = atalhosResponse.data?.placeholders || []
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao carregar assuntos'
  } finally {
    carregando.value = false
  }
}

function editar(row) {
  editandoId.value = row.id
  form.nome = row.nome
  form.descricao = row.descricao || ''
  form.assunto = row.assunto || ''
  form.ativo = row.ativo
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function cancelar() {
  editandoId.value = null
  Object.assign(form, vazio())
}

function inserirVariavel(chave) {
  const token = `{${chave}}`
  const el = assuntoRef.value
  const inicio = el?.selectionStart ?? form.assunto.length
  const fim = el?.selectionEnd ?? inicio
  form.assunto = form.assunto.slice(0, inicio) + token + form.assunto.slice(fim)
  nextTick(() => {
    el?.focus()
    el?.setSelectionRange(inicio + token.length, inicio + token.length)
  })
}

async function salvar() {
  erro.value = ''
  ok.value = ''
  if (!form.nome.trim() || !form.assunto.trim()) {
    erro.value = 'Nome e texto do assunto são obrigatórios'
    return
  }

  const payload = {
    nome: form.nome.trim(),
    descricao: form.descricao?.trim() || null,
    assunto: form.assunto.trim(),
    ativo: form.ativo,
  }

  try {
    if (editandoId.value) {
      await api.put(`/api/assuntos-email/${editandoId.value}`, payload)
      ok.value = 'Assunto atualizado. Os tipos vinculados usarão o novo texto nos próximos envios.'
    } else {
      await api.post('/api/assuntos-email', payload)
      ok.value = 'Assunto criado. Agora vincule-o a um tipo de envio.'
    }
    cancelar()
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao salvar assunto'
  }
}

async function remover(row) {
  const usados = vinculados(row)
  if (usados.length) {
    erro.value = `O assunto está vinculado a ${usados.length} tipo(s). Remova o vínculo em Tipos de Envio antes de excluí-lo.`
    return
  }
  if (!confirm(`Remover o assunto "${row.nome}"?`)) return
  try {
    await api.delete(`/api/assuntos-email/${row.id}`)
    ok.value = 'Assunto removido'
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao remover assunto'
  }
}

onMounted(carregar)
</script>

<template>
  <div>
    <h2>Assuntos de e-mail</h2>
    <p class="text-muted">
      Salve assuntos reutilizáveis e vincule cada um ao tipo correspondente em
      <RouterLink to="/tipos-envio">Tipos de Envio</RouterLink>. O modo FULL e o envio manual
      usam automaticamente o assunto ligado ao tipo escolhido.
    </p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok" class="alert alert-ok">{{ ok }}</div>

    <div class="card">
      <h3>{{ titulo }}</h3>
      <form @submit.prevent="salvar">
        <div class="row">
          <div>
            <label>Nome *</label>
            <input v-model="form.nome" maxlength="120" placeholder="Ex.: Apólice Auto" />
          </div>
          <div>
            <label>Texto do assunto *</label>
            <input
              ref="assuntoRef"
              v-model="form.assunto"
              maxlength="500"
              placeholder="Ex.: Sua apólice {numero_apolice}"
            />
            <small class="text-muted">
              Clique em uma variável abaixo para inseri-la automaticamente.
            </small>
          </div>
        </div>
        <div class="variaveis-assunto mt-2">
          <small class="text-muted">
            No assunto use <code>{variavel}</code>; no corpo use <code v-pre>{{ variavel }}</code>.
          </small>
          <div class="variaveis-botoes mt-2">
            <button
              v-for="item in placeholders"
              :key="item.chave"
              type="button"
              class="btn btn-ghost btn-sm"
              @click="inserirVariavel(item.chave)"
            >
              {{ item.label }} · <code>{{ '{' + item.chave + '}' }}</code>
            </button>
          </div>
        </div>
        <div class="mt-2">
          <label>Descrição</label>
          <input v-model="form.descricao" maxlength="255" placeholder="Uso interno da equipe" />
        </div>
        <div class="mt-2 flex gap-2 items-center">
          <label class="m-0"><input v-model="form.ativo" type="checkbox" /> Ativo</label>
        </div>
        <div class="flex gap-2 mt-2">
          <button type="submit" class="btn btn-accent">
            {{ editandoId ? 'Salvar' : 'Cadastrar' }}
          </button>
          <button v-if="editandoId" type="button" class="btn btn-ghost" @click="cancelar">
            Cancelar
          </button>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="flex gap-2 items-center mb-2">
        <h3 class="m-0">Assuntos salvos</h3>
        <span class="spacer"></span>
        <button class="btn btn-ghost btn-sm" :disabled="carregando" @click="carregar">
          Atualizar
        </button>
      </div>
      <p v-if="carregando" class="text-muted">Carregando…</p>
      <table v-else-if="lista.length" class="table">
        <thead>
          <tr>
            <th>Nome</th>
            <th>Assunto</th>
            <th>Tipos vinculados</th>
            <th>Ativo</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in lista" :key="row.id">
            <td>{{ row.nome }}</td>
            <td>{{ row.assunto }}</td>
            <td>
              <span v-if="vinculados(row).length">
                {{ vinculados(row).map((tipo) => tipo.nome).join(', ') }}
              </span>
              <span v-else class="text-muted">Nenhum</span>
            </td>
            <td>{{ row.ativo ? 'Sim' : 'Não' }}</td>
            <td>
              <button class="btn btn-ghost btn-sm" @click="editar(row)">Editar</button>
              <button class="btn btn-danger btn-sm" @click="remover(row)">Remover</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-muted">Nenhum assunto salvo.</p>
    </div>
  </div>
</template>

<style scoped>
.variaveis-botoes {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
</style>
