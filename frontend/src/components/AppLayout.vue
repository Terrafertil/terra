<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'
import { api } from '../api'
import OnboardingTour from './OnboardingTour.vue'
import BrandLogo from './BrandLogo.vue'
import BackendAccessGate from './BackendAccessGate.vue'

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()

const mostrarUsuarios = computed(() => auth.authEnabled && Boolean(auth.user?.is_admin))
const mostrarBackup = computed(() => !auth.authEnabled || auth.podeAcessarBackup)
const mostrarTour = ref(false)

const linksFixos = [
  { to: '/dashboard', label: 'Dashboard', destaque: false },
  { to: '/tutorial', label: 'Tutorial', destaque: true },
]

let pollTimer = null

async function atualizarNotificacoes() {
  try {
    const { data } = await api.get('/api/notificacoes/contagem')
    ui.notificacoesNaoLidas = data?.nao_lidas ?? 0
  } catch {
  }
}

async function carregarStatusOcr() {
  try {
    const { data } = await api.get('/api/status')
    ui.ocrDisponivel = data.ocr_disponivel ?? false
    ui.notificacoesNaoLidas = data.notificacoes_nao_lidas ?? 0
    ui.socModeActive = Boolean(data.soc_mode_active)
  } catch {
  }
}

function sair() {
  auth.logout()
  router.push({ name: 'login' })
}

function tourUserId() {
  if (!auth.authEnabled) return 'anon'
  const id = auth.user?.id
  return id != null ? String(id) : null
}

function avaliarTourAutomatico() {
  const uid = tourUserId()
  if (uid == null) return
  if (!ui.tourConcluido(uid)) {
    mostrarTour.value = true
  }
}

function iniciarTour() {
  const uid = tourUserId()
  if (uid != null) ui.reiniciarTour(uid)
  mostrarTour.value = true
}

onMounted(async () => {
  carregarStatusOcr()
  if (auth.authEnabled && auth.token && !auth.user) {
    await auth.carregarUsuario()
  }
  avaliarTourAutomatico()
  pollTimer = setInterval(() => {
    atualizarNotificacoes()
  }, 30000)
})

watch(
  () => auth.user?.id,
  (id) => {
    if (id != null) avaliarTourAutomatico()
  }
)

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="app-shell">
    <aside class="app-sidebar">
      <div class="app-brand">
        <BrandLogo compact tagline="Painel de Operações" />
      </div>
      <nav class="sidebar-nav">
        <RouterLink
          v-for="l in linksFixos"
          :key="l.to"
          class="nav-link"
          :class="{ 'nav-link--tutorial': l.destaque }"
          :to="l.to"
        >
          {{ l.label }}
          <span
            v-if="l.to === '/dashboard' && ui.notificacoesNaoLidas > 0"
            class="nav-badge"
          >{{ ui.notificacoesNaoLidas }}</span>
        </RouterLink>

        <p class="nav-section-label">Mais</p>
        <RouterLink class="nav-link" to="/envio">Envio Manual</RouterLink>
        <RouterLink class="nav-link" to="/clientes">Clientes</RouterLink>
        <RouterLink class="nav-link" to="/autos">Autos</RouterLink>
        <RouterLink class="nav-link" to="/full-config">FULL — Configuração</RouterLink>
        <RouterLink class="nav-link" to="/tipos-envio">Tipos de Envio</RouterLink>
        <RouterLink class="nav-link" to="/corpos-email">Corpos de E-mail</RouterLink>
        <RouterLink class="nav-link" to="/assinaturas">Assinaturas</RouterLink>
        <RouterLink class="nav-link" to="/capa">Capa</RouterLink>
        <RouterLink v-if="mostrarBackup" class="nav-link" to="/backup">Backup</RouterLink>
        <RouterLink class="nav-link" to="/historico">Histórico</RouterLink>
        <RouterLink v-if="mostrarUsuarios" class="nav-link" to="/usuarios">Usuários</RouterLink>
      </nav>
      <footer class="sidebar-credit">
        <button type="button" class="btn-tour-replay" @click="iniciarTour">
          <span class="btn-tour-replay__icon" aria-hidden="true">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M4 12a8 8 0 0 1 13.66-5.66M4 12V7m0 5h5"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </span>
          Rever tour guiado
        </button>
        <a
          href="https://www.zontech.online/"
          target="_blank"
          rel="noopener noreferrer"
          title="Zona Tech — zontech.online"
        >
          Zona Tech
        </a>
      </footer>
    </aside>

    <main class="app-main">
      <div v-if="ui.socModeActive" class="soc-global-banner" role="alert">
        <strong>MODO SOC ATIVO</strong> — envios e alterações bloqueados. Desative no Dashboard com a chave de emergência.
      </div>

      <header class="app-topbar app-topbar--auth">
        <div>
          <small class="text-muted">
            Autenticação: <strong>{{ auth.authEnabled ? 'ATIVA' : 'DESATIVADA' }}</strong>
            <span v-if="ui.ocrDisponivel" class="ocr-pill">OCR ativo</span>
          </small>
        </div>
        <div v-if="auth.authEnabled && auth.user">
          <span class="text-muted">{{ auth.user.nome }}</span>
          <button class="btn btn-ghost btn-sm" style="margin-left:.6rem" @click="sair">Sair</button>
        </div>
      </header>

      <RouterView />
    </main>

    <OnboardingTour v-if="mostrarTour" @fechar="mostrarTour = false" />
    <BackendAccessGate />
  </div>
</template>

<style scoped>
.nav-badge {
  display: inline-block;
  min-width: 1.1rem;
  padding: 0.05rem 0.35rem;
  margin-left: 0.35rem;
  border-radius: 999px;
  background: var(--err);
  color: #fff;
  font-size: 0.7rem;
  font-weight: 700;
  text-align: center;
}
.soc-global-banner {
  margin: 0 0 0.75rem;
  padding: 0.65rem 1rem;
  border-radius: 8px;
  background: rgba(197, 48, 48, 0.15);
  border: 1px solid var(--err);
  color: var(--err);
  font-size: 0.9rem;
}
.ocr-pill {
  margin-left: 0.5rem;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  background: rgba(122, 252, 87, 0.2);
  color: var(--tf-verde-agro);
  font-size: 0.75rem;
}
</style>
