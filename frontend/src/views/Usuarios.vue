<script setup>
import { ref, reactive, onMounted } from 'vue'
import { api } from '../api'

const usuarios = ref([])
const erro = ref('')
const ok = ref('')
const form = reactive({
  username: '',
  nome: '',
  email: '',
  senha: '',
  is_admin: false,
  acesso_backup: false,
  ativo: true,
})
const editandoId = ref(null)

const USERNAME_DIRETOR_RESERVADO = 'admindiretor'

function filtrarVisiveis(lista) {
  return (lista || []).filter(
    (u) =>
      !u.is_diretor &&
      String(u.username || '').trim().toLowerCase() !== USERNAME_DIRETOR_RESERVADO
  )
}

async function carregar() {
  erro.value = ''
  try {
    const { data } = await api.get('/api/usuarios')
    usuarios.value = filtrarVisiveis(data)
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao carregar usuários (login precisa estar ativo)'
  }
}

function editar(u) {
  editandoId.value = u.id
  Object.assign(form, { ...u, senha: '' })
}

function limpar() {
  editandoId.value = null
  Object.assign(form, {
    username: '',
    nome: '',
    email: '',
    senha: '',
    is_admin: false,
    acesso_backup: false,
    ativo: true,
  })
}

async function salvar() {
  erro.value = ''; ok.value = ''
  try {
    if (editandoId.value) {
      const body = { ...form }
      if (!body.senha) delete body.senha
      delete body.username
      await api.put(`/api/usuarios/${editandoId.value}`, body)
      ok.value = 'Usuário atualizado'
    } else {
      await api.post('/api/usuarios', form)
      ok.value = 'Usuário criado'
    }
    limpar()
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao salvar'
  }
}

function podeGerir(u) {
  return (
    !u.is_diretor &&
    String(u.username || '').trim().toLowerCase() !== USERNAME_DIRETOR_RESERVADO
  )
}

async function remover(u) {
  if (!podeGerir(u)) {
    erro.value = 'Este utilizador não pode ser removido.'
    return
  }
  if (!confirm(`Remover usuário ${u.username}?`)) return
  try {
    await api.delete(`/api/usuarios/${u.id}`)
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao remover'
  }
}

onMounted(carregar)
</script>

<template>
  <div>
    <h2>Usuários</h2>
    <p class="text-muted">Gerenciamento de usuários (só funciona se <code>AUTH_ENABLED=true</code>).</p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok" class="alert alert-ok">{{ ok }}</div>

    <div class="card">
      <h3>{{ editandoId ? 'Editar usuário' : 'Novo usuário' }}</h3>
      <form @submit.prevent="salvar">
        <div class="row">
          <div>
            <label>Username *</label>
            <input v-model="form.username" required :disabled="!!editandoId" />
          </div>
          <div>
            <label>Nome *</label>
            <input v-model="form.nome" required />
          </div>
          <div>
            <label>E-mail</label>
            <input v-model="form.email" type="email" />
          </div>
          <div>
            <label>{{ editandoId ? 'Nova senha (deixe vazio p/ manter)' : 'Senha *' }}</label>
            <input v-model="form.senha" type="password" :required="!editandoId" />
            <p class="text-muted" style="font-size:0.82rem;margin-top:0.35rem">
              Mín. 8 caracteres, maiúsculas, minúsculas, números e carácter especial.
            </p>
          </div>
          <div>
            <label>Admin</label>
            <select v-model="form.is_admin">
              <option :value="true">Sim</option>
              <option :value="false">Não</option>
            </select>
          </div>
          <div>
            <label>Acesso ao backup</label>
            <select v-model="form.acesso_backup" :disabled="form.is_admin">
              <option :value="true">Sim</option>
              <option :value="false">Não</option>
            </select>
            <p class="text-muted" style="font-size:0.82rem;margin-top:0.35rem">
              Ver e descarregar PDFs em <code>backend/backup/</code>. Administradores têm acesso sempre.
            </p>
          </div>
          <div>
            <label>Ativo</label>
            <select v-model="form.ativo">
              <option :value="true">Sim</option>
              <option :value="false">Não</option>
            </select>
          </div>
        </div>
        <div class="mt-4 flex gap-2">
          <button class="btn btn-primary">{{ editandoId ? 'Salvar' : 'Criar' }}</button>
          <button v-if="editandoId" type="button" class="btn btn-ghost" @click="limpar">Cancelar</button>
        </div>
      </form>
    </div>

    <div class="card">
      <table class="table" v-if="usuarios.length">
        <thead>
          <tr>
            <th>Username</th><th>Nome</th><th>E-mail</th><th>Admin</th><th>Backup</th><th>Ativo</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in usuarios" :key="u.id">
            <td>{{ u.username }}</td>
            <td>{{ u.nome }}</td>
            <td>{{ u.email || '—' }}</td>
            <td>{{ u.is_admin ? 'Sim' : 'Não' }}</td>
            <td>{{ u.is_admin || u.acesso_backup ? 'Sim' : 'Não' }}</td>
            <td>{{ u.ativo ? 'Sim' : 'Não' }}</td>
            <td style="text-align:right; white-space:nowrap;">
              <button v-if="podeGerir(u)" class="btn btn-ghost btn-sm" @click="editar(u)">
                Editar
              </button>
              <button
                v-if="podeGerir(u)"
                class="btn btn-danger btn-sm"
                @click="remover(u)"
                style="margin-left:.3rem"
              >
                Remover
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-muted">Nenhum usuário carregado.</p>
    </div>
  </div>
</template>
