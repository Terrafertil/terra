<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { sanitizeEmailHtml } from '../utils/sanitizeEmail'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  placeholder: {
    type: String,
    default: 'Escreva o corpo do e-mail…',
  },
})

const emit = defineEmits(['update:modelValue'])

const editorRef = ref(null)
const rawEditorRef = ref(null)
const modo = ref('visual')
const htmlFonte = ref(props.modelValue || '')
const corAtual = ref('#000000')
const corFundoAtual = ref('#fff59d')
const fonteAtual = ref('Arial')
const tamanhoAtual = ref('3')
const estados = ref({})

let selecaoSalva = null
let estruturaDocumento = { antes: '', depois: '' }

const comandosComEstado = [
  'bold',
  'italic',
  'underline',
  'strikeThrough',
  'insertOrderedList',
  'insertUnorderedList',
  'justifyLeft',
  'justifyCenter',
  'justifyRight',
]

function separarDocumento(html) {
  const resultado = String(html || '').match(
    /^([\s\S]*?<body\b[^>]*>)([\s\S]*?)(<\/body\s*>[\s\S]*)$/i,
  )

  if (!resultado) {
    return { antes: '', conteudo: String(html || ''), depois: '' }
  }

  return {
    antes: resultado[1],
    conteudo: resultado[2],
    depois: resultado[3],
  }
}

function emitirHtml(novoHtml) {
  htmlFonte.value = novoHtml
  emit('update:modelValue', novoHtml)
}

function carregarEditorVisual() {
  const partes = separarDocumento(htmlFonte.value)
  estruturaDocumento = { antes: partes.antes, depois: partes.depois }
  const conteudoSeguro = sanitizeEmailHtml(partes.conteudo)

  if (editorRef.value && editorRef.value.innerHTML !== conteudoSeguro) {
    editorRef.value.innerHTML = conteudoSeguro
  }
}

function sincronizarEditorVisual() {
  if (!editorRef.value) return
  const conteudo = editorRef.value.innerHTML
  emitirHtml(`${estruturaDocumento.antes}${conteudo}${estruturaDocumento.depois}`)
}

function aoDigitarHtml(event) {
  emitirHtml(event.target.value)
}

function estaDentroDoEditor(no) {
  const editor = editorRef.value
  if (!editor || !no) return false
  return no === editor || editor.contains(no.nodeType === Node.TEXT_NODE ? no.parentNode : no)
}

function guardarSelecao() {
  if (modo.value !== 'visual') return
  const selecao = window.getSelection()
  if (!selecao || !selecao.rangeCount) return

  const intervalo = selecao.getRangeAt(0)
  if (estaDentroDoEditor(intervalo.commonAncestorContainer)) {
    selecaoSalva = intervalo.cloneRange()
  }
}

function posicionarCursorNoFim() {
  const editor = editorRef.value
  if (!editor) return null

  const intervalo = document.createRange()
  intervalo.selectNodeContents(editor)
  intervalo.collapse(false)
  const selecao = window.getSelection()
  selecao.removeAllRanges()
  selecao.addRange(intervalo)
  return intervalo
}

function restaurarSelecao() {
  const editor = editorRef.value
  if (!editor) return null

  editor.focus()
  const selecao = window.getSelection()
  if (!selecao) return null

  if (selecaoSalva && estaDentroDoEditor(selecaoSalva.commonAncestorContainer)) {
    try {
      selecao.removeAllRanges()
      selecao.addRange(selecaoSalva)
      return selecaoSalva
    } catch {
      selecaoSalva = null
    }
  }

  return posicionarCursorNoFim()
}

function atualizarEstados() {
  if (modo.value !== 'visual' || !editorRef.value) return

  const proximos = {}
  for (const comando of comandosComEstado) {
    try {
      proximos[comando] = document.queryCommandState(comando)
    } catch {
      proximos[comando] = false
    }
  }
  estados.value = proximos
}

function executar(comando, valor = null) {
  restaurarSelecao()
  try {
    document.execCommand(comando, false, valor)
  } catch {
    return
  }
  guardarSelecao()
  sincronizarEditorVisual()
  atualizarEstados()
}

function limparFormatacao() {
  executar('removeFormat')
  executar('unlink')
}

function escaparHtml(texto) {
  return String(texto)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function escaparAtributo(texto) {
  return escaparHtml(texto).replaceAll('`', '&#096;')
}

function conteudoInserivel(html) {
  return separarDocumento(html).conteudo
}

function inserirNoHtmlBruto(conteudo) {
  const editor = rawEditorRef.value
  const inicio = editor && typeof editor.selectionStart === 'number'
    ? editor.selectionStart
    : htmlFonte.value.length
  const fim = editor && typeof editor.selectionEnd === 'number'
    ? editor.selectionEnd
    : inicio
  const novoHtml = htmlFonte.value.slice(0, inicio) + conteudo + htmlFonte.value.slice(fim)
  emitirHtml(novoHtml)

  nextTick(() => {
    if (!rawEditorRef.value) return
    const novaPosicao = inicio + conteudo.length
    rawEditorRef.value.focus()
    rawEditorRef.value.setSelectionRange(novaPosicao, novaPosicao)
  })
}

function inserirFragmentoVisual(html) {
  const editor = editorRef.value
  if (!editor) return

  const intervalo = restaurarSelecao() || posicionarCursorNoFim()
  if (!intervalo) return

  const fragmento = intervalo.createContextualFragment(
    sanitizeEmailHtml(conteudoInserivel(html)),
  )
  const ultimoNo = fragmento.lastChild
  intervalo.deleteContents()
  intervalo.insertNode(fragmento)

  if (ultimoNo) {
    intervalo.setStartAfter(ultimoNo)
    intervalo.collapse(true)
    const selecao = window.getSelection()
    selecao.removeAllRanges()
    selecao.addRange(intervalo)
    selecaoSalva = intervalo.cloneRange()
  }

  sincronizarEditorVisual()
  atualizarEstados()
}

function insertHtml(html) {
  const conteudo = String(html || '')
  if (!conteudo) return

  if (modo.value === 'html') {
    inserirNoHtmlBruto(conteudo)
    return
  }

  inserirFragmentoVisual(conteudo)
}

function insertText(texto) {
  const conteudo = String(texto || '')
  if (!conteudo) return

  if (modo.value === 'html') {
    inserirNoHtmlBruto(conteudo)
    return
  }

  inserirFragmentoVisual(escaparHtml(conteudo).replace(/\r?\n/g, '<br>'))
}

function inserirLink() {
  guardarSelecao()
  const informado = window.prompt('Endereço do link (URL ou e-mail):', 'https://')
  if (!informado?.trim()) return

  let endereco = informado.trim()
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(endereco)) {
    endereco = `mailto:${endereco}`
  } else if (!/^(https?:|mailto:|tel:)/i.test(endereco)) {
    endereco = `https://${endereco}`
  }

  if (!/^(https?:|mailto:|tel:)/i.test(endereco)) return

  const intervalo = restaurarSelecao()
  if (!intervalo) return

  if (intervalo.collapsed) {
    inserirFragmentoVisual(
      `<a href="${escaparAtributo(endereco)}">${escaparHtml(endereco)}</a>`,
    )
  } else {
    executar('createLink', endereco)
  }
}

function aplicarCor(event) {
  corAtual.value = event.target.value
  executar('foreColor', corAtual.value)
}

function aplicarCorFundo(event) {
  corFundoAtual.value = event.target.value
  executar('hiliteColor', corFundoAtual.value)
}

function aplicarFonte(event) {
  fonteAtual.value = event.target.value
  executar('fontName', fonteAtual.value)
}

function aplicarTamanho(event) {
  tamanhoAtual.value = event.target.value
  executar('fontSize', tamanhoAtual.value)
}

function mudarModo(novoModo) {
  if (novoModo === modo.value) return

  if (modo.value === 'visual') sincronizarEditorVisual()
  modo.value = novoModo
  selecaoSalva = null

  if (novoModo === 'visual') {
    nextTick(() => {
      carregarEditorVisual()
      editorRef.value?.focus()
    })
  } else {
    nextTick(() => rawEditorRef.value?.focus())
  }
}

function focus() {
  if (modo.value === 'html') rawEditorRef.value?.focus()
  else editorRef.value?.focus()
}

function aoColar(event) {
  const transferencia = event.clipboardData
  if (!transferencia) return

  const html = transferencia.getData('text/html')
  if (html) {
    event.preventDefault()
    inserirFragmentoVisual(sanitizeEmailHtml(html))
    return
  }

  const texto = transferencia.getData('text/plain')
  if (!texto) return
  event.preventDefault()
  insertText(texto)
}

function aoMudarSelecao() {
  guardarSelecao()
  atualizarEstados()
}

watch(
  () => props.modelValue,
  (novoValor) => {
    const valor = novoValor || ''
    if (valor === htmlFonte.value) return
    htmlFonte.value = valor
    if (modo.value === 'visual') nextTick(carregarEditorVisual)
  },
)

onMounted(() => {
  carregarEditorVisual()
  document.addEventListener('selectionchange', aoMudarSelecao)
})

onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', aoMudarSelecao)
})

defineExpose({
  focus,
  insertHtml,
  insertText,
  mudarModo,
})
</script>

<template>
  <div class="rich-email-editor">
    <div class="editor-header">
      <div v-if="modo === 'visual'" class="format-toolbar" role="toolbar" aria-label="Formatação do corpo do e-mail">
        <div class="toolbar-group toolbar-group--selects">
          <select
            v-model="fonteAtual"
            class="tool-select tool-select--font"
            title="Fonte"
            aria-label="Fonte"
            @mousedown="guardarSelecao"
            @change="aplicarFonte"
          >
            <option value="Arial">Arial</option>
            <option value="Georgia">Georgia</option>
            <option value="Tahoma">Tahoma</option>
            <option value="Trebuchet MS">Trebuchet</option>
            <option value="Verdana">Verdana</option>
            <option value="Courier New">Monoespaçada</option>
          </select>
          <select
            v-model="tamanhoAtual"
            class="tool-select tool-select--size"
            title="Tamanho do texto"
            aria-label="Tamanho do texto"
            @mousedown="guardarSelecao"
            @change="aplicarTamanho"
          >
            <option value="1">Pequeno</option>
            <option value="3">Normal</option>
            <option value="5">Grande</option>
            <option value="7">Muito grande</option>
          </select>
        </div>

        <div class="toolbar-divider" aria-hidden="true"></div>

        <div class="toolbar-group">
          <button type="button" class="tool-btn" title="Desfazer" aria-label="Desfazer" @mousedown.prevent @click="executar('undo')">↶</button>
          <button type="button" class="tool-btn" title="Refazer" aria-label="Refazer" @mousedown.prevent @click="executar('redo')">↷</button>
        </div>

        <div class="toolbar-divider" aria-hidden="true"></div>

        <div class="toolbar-group">
          <button
            type="button"
            class="tool-btn tool-btn--bold"
            :class="{ active: estados.bold }"
            title="Negrito"
            aria-label="Negrito"
            :aria-pressed="Boolean(estados.bold)"
            @mousedown.prevent
            @click="executar('bold')"
          >B</button>
          <button
            type="button"
            class="tool-btn tool-btn--italic"
            :class="{ active: estados.italic }"
            title="Itálico"
            aria-label="Itálico"
            :aria-pressed="Boolean(estados.italic)"
            @mousedown.prevent
            @click="executar('italic')"
          >I</button>
          <button
            type="button"
            class="tool-btn tool-btn--underline"
            :class="{ active: estados.underline }"
            title="Sublinhado"
            aria-label="Sublinhado"
            :aria-pressed="Boolean(estados.underline)"
            @mousedown.prevent
            @click="executar('underline')"
          >U</button>
          <button
            type="button"
            class="tool-btn tool-btn--strike"
            :class="{ active: estados.strikeThrough }"
            title="Tachado"
            aria-label="Tachado"
            :aria-pressed="Boolean(estados.strikeThrough)"
            @mousedown.prevent
            @click="executar('strikeThrough')"
          >S</button>
          <label class="color-tool" title="Cor do texto" @mousedown="guardarSelecao">
            <span class="color-tool__letter" :style="{ borderBottomColor: corAtual }">A</span>
            <input v-model="corAtual" type="color" aria-label="Cor do texto" @input="aplicarCor" />
          </label>
          <label class="color-tool" title="Cor de destaque" @mousedown="guardarSelecao">
            <span class="color-tool__highlight" :style="{ backgroundColor: corFundoAtual }">A</span>
            <input v-model="corFundoAtual" type="color" aria-label="Cor de destaque" @input="aplicarCorFundo" />
          </label>
        </div>

        <div class="toolbar-divider" aria-hidden="true"></div>

        <div class="toolbar-group">
          <button
            type="button"
            class="tool-btn tool-btn--text"
            :class="{ active: estados.insertOrderedList }"
            title="Lista numerada"
            aria-label="Lista numerada"
            :aria-pressed="Boolean(estados.insertOrderedList)"
            @mousedown.prevent
            @click="executar('insertOrderedList')"
          >1.</button>
          <button
            type="button"
            class="tool-btn"
            :class="{ active: estados.insertUnorderedList }"
            title="Lista com marcadores"
            aria-label="Lista com marcadores"
            :aria-pressed="Boolean(estados.insertUnorderedList)"
            @mousedown.prevent
            @click="executar('insertUnorderedList')"
          >•</button>
        </div>

        <div class="toolbar-divider" aria-hidden="true"></div>

        <div class="toolbar-group">
          <button
            type="button"
            class="tool-btn"
            :class="{ active: estados.justifyLeft }"
            title="Alinhar à esquerda"
            aria-label="Alinhar à esquerda"
            :aria-pressed="Boolean(estados.justifyLeft)"
            @mousedown.prevent
            @click="executar('justifyLeft')"
          >≡</button>
          <button
            type="button"
            class="tool-btn tool-btn--center"
            :class="{ active: estados.justifyCenter }"
            title="Centralizar"
            aria-label="Centralizar"
            :aria-pressed="Boolean(estados.justifyCenter)"
            @mousedown.prevent
            @click="executar('justifyCenter')"
          >≡</button>
          <button
            type="button"
            class="tool-btn tool-btn--right"
            :class="{ active: estados.justifyRight }"
            title="Alinhar à direita"
            aria-label="Alinhar à direita"
            :aria-pressed="Boolean(estados.justifyRight)"
            @mousedown.prevent
            @click="executar('justifyRight')"
          >≡</button>
          <button type="button" class="tool-btn" title="Diminuir recuo" aria-label="Diminuir recuo" @mousedown.prevent @click="executar('outdent')">⇤</button>
          <button type="button" class="tool-btn" title="Aumentar recuo" aria-label="Aumentar recuo" @mousedown.prevent @click="executar('indent')">⇥</button>
        </div>

        <div class="toolbar-divider" aria-hidden="true"></div>

        <div class="toolbar-group">
          <button type="button" class="tool-btn" title="Inserir link" aria-label="Inserir link" @mousedown.prevent @click="inserirLink">🔗</button>
          <button type="button" class="tool-btn tool-btn--text" title="Citação" aria-label="Citação" @mousedown.prevent @click="executar('formatBlock', 'blockquote')">“ ”</button>
          <button type="button" class="tool-btn tool-btn--text" title="Limpar formatação" aria-label="Limpar formatação" @mousedown.prevent @click="limparFormatacao">Tx</button>
        </div>
      </div>

      <div class="mode-switch" aria-label="Modo do editor">
        <button
          type="button"
          class="mode-btn"
          :class="{ active: modo === 'visual' }"
          :aria-pressed="modo === 'visual'"
          @click="mudarModo('visual')"
        >Visual</button>
        <button
          type="button"
          class="mode-btn"
          :class="{ active: modo === 'html' }"
          :aria-pressed="modo === 'html'"
          @click="mudarModo('html')"
        >HTML</button>
      </div>
    </div>

    <div
      v-show="modo === 'visual'"
      ref="editorRef"
      class="editor-content"
      contenteditable="true"
      role="textbox"
      aria-multiline="true"
      :aria-label="placeholder"
      :data-placeholder="placeholder"
      spellcheck="true"
      @input="sincronizarEditorVisual"
      @blur="guardarSelecao"
      @keyup="guardarSelecao"
      @mouseup="guardarSelecao"
      @paste="aoColar"
    ></div>

    <textarea
      v-if="modo === 'html'"
      ref="rawEditorRef"
      class="raw-editor"
      :value="htmlFonte"
      rows="16"
      spellcheck="false"
      aria-label="Código HTML do corpo do e-mail"
      placeholder="Ex.: <p>Prezado(a)…</p>"
      @input="aoDigitarHtml"
    ></textarea>

    <div class="editor-footer">
      <span v-if="modo === 'visual'">As quebras e linhas em branco criadas com Enter serão mantidas no e-mail.</span>
      <span v-else>Modo avançado: edite o código dos modelos HTML legados.</span>
    </div>
  </div>
</template>

<style scoped>
.rich-email-editor {
  overflow: hidden;
  width: 100%;
  border: 1px solid var(--border, #e3e4e3);
  border-radius: var(--radius, 8px);
  background: #fff;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.rich-email-editor:focus-within {
  border-color: var(--accent, #00b94e);
  box-shadow: 0 0 0 3px rgba(0, 185, 78, 0.12);
}

.editor-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.55rem;
  padding: 0.45rem 0.55rem;
  border-bottom: 1px solid var(--border, #e3e4e3);
  background: var(--terra-50, #f7faf9);
}

.format-toolbar {
  display: flex;
  flex: 1;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.2rem;
  min-width: 0;
}

.toolbar-group {
  display: inline-flex;
  align-items: center;
  gap: 0.1rem;
}

.toolbar-group--selects {
  flex-wrap: wrap;
}

.tool-select {
  height: 2rem;
  max-width: 8rem;
  padding: 0 1.55rem 0 0.45rem;
  border: 0;
  border-radius: 5px;
  background-color: transparent;
  color: #273a37;
  font-size: 0.78rem;
  cursor: pointer;
}

.tool-select:hover,
.tool-select:focus-visible {
  background-color: #e4ebe8;
  outline: none;
}

.tool-select--size { max-width: 6.5rem; }

.toolbar-divider {
  width: 1px;
  height: 1.45rem;
  margin: 0 0.15rem;
  background: var(--border, #e3e4e3);
}

.tool-btn,
.color-tool {
  display: inline-grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #273a37;
  font: inherit;
  line-height: 1;
  cursor: pointer;
}

.tool-btn:hover,
.color-tool:hover,
.tool-btn.active {
  background: #e4ebe8;
}

.tool-btn:focus-visible,
.color-tool:focus-within,
.mode-btn:focus-visible {
  outline: 2px solid var(--accent, #00b94e);
  outline-offset: 1px;
}

.tool-btn--bold { font-weight: 800; }
.tool-btn--italic { font-style: italic; font-family: Georgia, serif; }
.tool-btn--underline { text-decoration: underline; }
.tool-btn--strike { text-decoration: line-through; }
.tool-btn--text { width: 2.25rem; font-size: 0.78rem; font-weight: 700; }
.tool-btn--center { text-align: center; padding-inline: 0.35rem; }
.tool-btn--right { text-align: right; padding-left: 0.65rem; }

.color-tool {
  position: relative;
}

.color-tool__letter {
  padding: 0 0.2rem 0.12rem;
  border-bottom: 3px solid #000;
  font-weight: 700;
}

.color-tool__highlight {
  padding: 0.08rem 0.22rem;
  border-radius: 2px;
  font-weight: 700;
}

.color-tool input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.mode-switch {
  display: inline-flex;
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid var(--border, #e3e4e3);
  border-radius: 6px;
  background: #fff;
}

.mode-btn {
  padding: 0.38rem 0.55rem;
  border: 0;
  background: transparent;
  color: var(--text-muted, #444c49);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
}

.mode-btn + .mode-btn {
  border-left: 1px solid var(--border, #e3e4e3);
}

.mode-btn.active {
  background: var(--tf-preto-musgo, #003c35);
  color: #fff;
}

.editor-content,
.raw-editor {
  display: block;
  width: 100%;
  min-height: 300px;
  padding: 1rem 1.1rem;
  border: 0;
  outline: 0;
  background: #fff;
  color: #202124;
  font-family: Arial, sans-serif;
  font-size: 14px;
  line-height: 1.5;
}

.editor-content {
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.editor-content:empty::before {
  color: #777;
  content: attr(data-placeholder);
  pointer-events: none;
}

.raw-editor {
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 0.86rem;
  line-height: 1.5;
}

.editor-footer {
  padding: 0.38rem 0.7rem;
  border-top: 1px solid var(--border, #e3e4e3);
  background: var(--terra-50, #f7faf9);
  color: var(--text-muted, #444c49);
  font-size: 0.76rem;
}

@media (max-width: 700px) {
  .editor-header {
    align-items: stretch;
    flex-direction: column-reverse;
  }

  .mode-switch {
    align-self: flex-end;
  }

  .toolbar-divider {
    display: none;
  }
}
</style>
