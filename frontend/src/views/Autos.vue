<script setup>
import { ref, onMounted, reactive, computed } from 'vue'
import { api } from '../api'

const autos = ref([])
const clientes = ref([])
const busca = ref('')
const filtroClienteId = ref(null)
const carregando = ref(false)
const erro = ref('')
const ok = ref('')

const form = reactive(vazio())
const editandoId = ref(null)

function vazio() {
  return {
    cliente_id: null,
    placa: '',
    marca: '',
    modelo: '',
    ano: '',
    chassi: '',
    renavam: '',
    cor: '',
    combustivel: '',
    observacoes: '',
    ativo: true,
  }
}

const titulo = computed(() => editandoId.value ? 'Editar veículo' : 'Novo veículo')

const autosFiltrados = computed(() => {
  let r = autos.value
  if (filtroClienteId.value) r = r.filter((a) => a.cliente_id === filtroClienteId.value)
  if (busca.value) {
    const q = busca.value.toLowerCase()
    r = r.filter((a) =>
      [a.placa, a.marca, a.modelo, a.chassi, a.cliente_nome]
        .filter(Boolean).some((t) => String(t).toLowerCase().includes(q)),
    )
  }
  return r
})

async function carregar() {
  carregando.value = true; erro.value = ''
  try {
    const [a, c] = await Promise.all([
      api.get('/api/autos'),
      api.get('/api/clientes'),
    ])
    autos.value = a.data
    clientes.value = c.data
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao carregar autos'
  } finally {
    carregando.value = false
  }
}

function editar(a) {
  editandoId.value = a.id
  Object.assign(form, a)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function cancelar() {
  editandoId.value = null
  Object.assign(form, vazio())
}

async function salvar() {
  erro.value = ''; ok.value = ''
  if (!form.cliente_id) { erro.value = 'Selecione o cliente'; return }
  if (!form.placa) { erro.value = 'Placa é obrigatória'; return }
  try {
    if (editandoId.value) {
      await api.put(`/api/autos/${editandoId.value}`, form)
      ok.value = 'Veículo atualizado'
    } else {
      await api.post('/api/autos', form)
      ok.value = 'Veículo cadastrado'
    }
    cancelar()
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao salvar'
  }
}

async function remover(a) {
  if (!confirm(`Remover veículo ${a.placa}?`)) return
  try {
    await api.delete(`/api/autos/${a.id}`)
    ok.value = 'Veículo removido'
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao remover'
  }
}

onMounted(carregar)
</script>

<template>
  <div>
    <h2>Autos</h2>
    <p class="text-muted">Veículos vinculados a clientes. Um cliente pode ter vários veículos.</p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok"   class="alert alert-ok">{{ ok }}</div>

    <div class="card">
      <h3>{{ titulo }}</h3>
      <form @submit.prevent="salvar">
        <div class="row">
          <div>
            <label>Cliente *</label>
            <select v-model="form.cliente_id" required>
              <option :value="null">— selecione —</option>
              <option v-for="c in clientes" :key="c.id" :value="c.id">{{ c.nome }}</option>
            </select>
          </div>
          <div><label>Placa *</label><input v-model="form.placa" required maxlength="20" /></div>
          <div><label>Marca</label><input v-model="form.marca" /></div>
          <div><label>Modelo</label><input v-model="form.modelo" /></div>
          <div><label>Ano</label><input v-model="form.ano" /></div>
          <div><label>Chassi</label><input v-model="form.chassi" /></div>
          <div><label>Renavam</label><input v-model="form.renavam" /></div>
          <div><label>Cor</label><input v-model="form.cor" /></div>
          <div><label>Combustível</label>
            <select v-model="form.combustivel">
              <option value="">—</option>
              <option>Gasolina</option><option>Etanol</option><option>Flex</option>
              <option>Diesel</option><option>GNV</option><option>Elétrico</option>
              <option>Híbrido</option>
            </select>
          </div>
        </div>
        <div class="mt-2">
          <label>Observações</label>
          <textarea v-model="form.observacoes" rows="2"></textarea>
        </div>
        <div class="flex gap-2 mt-2">
          <button type="submit" class="btn btn-accent">{{ editandoId ? 'Salvar' : 'Cadastrar' }}</button>
          <button v-if="editandoId" type="button" class="btn btn-ghost" @click="cancelar">Cancelar</button>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="flex gap-2 items-center mb-2">
        <input v-model="busca" placeholder="Buscar por placa, marca, modelo, cliente..." style="max-width: 320px" />
        <select v-model="filtroClienteId" style="max-width: 240px">
          <option :value="null">Todos os clientes</option>
          <option v-for="c in clientes" :key="c.id" :value="c.id">{{ c.nome }}</option>
        </select>
        <span class="spacer"></span>
        <button class="btn btn-ghost btn-sm" @click="carregar">Atualizar</button>
      </div>

      <table class="table" v-if="autosFiltrados.length">
        <thead>
          <tr>
            <th>Placa</th><th>Marca/Modelo</th><th>Ano</th><th>Cliente</th>
            <th>Combustível</th><th>Ativo</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in autosFiltrados" :key="a.id">
            <td><strong>{{ a.placa }}</strong></td>
            <td>{{ [a.marca, a.modelo].filter(Boolean).join(' ') || '—' }}</td>
            <td>{{ a.ano || '—' }}</td>
            <td>{{ a.cliente_nome || '—' }}</td>
            <td>{{ a.combustivel || '—' }}</td>
            <td>{{ a.ativo ? 'Sim' : 'Não' }}</td>
            <td>
              <button class="btn btn-ghost btn-sm" @click="editar(a)">Editar</button>
              <button class="btn btn-danger btn-sm" @click="remover(a)">Remover</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-muted">Nenhum veículo encontrado.</p>
    </div>
  </div>
</template>
