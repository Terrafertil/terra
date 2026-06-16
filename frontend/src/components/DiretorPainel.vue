<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const token = ref('')
const carregando = ref(false)
const erro = ref('')
const copiado = ref(false)

async function carregarToken() {
  carregando.value = true
  erro.value = ''
  try {
    const { data } = await api.get('/api/auth/diretor/token-recuperacao')
    token.value = data.token || ''
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Nao foi possivel obter o token'
  } finally {
    carregando.value = false
  }
}

async function copiar() {
  if (!token.value) return
  try {
    await navigator.clipboard.writeText(token.value)
    copiado.value = true
    setTimeout(() => {
      copiado.value = false
    }, 2500)
  } catch {
    erro.value = 'Nao foi possivel copiar. Selecione o texto manualmente.'
  }
}

onMounted(carregarToken)
</script>

<template>
  <section class="card diretor-painel">
    <h3>Admin Diretor — token de recuperacao</h3>
    <p class="text-muted" style="font-size: 0.9rem">
      Use este token apenas se esquecer a senha do utilizador
      <strong>admindiretor</strong>. Guarde-o num cofre seguro. Nao partilhe com outros
      utilizadores.
    </p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>

    <label class="mt-2">Token (letras e numeros)</label>
    <div class="token-row">
      <input :value="token" type="text" readonly class="token-input" />
      <button
        type="button"
        class="btn btn-accent"
        :disabled="!token || carregando"
        @click="copiar"
      >
        {{ copiado ? 'Copiado!' : 'Copiar' }}
      </button>
    </div>

    <button
      type="button"
      class="btn btn-ghost btn-sm mt-2"
      :disabled="carregando"
      @click="carregarToken"
    >
      {{ carregando ? 'A carregar...' : 'Atualizar' }}
    </button>
  </section>
</template>

<style scoped>
.diretor-painel {
  margin-bottom: 1rem;
  border-color: rgba(0, 185, 78, 0.35);
}
.token-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: stretch;
}
.token-input {
  flex: 1;
  min-width: 200px;
  font-family: ui-monospace, monospace;
  font-size: 0.85rem;
}
</style>
