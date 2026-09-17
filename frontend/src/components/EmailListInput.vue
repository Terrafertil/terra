<script setup>
import { computed, nextTick, ref, useId } from 'vue'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  id: {
    type: String,
    default: '',
  },
  label: {
    type: String,
    default: '',
  },
  hint: {
    type: String,
    default: '',
  },
  placeholder: {
    type: String,
    default: 'nome@exemplo.com',
  },
  max: {
    type: Number,
    default: 20,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])

const generatedId = useId()
const inputId = computed(() => props.id || `email-list-${generatedId}`)
const hintId = computed(() => `${inputId.value}-hint`)
const errorId = computed(() => `${inputId.value}-error`)
const inputRef = ref(null)
const rascunho = ref('')
const erro = ref('')

const EMAIL_SIMPLES = /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/

function normalizarLista(valores) {
  const vistos = new Set()
  const resultado = []

  for (const valor of Array.isArray(valores) ? valores : []) {
    const email = String(valor || '').trim()
    const chave = email.toLocaleLowerCase()
    if (!email || vistos.has(chave)) continue
    vistos.add(chave)
    resultado.push(email)
  }

  return resultado
}

const emails = computed(() => normalizarLista(props.modelValue))

function definirValidade(mensagem = '') {
  erro.value = mensagem
  nextTick(() => inputRef.value?.setCustomValidity(mensagem))
}

function limparErro() {
  if (erro.value) definirValidade('')
}

function separar(texto) {
  return String(texto || '')
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function adicionarTexto(texto) {
  const candidatos = separar(texto)
  if (!candidatos.length) return

  const atuais = emails.value
  const vistos = new Set(atuais.map((email) => email.toLocaleLowerCase()))
  const adicionados = []
  const invalidos = []
  let excedeuLimite = false

  for (const candidato of candidatos) {
    const chave = candidato.toLocaleLowerCase()
    if (vistos.has(chave)) continue
    if (!EMAIL_SIMPLES.test(candidato)) {
      invalidos.push(candidato)
      continue
    }
    if (atuais.length + adicionados.length >= props.max) {
      excedeuLimite = true
      continue
    }
    vistos.add(chave)
    adicionados.push(candidato)
  }

  if (adicionados.length) {
    emit('update:modelValue', [...atuais, ...adicionados])
  }

  rascunho.value = invalidos.join(', ')
  if (invalidos.length) {
    definirValidade(
      invalidos.length === 1
        ? `E-mail inválido: ${invalidos[0]}`
        : `E-mails inválidos: ${invalidos.join(', ')}`,
    )
  } else if (excedeuLimite) {
    erro.value = `Use no máximo ${props.max} destinatários adicionais.`
    nextTick(() => inputRef.value?.setCustomValidity(''))
  } else {
    definirValidade('')
  }
}

function onInput(event) {
  rascunho.value = event.target.value
  limparErro()
}

function onKeydown(event) {
  if (event.isComposing) return
  if (!['Enter', ',', ';'].includes(event.key)) return
  event.preventDefault()
  adicionarTexto(rascunho.value)
}

function onPaste(event) {
  const texto = event.clipboardData?.getData('text') || ''
  if (!texto.trim()) return
  event.preventDefault()
  const inicio = event.currentTarget.selectionStart ?? rascunho.value.length
  const fim = event.currentTarget.selectionEnd ?? inicio
  const textoCombinado = `${rascunho.value.slice(0, inicio)}${texto}${rascunho.value.slice(fim)}`
  adicionarTexto(textoCombinado)
}

function onBlur() {
  if (rascunho.value.trim()) adicionarTexto(rascunho.value)
}

function remover(index) {
  if (props.disabled) return
  const proximaLista = emails.value.filter((_, itemIndex) => itemIndex !== index)
  emit('update:modelValue', proximaLista)
  definirValidade('')
}

function focarInput() {
  if (!props.disabled) inputRef.value?.focus()
}
</script>

<template>
  <div class="email-list-field">
    <label v-if="label" :for="inputId">{{ label }}</label>
    <div
      class="email-list-input"
      :class="{
        'email-list-input--invalid': erro,
        'email-list-input--disabled': disabled,
      }"
      @click.self="focarInput"
    >
      <span
        v-for="(email, index) in emails"
        :key="email.toLocaleLowerCase()"
        class="email-list-chip"
      >
        <span>{{ email }}</span>
        <button
          type="button"
          class="email-list-chip__remove"
          :aria-label="`Remover ${email}`"
          :disabled="disabled"
          @click="remover(index)"
        >
          &times;
        </button>
      </span>
      <input
        :id="inputId"
        ref="inputRef"
        class="email-list-input__field"
        type="text"
        inputmode="email"
        autocomplete="email"
        :value="rascunho"
        :placeholder="emails.length ? 'Adicionar outro e-mail' : placeholder"
        :disabled="disabled"
        :aria-invalid="Boolean(erro)"
        :aria-describedby="[hint ? hintId : '', erro ? errorId : ''].filter(Boolean).join(' ') || undefined"
        @input="onInput"
        @keydown="onKeydown"
        @paste="onPaste"
        @blur="onBlur"
      />
    </div>
    <p v-if="hint" :id="hintId" class="email-list-hint">{{ hint }}</p>
    <p v-if="erro" :id="errorId" class="email-list-error" role="alert">{{ erro }}</p>
  </div>
</template>

<style scoped>
.email-list-input {
  display: flex;
  min-height: 42px;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  width: 100%;
  padding: 0.35rem 0.45rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
  cursor: text;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.email-list-input:focus-within {
  border-color: var(--tf-verde-agro);
  box-shadow: 0 0 0 2px rgba(122, 252, 87, 0.25);
}

.email-list-input--invalid {
  border-color: var(--err);
}

.email-list-input--invalid:focus-within {
  box-shadow: 0 0 0 2px rgba(183, 28, 28, 0.15);
}

.email-list-input--disabled {
  background: var(--terra-50);
  cursor: not-allowed;
  opacity: 0.75;
}

.email-list-chip {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  gap: 0.3rem;
  padding: 0.22rem 0.35rem 0.22rem 0.55rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--terra-100);
  color: var(--tf-preto-musgo);
  font-size: 0.82rem;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.email-list-chip__remove {
  display: inline-grid;
  width: 1.15rem;
  height: 1.15rem;
  place-items: center;
  flex: 0 0 auto;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}

.email-list-chip__remove:hover,
.email-list-chip__remove:focus-visible {
  background: rgba(0, 60, 53, 0.12);
  outline: none;
}

.email-list-input__field {
  width: auto;
  min-width: min(220px, 100%);
  flex: 1 1 220px;
  padding: 0.2rem 0.25rem;
  border: 0;
  border-radius: 0;
  box-shadow: none;
  background: transparent;
}

.email-list-input__field:focus {
  border: 0;
  box-shadow: none;
}

.email-list-hint,
.email-list-error {
  margin: 0.3rem 0 0;
  font-size: 0.8rem;
}

.email-list-hint {
  color: var(--text-muted);
}

.email-list-error {
  color: var(--err);
}
</style>
