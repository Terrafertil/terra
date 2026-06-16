<script setup>
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
</script>

<template>
  <div>
    <h2>Backup de apólices</h2>
    <div class="card backup-blocked">
      <div class="backup-blocked__icon" aria-hidden="true">🔒</div>
      <h3>Acesso restrito</h3>
      <p>
        A pasta <code>backend/backup/</code> contém cópias dos PDFs enviados e só pode ser consultada
        por utilizadores autorizados.
      </p>
      <p class="text-muted">
        O seu utilizador
        <strong v-if="auth.user">{{ auth.user.nome || auth.user.username }}</strong>
        não tem permissão para aceder a esta área.
      </p>
      <p>
        <strong>Contacte o administrador do sistema</strong> para solicitar acesso ao backup.
      </p>
      <RouterLink to="/dashboard" class="btn btn-primary mt-3">Voltar ao Dashboard</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.backup-blocked {
  max-width: 520px;
  text-align: center;
  padding: 2rem 1.5rem;
}
.backup-blocked__icon {
  font-size: 2.5rem;
  margin-bottom: 0.5rem;
}
.backup-blocked h3 {
  margin: 0 0 0.75rem;
  color: var(--err);
}
.backup-blocked p {
  margin: 0 0 0.65rem;
  line-height: 1.5;
  font-size: 0.95rem;
}
</style>
