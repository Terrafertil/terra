<script setup>
import { ref, computed, watch } from 'vue'
import { api } from '../api'

const props = defineProps({
  status: { type: Object, default: null },
  isAdmin: { type: Boolean, default: false },
  isDiretor: { type: Boolean, default: false },
})

const emit = defineEmits(['atualizado'])

const ativarAberto = ref(false)
const desativarAberto = ref(false)
const chave = ref('')
const chave2 = ref('')
const chaveDesativar = ref('')
const motivo = ref('Suspeita de invasao ou ataque')
const erro = ref('')
const ok = ref('')
const processando = ref(false)

const socAtivo = computed(() => Boolean(props.status?.soc_mode_active))
const podeAtivar = computed(() => props.isAdmin && !socAtivo.value)
const podeDesativar = computed(() => props.isDiretor && socAtivo.value)

watch(
  () => props.status?.soc_mode_active,
  (v) => {
    if (v) ativarAberto.value = false
  }
)

async function ativar() {
  erro.value = ''
  ok.value = ''
  if (chave.value.length < 8) {
    erro.value = 'A chave de emergencia deve ter pelo menos 8 caracteres'
    return
  }
  if (chave.value !== chave2.value) {
    erro.value = 'As chaves nao coincidem'
    return
  }
  if (
    !confirm(
      'ATIVAR MODO SOC?\n\n- Todos os envios serao bloqueados\n- Os dados dos clientes serao recifrados\n- Guarde a chave no cofre — so o Admin Diretor pode desativar\n\nContinuar?'
    )
  ) {
    return
  }
  processando.value = true
  try {
    const { data } = await api.post('/api/soc/ativar', {
      chave_soc: chave.value,
      chave_soc_confirmacao: chave2.value,
      motivo: motivo.value,
    })
    ok.value = data.mensagem
    chave.value = ''
    chave2.value = ''
    ativarAberto.value = false
    emit('atualizado')
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Falha ao ativar modo SOC'
  } finally {
    processando.value = false
  }
}

async function desativar() {
  erro.value = ''
  ok.value = ''
  if (!chaveDesativar.value) {
    erro.value = 'Informe a chave de emergencia'
    return
  }
  processando.value = true
  try {
    const { data } = await api.post('/api/soc/desativar', {
      chave_soc: chaveDesativar.value,
    })
    ok.value = data.mensagem
    chaveDesativar.value = ''
    desativarAberto.value = false
    emit('atualizado')
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Chave incorreta ou falha ao desativar'
  } finally {
    processando.value = false
  }
}
</script>

<template>
  <section class="card soc-painel" :class="{ 'soc-painel--ativo': socAtivo }">
    <h3>Modo SOC (resposta a incidente)</h3>

    <div v-if="socAtivo" class="alert alert-err soc-banner">
      <strong>MODO SOC ATIVO</strong> - envios e operacoes bloqueados.
      <span v-if="status?.soc_motivo"> Motivo: {{ status.soc_motivo }}</span>
      <span v-if="status?.soc_ativado_por_nome" class="d-block mt-1" style="font-size: 0.85rem">
        Ativado por: <strong>{{ status.soc_ativado_por_nome }}</strong>
      </span>
      <span v-if="status?.soc_ativado_em" class="d-block" style="font-size: 0.85rem">
        Desde: {{ status.soc_ativado_em }}
      </span>
    </div>

    <div v-else class="soc-estado-inativo">
      <p class="text-muted mb-0" style="font-size: 0.9rem">
        <strong>Estado:</strong> inativo - operacoes normais.
      </p>
    </div>

    <template v-if="!isAdmin && !isDiretor">
      <p class="text-muted mt-2" style="font-size: 0.88rem">
        Em caso de incidente, contacte um administrador. Apenas administradores podem ativar o SOC;
        apenas o <strong>Admin Diretor</strong> pode desativa-lo.
      </p>
    </template>

    <template v-else-if="isAdmin && !isDiretor">
      <p v-if="!socAtivo" class="text-muted mt-2" style="font-size: 0.9rem">
        Em caso de ataque, ative o SOC para parar envios e recifrar clientes. A desativacao e feita
        pelo <strong>Admin Diretor</strong> com a chave guardada no cofre.
      </p>
      <p v-else class="text-muted mt-2" style="font-size: 0.88rem">
        Modo SOC ativo. Para desativar, o <strong>Admin Diretor</strong> deve usar a chave de
        emergencia definida na ativacao.
      </p>
    </template>

    <template v-else-if="isDiretor">
      <p v-if="!socAtivo" class="text-muted mt-2" style="font-size: 0.9rem">
        Como Admin Diretor, pode desativar o modo SOC quando o incidente estiver controlado (com a
        chave de emergencia). A ativacao e feita por outros administradores.
      </p>
    </template>

    <div v-if="erro" class="alert alert-err mt-2">{{ erro }}</div>
    <div v-if="ok" class="alert alert-ok mt-2">{{ ok }}</div>

    <div v-if="podeAtivar" class="flex gap-2 flex-wrap mt-2">
      <button type="button" class="btn btn-danger" @click="ativarAberto = true">
        Ativar modo SOC
      </button>
    </div>

    <div v-if="podeDesativar" class="flex gap-2 mt-2">
      <button type="button" class="btn btn-accent" @click="desativarAberto = true">
        Desativar modo SOC (chave de emergencia)
      </button>
    </div>

    <div v-if="ativarAberto && podeAtivar" class="modal-backdrop" @click.self="ativarAberto = false">
      <div class="modal-card soc-modal">
        <h4>Ativar modo SOC</h4>
        <label>Nova chave de emergencia *</label>
        <input v-model="chave" type="password" autocomplete="new-password" />
        <label class="mt-2">Confirmar chave *</label>
        <input v-model="chave2" type="password" autocomplete="new-password" />
        <label class="mt-2">Motivo</label>
        <input v-model="motivo" type="text" placeholder="Ex.: intrusao detectada" />
        <div class="flex gap-2 mt-4">
          <button type="button" class="btn btn-danger" :disabled="processando" @click="ativar">
            {{ processando ? 'A processar...' : 'Confirmar ativacao' }}
          </button>
          <button type="button" class="btn btn-ghost" @click="ativarAberto = false">Cancelar</button>
        </div>
      </div>
    </div>

    <div v-if="desativarAberto && podeDesativar" class="modal-backdrop" @click.self="desativarAberto = false">
      <div class="modal-card soc-modal">
        <h4>Desativar modo SOC</h4>
        <p class="text-muted" style="font-size: 0.9rem">
          Os dados voltam a criptografia normal do .env. Os envios sao liberados.
        </p>
        <label>Chave de emergencia usada na ativacao *</label>
        <input
          v-model="chaveDesativar"
          type="password"
          autocomplete="off"
          @keyup.enter="desativar"
        />
        <div class="flex gap-2 mt-4">
          <button type="button" class="btn btn-accent" :disabled="processando" @click="desativar">
            {{ processando ? 'A processar...' : 'Desativar e restaurar operacao' }}
          </button>
          <button type="button" class="btn btn-ghost" @click="desativarAberto = false">
            Cancelar
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.soc-painel--ativo {
  border-color: var(--err);
  box-shadow: 0 0 0 1px rgba(197, 48, 48, 0.25);
}
.soc-banner {
  margin-bottom: 0.75rem;
}
.soc-estado-inativo {
  margin-bottom: 0.25rem;
}
.soc-modal {
  max-width: 420px;
}
</style>
