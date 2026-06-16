<script setup>
defineProps({
  /** Sidebar: ícone + título na mesma linha */
  compact: { type: Boolean, default: false },
  /** Login: bloco centralizado, um pouco maior */
  centered: { type: Boolean, default: false },
  /** Linha extra abaixo do subtítulo (ex.: Painel de Operações) */
  tagline: { type: String, default: '' },
})
</script>

<template>
  <div
    class="brand"
    :class="{ 'brand--compact': compact, 'brand--centered': centered }"
    role="img"
    aria-label="Terra Fértil Corretora de Seguros"
  >
    <svg
      class="brand__mark"
      viewBox="0 0 44 44"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="44" height="44" rx="10" fill="#003C35" />
      <path
        d="M22 9c-6.5 0-11 4.5-11 11 0 8.5 11 21 11 21s11-12.5 11-21c0-6.5-4.5-11-11-11z"
        fill="#00B94E"
      />
      <circle cx="22" cy="19" r="4.5" fill="#7AFC57" />
    </svg>
    <div class="brand__text">
      <span class="brand__title">Terra Fértil</span>
      <span class="brand__subtitle">Corretora de Seguros</span>
      <span v-if="tagline" class="brand__tagline">{{ tagline }}</span>
    </div>
  </div>
</template>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: 0.65rem;
}

.brand--centered {
  flex-direction: column;
  text-align: center;
  gap: 0.75rem;
  margin-bottom: 0.25rem;
}

.brand__mark {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: block;
}

.brand--centered .brand__mark {
  width: 52px;
  height: 52px;
}

.brand__text {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  min-width: 0;
}

.brand--compact .brand__text {
  flex: 1;
}

.brand__title {
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.15;
  color: #fff;
  letter-spacing: -0.01em;
}

.brand--centered .brand__title {
  font-size: 1.2rem;
  color: var(--tf-preto-musgo, #003c35);
}

.brand__subtitle {
  font-size: 0.62rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--tf-verde-sereno, #6ec08b);
  line-height: 1.2;
}

.brand--centered .brand__subtitle {
  color: var(--tf-cinza-sombra, #444c49);
  font-size: 0.68rem;
}

.brand__tagline {
  font-size: 0.68rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--terra-300, #b8dcc8);
  margin-top: 0.15rem;
}
</style>
