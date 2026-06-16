import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
  {
    path: '/recuperar-diretor',
    name: 'recuperarDiretor',
    component: () => import('../views/RecuperarDiretor.vue'),
    meta: { public: true },
  },
  {
    path: '/trocar-senha',
    name: 'trocarSenha',
    component: () => import('../views/TrocarSenha.vue'),
    meta: { public: true, passwordChangeOnly: true },
  },
  {
    path: '/',
    component: () => import('../components/AppLayout.vue'),
    children: [
      { path: 'dashboard',  name: 'dashboard',  component: () => import('../views/Dashboard.vue') },
      { path: 'clientes',   name: 'clientes',   component: () => import('../views/Clientes.vue') },
      { path: 'autos',      name: 'autos',      component: () => import('../views/Autos.vue') },
      { path: 'envio',      name: 'envio',      component: () => import('../views/EnvioManual.vue') },
      { path: 'full-config',name: 'fullConfig', component: () => import('../views/FullConfig.vue') },
      { path: 'tipos-envio',name: 'tiposEnvio', component: () => import('../views/TiposEnvio.vue') },
      { path: 'corpos-email', name: 'corposEmail', component: () => import('../views/CorposEmail.vue') },
      { path: 'assinaturas', name: 'assinaturas', component: () => import('../views/Assinaturas.vue') },
      { path: 'capa',       name: 'capa',       component: () => import('../views/Capa.vue') },
      {
        path: 'backup',
        name: 'backup',
        component: () => import('../views/Backup.vue'),
        meta: { requiresBackupAccess: true },
      },
      { path: 'historico',  name: 'historico',  component: () => import('../views/Historico.vue') },
      { path: 'tutorial',   name: 'tutorial',   component: () => import('../views/Tutorial.vue') },
      {
        path: 'usuarios',
        name: 'usuarios',
        component: () => import('../views/Usuarios.vue'),
        meta: { requiresAdmin: true },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth._loaded) {
    try {
      await auth.carregarStatus()
    } catch { /* backend offline */ }
    auth.restaurarSessao()
    auth._loaded = true
  }

  if (to.meta.passwordChangeOnly) {
    if (!auth.authEnabled) return { name: 'dashboard' }
    if (!auth.token) return { name: 'login', query: { redirect: '/trocar-senha' } }
    if (!auth.mustChangePassword) return { name: 'dashboard' }
    return true
  }

  if (to.meta.public) {
    if (to.name === 'login' && auth.authEnabled && auth.token && auth.mustChangePassword) {
      return { name: 'trocarSenha' }
    }
    if (to.name === 'login' && auth.authEnabled && auth.token && !auth.mustChangePassword) {
      return { name: 'dashboard' }
    }
    return true
  }

  if (!auth.authEnabled) return true
  if (!auth.token) return { name: 'login', query: { redirect: to.fullPath } }
  if (auth.mustChangePassword) return { name: 'trocarSenha' }

  if (to.meta.requiresAdmin) {
    if (!auth.user) await auth.carregarUsuario()
    if (!auth.user?.is_admin) return { name: 'dashboard' }
  }

  if (to.meta.requiresBackupAccess) {
    if (!auth.user) await auth.carregarUsuario()
    if (!auth.podeAcessarBackup) return { name: 'dashboard' }
  }

  return true
})

export default router
