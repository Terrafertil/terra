<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { api } from '../api'
import BrandLogo from '../components/BrandLogo.vue'

const auth = useAuthStore()
const router = useRouter()

const senhaAtual = ref('')
const senhaNova = ref('')
const senhaNova2 = ref('')
const erro = ref('')
const ok = ref('')
const loading = ref(false)

const regras = computed(() => {
  const s = senhaNova.value
  return {
    tamanho: s.length >= 8,
    minuscula: /[a-z]/.test(s),
    maiuscula: /[A-Z]/.test(s),
    numero: /\d/.test(s),
    especial: /[^A-Za-z0-9]/.test(s),
  }
})

const senhaValida = computed(() => Object.values(regras.value).every(Boolean))

async function enviar() {
  erro.value = ''
  ok.value = ''
  if (!senhaValida.value) {
    erro.value = 'A nova senha não cumpre todos os requisitos.'
    return
  }
  if (senhaNova.value !== senhaNova2.value) {
    erro.value = 'A confirmação não coincide com a nova senha.'
    return
  }
  loading.value = true
  try {
    const { data } = await api.post('/api/auth/trocar-senha', {
      senha_atual: senhaAtual.value,
      senha_nova: senhaNova.value,
      senha_nova_confirmacao: senhaNova2.value,
    })
    auth.aplicarToken(data.access_token)
    auth.user = data.user
    auth.mustChangePassword = false
    ok.value = data.mensagem
    setTimeout(() => router.replace('/dashboard'), 800)
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Não foi possível alterar a senha'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <form class="login-box" @submit.prevent="enviar">
      <BrandLogo centered />
      <h2 style="margin-bottom: 0.4rem">Definir nova senha</h2>
      <p class="text-muted" style="margin-bottom: 1.2rem">
        Por segurança, altere a senha inicial antes de usar o sistema.
      </p>

      <div v-if="erro" class="alert alert-err">{{ erro }}</div>
      <div v-if="ok" class="alert alert-ok">{{ ok }}</div>

      <label>Senha atual</label>
      <input
        v-model="senhaAtual"
        type="password"
        autocomplete="current-password"
        required
        autofocus
      />

      <label class="mt-2">Nova senha</label>
      <input v-model="senhaNova" type="password" autocomplete="new-password" required />

      <ul class="senha-regras">
        <li :class="{ ok: regras.tamanho }">Mínimo 8 caracteres</li>
        <li :class="{ ok: regras.maiuscula }">Letra maiúscula</li>
        <li :class="{ ok: regras.minuscula }">Letra minúscula</li>
        <li :class="{ ok: regras.numero }">Número</li>
        <li :class="{ ok: regras.especial }">Carácter especial</li>
      </ul>

      <label class="mt-2">Confirmar nova senha</label>
      <input v-model="senhaNova2" type="password" autocomplete="new-password" required />

      <button
        class="btn btn-primary"
        style="margin-top: 1.2rem; width: 100%"
        :disabled="loading || !senhaValida"
      >
        {{ loading ? 'A guardar…' : 'Guardar nova senha' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.senha-regras {
  margin: 0.5rem 0 0;
  padding-left: 1.1rem;
  font-size: 0.85rem;
  color: var(--muted);
}
.senha-regras li.ok {
  color: var(--ok);
}
</style>
