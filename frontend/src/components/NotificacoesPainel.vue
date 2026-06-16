<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { useUiStore } from '../stores/ui'

const ui = useUiStore()
const lista = ref([])
const carregando = ref(false)
const expandido = ref(true)
let timer = null

async function carregar() {
  carregando.value = true
  try {
    const [n, c] = await Promise.all([
      api.get('/api/notificacoes', { params: { apenas_nao_lidas: true, limite: 20 } }),
      api.get('/api/notificacoes/contagem'),
    ])
    lista.value = n.data
    ui.notificacoesNaoLidas = c.data?.nao_lidas ?? 0
  } catch {
    /* API offline */
  } finally {
    carregando.value = false
  }
}

async function marcarLida(id) {
  await api.patch(`/api/notificacoes/${id}/lida`)
  await carregar()
}

async function marcarTodas() {
  await api.post('/api/notificacoes/marcar-todas-lidas')
  await carregar()
}

onMounted(() => {
  carregar()
  timer = setInterval(carregar, 30000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

defineExpose({ carregar })
</script>

<template>
  <section v-if="lista.length" class="card notificacoes-card">
    <div class="flex items-center gap-2 mb-2">
      <h3 class="m-0">
        Alertas do FULL
        <span class="badge erro">{{ ui.notificacoesNaoLidas }}</span>
      </h3>
      <span class="spacer" />
      <button type="button" class="btn btn-ghost btn-sm" @click="expandido = !expandido">
        {{ expandido ? 'Ocultar' : 'Mostrar' }}
      </button>
      <button type="button" class="btn btn-ghost btn-sm" :disabled="carregando" @click="carregar">
        Atualizar
      </button>
      <button type="button" class="btn btn-ghost btn-sm" @click="marcarTodas">Marcar todas lidas</button>
    </div>
    <p v-if="expandido" class="text-muted mb-2" style="font-size: 0.88rem">
      PDFs que o modo automático não processou. Corrija (cadastre cliente, use
      <RouterLink to="/envio">envio manual</RouterLink>) e marque como lida.
    </p>
    <ul v-show="expandido" class="notificacoes-lista">
      <li v-for="n in lista" :key="n.id" class="notificacao-item">
        <div class="notificacao-corpo">
          <strong>{{ n.arquivo }}</strong>
          <span v-if="n.layout" class="badge pendente">{{ n.layout }}</span>
          <p class="text-muted m-0">{{ n.motivo }}</p>
          <small class="text-muted">{{ new Date(n.criado_em).toLocaleString() }}</small>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" @click="marcarLida(n.id)">Lida</button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.notificacoes-card {
  border-left: 4px solid var(--err);
}
.notificacoes-lista {
  list-style: none;
  margin: 0;
  padding: 0;
}
.notificacao-item {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  padding: 0.65rem 0;
  border-bottom: 1px solid var(--border);
}
.notificacao-item:last-child {
  border-bottom: none;
}
.notificacao-corpo {
  flex: 1;
  min-width: 0;
}
.notificacao-corpo p {
  font-size: 0.88rem;
  margin-top: 0.25rem;
}
</style>
