<script setup>
import { ref, onMounted, reactive, computed } from 'vue'
import { api } from '../api'

const tipos = ref([])
const corpos = ref([])
const carregando = ref(false)
const erro = ref('')
const ok = ref('')

const form = reactive({
  codigo: '',
  nome: '',
  descricao: '',
  na_fila_full: true,
  corpo_email_id: null,
  ativo: true,
})
const editandoId = ref(null)

const titulo = computed(() => (editandoId.value ? 'Editar tipo de envio' : 'Novo tipo de envio'))

function vazio() {
  return {
    codigo: '',
    nome: '',
    descricao: '',
    na_fila_full: true,
    corpo_email_id: null,
    ativo: true,
  }
}

async function carregar() {
  carregando.value = true
  erro.value = ''
  try {
    const [t, c] = await Promise.all([
      api.get('/api/tipos-envio'),
      api.get('/api/corpos-email', { params: { ativo: true } }),
    ])
    tipos.value = t.data
    corpos.value = c.data
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao carregar tipos de envio'
  } finally {
    carregando.value = false
  }
}

function editar(row) {
  editandoId.value = row.id
  form.codigo = row.codigo
  form.nome = row.nome
  form.descricao = row.descricao || ''
  form.na_fila_full = row.na_fila_full
  form.corpo_email_id = row.corpo_email_id
  form.ativo = row.ativo
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function cancelar() {
  editandoId.value = null
  Object.assign(form, vazio())
}

async function salvar() {
  erro.value = ''
  ok.value = ''
  if (!form.codigo.trim() || !form.nome.trim()) {
    erro.value = 'Código e nome são obrigatórios'
    return
  }
  const payload = {
    codigo: form.codigo.trim().toLowerCase(),
    nome: form.nome.trim(),
    descricao: form.descricao?.trim() || null,
    na_fila_full: form.na_fila_full,
    corpo_email_id: form.corpo_email_id || null,
    ativo: form.ativo,
    ordem: 0,
  }
  try {
    if (editandoId.value) {
      await api.put(`/api/tipos-envio/${editandoId.value}`, {
        codigo: payload.codigo,
        nome: payload.nome,
        descricao: payload.descricao,
        na_fila_full: payload.na_fila_full,
        corpo_email_id: payload.corpo_email_id,
        ativo: payload.ativo,
      })
      ok.value = 'Tipo atualizado. A subpasta em ENTRADA segue o código (ex.: auto → pasta auto).'
    } else {
      await api.post('/api/tipos-envio', payload)
      ok.value = 'Tipo criado. A pasta correspondente foi criada em ENTRADA.'
    }
    cancelar()
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao salvar'
  }
}

async function remover(row) {
  if (!confirm(`Remover o tipo "${row.nome}"? A pasta em disco não é apagada automaticamente.`)) return
  try {
    await api.delete(`/api/tipos-envio/${row.id}`)
    ok.value = 'Tipo removido'
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao remover'
  }
}

onMounted(carregar)
</script>

<template>
  <div>
    <h2>Tipos de envio</h2>
    <p class="text-muted">
      Cada tipo usa uma <strong>subpasta</strong> com o mesmo nome do código dentro da pasta de entrada do FULL
      (ex.: código <code>auto</code> → arquivos em <code>…/entrada/auto</code>). Associe um
      <strong>corpo de e-mail</strong> para o modo FULL usar o HTML correto em cada tipo.
    </p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok"   class="alert alert-ok">{{ ok }}</div>

    <div class="card">
      <h3>{{ titulo }}</h3>
      <form @submit.prevent="salvar">
        <div class="row">
          <div>
            <label>Código (pasta) *</label>
            <input
              v-model="form.codigo"
              :disabled="!!editandoId"
              placeholder="ex.: auto"
              maxlength="60"
            />
            <small class="text-muted">Letras minúsculas, números, <code>_</code> e <code>-</code>.</small>
          </div>
          <div><label>Nome *</label><input v-model="form.nome" maxlength="120" /></div>
          <div>
            <label>Corpo de e-mail (FULL)</label>
            <select v-model="form.corpo_email_id">
              <option :value="null">— nenhum —</option>
              <option v-for="c in corpos" :key="c.id" :value="c.id">{{ c.nome }}</option>
            </select>
          </div>
        </div>
        <div class="row">
          <div class="flex gap-2 items-center">
            <label class="m-0"><input type="checkbox" v-model="form.na_fila_full" /> Na fila do FULL (padrão)</label>
          </div>
          <div class="flex gap-2 items-center">
            <label class="m-0"><input type="checkbox" v-model="form.ativo" /> Ativo</label>
          </div>
        </div>
        <div class="mt-2">
          <label>Descrição</label>
          <input v-model="form.descricao" maxlength="255" />
        </div>
        <div class="flex gap-2 mt-2">
          <button type="submit" class="btn btn-accent">{{ editandoId ? 'Salvar' : 'Cadastrar' }}</button>
          <button v-if="editandoId" type="button" class="btn btn-ghost" @click="cancelar">Cancelar</button>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="flex gap-2 items-center mb-2">
        <h3 class="m-0">Cadastrados</h3>
        <span class="spacer"></span>
        <button class="btn btn-ghost btn-sm" :disabled="carregando" @click="carregar">Atualizar</button>
      </div>
      <p v-if="carregando" class="text-muted">Carregando…</p>
      <table v-else-if="tipos.length" class="table">
        <thead>
          <tr>
            <th>Código</th>
            <th>Nome</th>
            <th>Corpo e-mail</th>
            <th>Fila FULL</th>
            <th>Pasta</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in tipos" :key="t.id">
            <td><code>{{ t.codigo }}</code></td>
            <td>{{ t.nome }}</td>
            <td>
              <span v-if="t.corpo_email_id">{{ corpos.find((c) => c.id === t.corpo_email_id)?.nome || '#' + t.corpo_email_id }}</span>
              <span v-else class="text-muted">—</span>
            </td>
            <td>{{ t.na_fila_full ? 'Sim' : 'Não' }}</td>
            <td><small class="text-muted">{{ t.pasta }}</small></td>
            <td>
              <button class="btn btn-ghost btn-sm" @click="editar(t)">Editar</button>
              <button class="btn btn-danger btn-sm" @click="remover(t)">Remover</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-muted">Nenhum tipo cadastrado.</p>
    </div>
  </div>
</template>
