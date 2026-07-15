import { defineStore } from 'pinia'
import { api } from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    authEnabled: false,
    mustChangePassword: false,
    _loaded: false,
  }),
  getters: {
    isLogged: (s) => Boolean(s.user) || !s.authEnabled,
    needsPasswordChange: (s) =>
      s.authEnabled && Boolean(s.user) && s.mustChangePassword,
    podeAcessarBackup: (s) => {
      if (!s.authEnabled) return true
      if (!s.user) return false
      return Boolean(s.user.is_admin || s.user.acesso_backup)
    },
    isDiretor: (s) => Boolean(s.user?.is_diretor),
  },
  actions: {
    aplicarUsuario(user) {
      this.user = user || null
      this.mustChangePassword = Boolean(user?.must_change_password)
    },
    limparSessao() {
      this.user = null
      this.mustChangePassword = false
      // Remove sessÃµes antigas, usadas antes da migraÃ§Ã£o para cookie HttpOnly.
      localStorage.removeItem('access_token')
      localStorage.removeItem('tf_backend_access_key')
    },
    async carregarStatus() {
      const { data } = await api.get('/api/auth/status')
      this.authEnabled = Boolean(data.auth_enabled)
      return data
    },
    async carregarUsuario() {
      if (!this.authEnabled) return null
      try {
        const { data } = await api.get('/api/auth/me')
        this.aplicarUsuario(data)
        return data
      } catch {
        this.limparSessao()
        return null
      }
    },
    async login(username, senha) {
      const { data } = await api.post('/api/auth/login', { username, senha })
      this.aplicarUsuario(data.user)
      return data
    },
    async logout() {
      try {
        await api.post('/api/auth/logout')
      } finally {
        this.limparSessao()
      }
    },
    async restaurarSessao() {
      this.limparSessao()
      if (this.authEnabled) await this.carregarUsuario()
    },
  },
})
