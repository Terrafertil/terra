import { defineStore } from 'pinia'
import { api } from '../api'

function claimsFromToken(token) {
  if (!token) return {}
  try {
    const b = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(b))
  } catch {
    return {}
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: localStorage.getItem('access_token') || null,
    authEnabled: false,
    mustChangePassword: false,
    _loaded: false,
  }),
  getters: {
    isLogged: (s) => !!s.token || !s.authEnabled,
    needsPasswordChange: (s) => s.authEnabled && !!s.token && s.mustChangePassword,
    podeAcessarBackup: (s) => {
      if (!s.authEnabled) return true
      const u = s.user
      if (!u) return false
      return Boolean(u.is_admin || u.acesso_backup)
    },
    isDiretor: (s) => Boolean(s.user?.is_diretor),
  },
  actions: {
    async carregarStatus() {
      const { data } = await api.get('/api/auth/status')
      this.authEnabled = !!data.auth_enabled
      return data
    },
    async carregarUsuario() {
      if (!this.token || !this.authEnabled) return null
      try {
        const { data } = await api.get('/api/auth/me')
        this.user = data
        return data
      } catch {
        return null
      }
    },
    async login(username, senha) {
      const { data } = await api.post('/api/auth/login', { username, senha })
      this.aplicarToken(data.access_token)
      this.user = data.user
      this.mustChangePassword = !!data.user?.must_change_password
      return data
    },
    logout() {
      this.token = null
      this.user = null
      this.mustChangePassword = false
      localStorage.removeItem('access_token')
    },
    aplicarToken(token) {
      this.token = token
      if (token) {
        localStorage.setItem('access_token', token)
        const c = claimsFromToken(token)
        this.mustChangePassword = !!c.must_change_password
      } else {
        localStorage.removeItem('access_token')
        this.mustChangePassword = false
      }
    },
    async restaurarSessao() {
      if (this.token) {
        const c = claimsFromToken(this.token)
        this.mustChangePassword = !!c.must_change_password
        if (this.authEnabled) {
          await this.carregarUsuario()
        }
      }
    },
  },
})
