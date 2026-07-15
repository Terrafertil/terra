import axios from 'axios'

const baseURL = import.meta.env.VITE_API_URL || ''
export const api = axios.create({
  baseURL,
  timeout: 60_000,
  withCredentials: true,
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      if (!['/login', '/recuperar-diretor'].includes(window.location.pathname)) {
        window.location.href = '/login'
      }
    }
    if (err.response?.data?.code === 'password_change_required') {
      err.passwordChangeRequired = true
      const path = window.location.pathname
      if (path !== '/trocar-senha' && path !== '/login') {
        window.location.href = '/trocar-senha'
      }
    }
    if (
      err.response?.status === 403 &&
      String(err.response?.data?.detail || '').toLowerCase().includes('backend')
    ) {
      err.backendAccessDenied = true
    }
    return Promise.reject(err)
  }
)

export const API_BASE_URL = baseURL
