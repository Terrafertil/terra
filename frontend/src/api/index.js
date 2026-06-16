import axios from 'axios'

const baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const STORAGE_BACKEND_KEY = 'tf_backend_access_key'

export const api = axios.create({
  baseURL,
  timeout: 60_000,
})

function backendAccessKey() {
  return (
    localStorage.getItem(STORAGE_BACKEND_KEY) ||
    import.meta.env.VITE_BACKEND_ACCESS_KEY ||
    ''
  )
}

export function setBackendAccessKey(chave) {
  if (chave) localStorage.setItem(STORAGE_BACKEND_KEY, chave)
  else localStorage.removeItem(STORAGE_BACKEND_KEY)
}

export function getBackendAccessKey() {
  return backendAccessKey()
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`

  const bk = backendAccessKey()
  if (bk) config.headers['X-Backend-Access-Key'] = bk

  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
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
