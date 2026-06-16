<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { API_BASE_URL, setBackendAccessKey, getBackendAccessKey } from '../api'

const visivel = ref(false)
const chave = ref('')
const erro = ref('')
const carregando = ref(false)
const precisaChave = ref(false)

async function verificarNecessidade() {
  try {
    const { data } = await axios.get(`${API_BASE_URL}/api/status`)
    precisaChave.value = Boolean(data.backend_access_enabled)
    if (precisaChave.value && !getBackendAccessKey()) {
      visivel.value = true
    }
  } catch {
    /* backend offline */
  }
}

async function confirmar() {
  erro.value = ''
  carregando.value = true
  try {
    const { data } = await axios.post(`${API_BASE_URL}/api/auth/verificar-acesso-backend`, {
      chave: chave.value,
    })
    if (data?.ok) {
      setBackendAccessKey(chave.value.trim())
      visivel.value = false
      window.location.reload()
    } else {
      erro.value = 'Chave recusada pelo servidor'
    }
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Chave inválida'
  } finally {
    carregando.value = false
  }
}

onMounted(verificarNecessidade)
</script>

<template>
  <div v-if="visivel" class="modal-backdrop backend-gate">
    <div class="modal-card" role="dialog" aria-labelledby="gate-titulo">
      <h3 id="gate-titulo">Acesso ao backend</h3>
      <p class="text-muted" style="font-size: 0.9rem">
        O servidor exige uma chave de acesso antes de expor os dados dos clientes.
        Peça a chave ao administrador do sistema (valor de <code>BACKEND_ACCESS_KEY</code>).
      </p>
      <label>Chave de acesso</label>
      <input
        v-model="chave"
        type="password"
        autocomplete="off"
        placeholder="Cole a chave do administrador"
        @keyup.enter="confirmar"
      />
      <div v-if="erro" class="alert alert-err mt-2">{{ erro }}</div>
      <button
        type="button"
        class="btn btn-accent mt-4"
        style="width: 100%"
        :disabled="carregando || !chave.trim()"
        @click="confirmar"
      >
        {{ carregando ? 'A validar…' : 'Desbloquear painel' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.backend-gate {
  z-index: 3000;
}
</style>
