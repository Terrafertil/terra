<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  capas: { type: Array, default: () => [] },
  label: { type: String, required: true },
  vazio: { type: String, default: 'Nenhuma capa selecionada.' },
})
const emit = defineEmits(['update:modelValue'])
const novaCapa = ref('')
const MAX_CAPAS = 10

const disponiveis = computed(() => {
  const selecionadas = new Set(props.modelValue.map(Number))
  return props.capas.filter((capa) => !selecionadas.has(Number(capa.id)))
})

function nome(capaId) {
  return props.capas.find((capa) => Number(capa.id) === Number(capaId))?.nome || `Capa #${capaId}`
}

function adicionar() {
  const id = Number(novaCapa.value)
  if (
    !id ||
    props.modelValue.length >= MAX_CAPAS ||
    props.modelValue.some((item) => Number(item) === id)
  ) return
  emit('update:modelValue', [...props.modelValue, id])
  novaCapa.value = ''
}

function remover(indice) {
  const itens = [...props.modelValue]
  itens.splice(indice, 1)
  emit('update:modelValue', itens)
}

function mover(indice, direcao) {
  const destino = indice + direcao
  if (destino < 0 || destino >= props.modelValue.length) return
  const itens = [...props.modelValue]
  ;[itens[indice], itens[destino]] = [itens[destino], itens[indice]]
  emit('update:modelValue', itens)
}
</script>

<template>
  <div class="capa-selector">
    <label>{{ label }}</label>
    <div class="capa-adicionar">
      <select v-model="novaCapa">
        <option value="">— escolher um padrão —</option>
        <option v-for="capa in disponiveis" :key="capa.id" :value="capa.id">
          {{ capa.nome }} · {{ capa.paginas }} pág.
        </option>
      </select>
      <button
        type="button"
        class="btn btn-ghost btn-sm"
        :disabled="!novaCapa || modelValue.length >= MAX_CAPAS"
        @click="adicionar"
      >
        Adicionar
      </button>
    </div>
    <p class="text-muted m-0 mt-2" style="font-size: 0.8rem">
      {{ modelValue.length }}/{{ MAX_CAPAS }} capas selecionadas deste lado.
    </p>
    <ol v-if="modelValue.length" class="capas-ordenadas">
      <li v-for="(capaId, indice) in modelValue" :key="capaId">
        <span class="capa-posicao" aria-hidden="true">{{ indice + 1 }}.</span>
        <span>{{ nome(capaId) }}</span>
        <span class="capa-acoes">
          <button type="button" class="btn btn-ghost btn-sm" :disabled="indice === 0" title="Mover para cima" @click="mover(indice, -1)">↑</button>
          <button type="button" class="btn btn-ghost btn-sm" :disabled="indice === modelValue.length - 1" title="Mover para baixo" @click="mover(indice, 1)">↓</button>
          <button type="button" class="btn btn-danger btn-sm" @click="remover(indice)">Remover</button>
        </span>
      </li>
    </ol>
    <p v-else class="text-muted m-0 mt-2">{{ vazio }}</p>
  </div>
</template>

<style scoped>
.capa-adicionar { display: flex; gap: 0.5rem; align-items: center; }
.capa-adicionar select { flex: 1; }
.capas-ordenadas { margin: 0.65rem 0 0; padding-left: 0; list-style: none; }
.capas-ordenadas li { margin: 0.35rem 0; padding-left: 0.2rem; }
.capas-ordenadas li::marker { font-weight: 700; }
.capas-ordenadas li, .capa-acoes { display: flex; align-items: center; gap: 0.35rem; }
.capas-ordenadas li { justify-content: space-between; }
.capa-posicao { min-width: 1.5rem; font-weight: 700; }
.capas-ordenadas li > :nth-child(2) { margin-right: auto; }
</style>
