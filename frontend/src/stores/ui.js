import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

const TOUR_PREFIX = 'tf_tour_v3_concluido_'

function tourStorageKey(userId) {
  if (userId == null || userId === '') return null
  return `${TOUR_PREFIX}${userId}`
}

export const useUiStore = defineStore('ui', () => {
  const notificacoesNaoLidas = ref(0)
  const ocrDisponivel = ref(false)
  const socModeActive = ref(false)
  let notificacoesTimer = null

  async function atualizarContagemNotificacoes() {
    try {
      const { data } = await api.get('/api/notificacoes/contagem')
      notificacoesNaoLidas.value = data?.nao_lidas ?? 0
    } catch {
      // MantÃ©m o Ãºltimo valor quando a API estiver indisponÃ­vel.
    }
  }

  function iniciarPollingNotificacoes() {
    if (notificacoesTimer) return
    atualizarContagemNotificacoes()
    notificacoesTimer = setInterval(atualizarContagemNotificacoes, 30000)
  }

  function pararPollingNotificacoes() {
    if (notificacoesTimer) clearInterval(notificacoesTimer)
    notificacoesTimer = null
  }

  /** userId: id do utilizador (string/number) ou 'anon' quando auth desligada */
  function tourConcluido(userId) {
    const key = tourStorageKey(userId)
    if (!key) return false
    return localStorage.getItem(key) === '1'
  }

  function marcarTourConcluido(userId) {
    const key = tourStorageKey(userId)
    if (key) localStorage.setItem(key, '1')
  }

  function reiniciarTour(userId) {
    const key = tourStorageKey(userId)
    if (key) localStorage.removeItem(key)
  }

  return {
    notificacoesNaoLidas,
    ocrDisponivel,
    socModeActive,
    atualizarContagemNotificacoes,
    iniciarPollingNotificacoes,
    pararPollingNotificacoes,
    tourConcluido,
    marcarTourConcluido,
    reiniciarTour,
  }
})
