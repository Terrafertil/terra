<script setup>
import { ref } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { api } from '../api'
import BrandLogo from '../components/BrandLogo.vue'

const auth = useAuthStore()
const router = useRouter()

const token = ref('')
const senhaNova = ref('')
const senhaNova2 = ref('')
const erro = ref('')
const loading = ref(false)

async function enviar() {
  erro.value = ''
  if (senhaNova.value !== senhaNova2.value) {
    erro.value = 'A confirmacao nao coincide.'
    return
  }
  loading.value = true
  try {
    const { data } = await api.post('/api/auth/recuperar-diretor', {
      token: token.value.trim(),
      senha_nova: senhaNova.value,
      senha_nova_confirmacao: senhaNova2.value,
    })
    auth.aplicarToken(data.access_token)
    auth.user = data.user
    auth.mustChangePassword = false
    router.replace('/dashboard')
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Recuperacao falhou'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <form class="login-box" @submit.prevent="enviar">
      <BrandLogo centered />
      <h2 style="margin-bottom: 0.4rem">Recuperar Admin Diretor</h2>
      <p class="text-muted" style="margin-bottom: 1.2rem">
        Utilize o token de recuperacao guardado no cofre da empresa.
      </p>

      <div v-if="erro" class="alert alert-err">{{ erro }}</div>

      <label>Token de recuperacao</label>
      <input v-model="token" type="text" autocomplete="off" required />

      <label class="mt-2">Nova senha</label>
      <input v-model="senhaNova" type="password" autocomplete="new-password" required />

      <label class="mt-2">Confirmar nova senha</label>
      <input v-model="senhaNova2" type="password" autocomplete="new-password" required />

      <button class="btn btn-primary" style="margin-top: 1.2rem; width: 100%" :disabled="loading">
        {{ loading ? 'A guardar...' : 'Redefinir senha' }}
      </button>

      <p class="text-muted mt-3" style="font-size: 0.88rem; text-align: center">
        <RouterLink to="/login">Voltar ao login</RouterLink>
      </p>
    </form>
  </div>
</template>
