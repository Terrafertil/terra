<script setup>
import { ref, onMounted, reactive, computed, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'

const lista = ref([])
const placeholders = ref([])
const modelos = ref([])
const personalizados = ref([])
const painelVars = ref(true)
const abaAtalhos = ref('variaveis')
const carregando = ref(false)
const erro = ref('')
const ok = ref('')

const form = reactive({
  nome: '',
  descricao: '',
  assunto: '',
  html: '',
  ativo: true,
})
const editandoId = ref(null)
const textareaRef = ref(null)

const novoAtalho = reactive({ nome: '', descricao: '', html: '' })
const salvandoAtalhos = ref(false)

const titulo = computed(() => (editandoId.value ? 'Editar corpo de e-mail' : 'Novo corpo de e-mail'))

const placeholdersAgrupados = computed(() => {
  const m = new Map()
  for (const p of placeholders.value) {
    const g = p.grupo || 'Outros'
    if (!m.has(g)) m.set(g, [])
    m.get(g).push(p)
  }
  return [...m.entries()]
})

function vazio() {
  return { nome: '', descricao: '', assunto: '', html: '', ativo: true }
}

async function carregar() {
  carregando.value = true
  erro.value = ''
  try {
    const [c, at] = await Promise.all([
      api.get('/api/corpos-email'),
      api.get('/api/corpos-email/atalhos'),
    ])
    lista.value = c.data
    placeholders.value = at.data?.placeholders || []
    modelos.value = at.data?.modelos || []
    personalizados.value = at.data?.personalizados || []
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao carregar'
  } finally {
    carregando.value = false
  }
}

function editar(row) {
  editandoId.value = row.id
  form.nome = row.nome
  form.descricao = row.descricao || ''
  form.assunto = row.assunto || ''
  form.html = row.html || ''
  form.ativo = row.ativo
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function cancelar() {
  editandoId.value = null
  Object.assign(form, vazio())
}

function textoPlaceholder(chave) {
  return '{{ ' + chave + ' }}'
}

function inserirHtml(texto) {
  const token = texto
  const el = textareaRef.value
  if (el && typeof el.selectionStart === 'number') {
    const start = el.selectionStart
    const end = el.selectionEnd
    const v = form.html
    form.html = v.slice(0, start) + token + v.slice(end)
    nextTick(() => {
      el.focus()
      const pos = start + token.length
      el.setSelectionRange(pos, pos)
    })
  } else {
    form.html += token
  }
}

function inserirNoHtml(chave) {
  inserirHtml(`{{ ${chave} }}`)
}

function aplicarModelo(m) {
  if (m.html) inserirHtml(m.html)
  if (m.tipo_codigo_sugerido && !form.descricao) {
    form.descricao = `Modelo: ${m.label}`
  }
  ok.value = `Bloco "${m.label}" inserido.`
}

async function salvarPersonalizados() {
  salvandoAtalhos.value = true
  erro.value = ''
  try {
    const { data } = await api.put('/api/corpos-email/atalhos-personalizados', {
      atalhos: personalizados.value,
    })
    personalizados.value = data.personalizados || []
    ok.value = 'Atalhos personalizados guardados.'
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao guardar atalhos'
  } finally {
    salvandoAtalhos.value = false
  }
}

function adicionarAtalhoPersonalizado() {
  if (!novoAtalho.nome.trim() || !novoAtalho.html.trim()) {
    erro.value = 'Nome e HTML são obrigatórios para criar um atalho.'
    return
  }
  personalizados.value.push({
    id: `p_${Date.now().toString(36)}`,
    nome: novoAtalho.nome.trim(),
    descricao: novoAtalho.descricao?.trim() || null,
    html: novoAtalho.html,
  })
  novoAtalho.nome = ''
  novoAtalho.descricao = ''
  novoAtalho.html = ''
  salvarPersonalizados()
}

function removerAtalhoPersonalizado(id) {
  personalizados.value = personalizados.value.filter((a) => a.id !== id)
  salvarPersonalizados()
}

async function salvar() {
  erro.value = ''
  ok.value = ''
  if (!form.nome.trim()) {
    erro.value = 'Nome é obrigatório'
    return
  }
  try {
    if (editandoId.value) {
      await api.put(`/api/corpos-email/${editandoId.value}`, {
        nome: form.nome.trim(),
        descricao: form.descricao?.trim() || null,
        assunto: form.assunto?.trim() || null,
        html: form.html,
        ativo: form.ativo,
      })
      ok.value = 'Corpo de e-mail atualizado'
    } else {
      await api.post('/api/corpos-email', {
        nome: form.nome.trim(),
        descricao: form.descricao?.trim() || null,
        assunto: form.assunto?.trim() || null,
        html: form.html,
        ativo: form.ativo,
      })
      ok.value = 'Corpo criado. Associe-o a um tipo de envio para o FULL usar automaticamente.'
    }
    cancelar()
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao salvar'
  }
}

async function remover(row) {
  if (!confirm(`Remover o modelo "${row.nome}"?`)) return
  try {
    await api.delete(`/api/corpos-email/${row.id}`)
    ok.value = 'Removido'
    await carregar()
  } catch (e) {
    erro.value = e.response?.data?.detail || 'Erro ao remover'
  }
}

onMounted(carregar)
</script>

<template>
  <div>
    <h2>Corpos de e-mail</h2>
    <p class="text-muted">
      Modelos HTML com variáveis <code v-pre>{{ nome }}</code>. Use os atalhos por modelo de apólice
      ou crie os seus — visíveis para toda a equipe.
      <RouterLink to="/tutorial">Ver tutorial</RouterLink>
    </p>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok" class="alert alert-ok">{{ ok }}</div>

    <div class="card">
      <h3>{{ titulo }}</h3>
      <form @submit.prevent="salvar">
        <div class="row">
          <div><label>Nome *</label><input v-model="form.nome" maxlength="120" /></div>
          <div><label>Assunto (opcional)</label><input v-model="form.assunto" maxlength="255" /></div>
        </div>
        <div class="mt-2">
          <label>Descrição</label>
          <input v-model="form.descricao" maxlength="255" />
        </div>

        <div class="mt-2">
          <label>HTML</label>
          <textarea
            ref="textareaRef"
            v-model="form.html"
            rows="16"
            class="html-editor"
            placeholder="Ex.: <p>Prezado(a) …</p>"
          ></textarea>
        </div>

        <div class="corpo-vars-toolbar">
          <span class="text-muted" style="font-size: 0.9rem">Atalhos</span>
          <label class="switch-label">
            <input v-model="painelVars" type="checkbox" class="switch-input" />
            <span class="switch-slider" aria-hidden="true"></span>
            <span class="switch-state">{{ painelVars ? 'Atalhos visíveis' : 'Mostrar atalhos' }}</span>
          </label>
        </div>

        <div v-show="painelVars" class="painel-placeholders card-inline">
          <div class="atalhos-tabs">
            <button
              type="button"
              class="btn btn-sm"
              :class="abaAtalhos === 'variaveis' ? 'btn-accent' : 'btn-ghost'"
              @click="abaAtalhos = 'variaveis'"
            >
              Variáveis
            </button>
            <button
              type="button"
              class="btn btn-sm"
              :class="abaAtalhos === 'modelos' ? 'btn-accent' : 'btn-ghost'"
              @click="abaAtalhos = 'modelos'"
            >
              Por modelo ({{ modelos.length }})
            </button>
            <button
              type="button"
              class="btn btn-sm"
              :class="abaAtalhos === 'meus' ? 'btn-accent' : 'btn-ghost'"
              @click="abaAtalhos = 'meus'"
            >
              Meus atalhos ({{ personalizados.length }})
            </button>
          </div>

          <template v-if="abaAtalhos === 'variaveis'">
            <p class="text-muted m-0 mb-2" style="font-size: 0.85rem">
              Clique para inserir na posição do cursor.
            </p>
            <div v-for="[grupo, itens] in placeholdersAgrupados" :key="grupo" class="ph-grupo">
              <strong class="ph-grupo-titulo">{{ grupo }}</strong>
              <div class="ph-botoes">
                <button
                  v-for="p in itens"
                  :key="p.chave"
                  type="button"
                  class="btn btn-ghost btn-sm ph-btn"
                  @click="inserirNoHtml(p.chave)"
                >
                  {{ p.label }} · <code>{{ textoPlaceholder(p.chave) }}</code>
                </button>
              </div>
            </div>
          </template>

          <template v-else-if="abaAtalhos === 'modelos'">
            <p class="text-muted m-0 mb-2" style="font-size: 0.85rem">
              Blocos prontos conforme os PDFs da pasta Modelos (Tokio, Yelum, manual…).
            </p>
            <div class="atalhos-modelos-grid">
              <div v-for="m in modelos" :key="m.id" class="atalho-modelo-card">
                <strong>{{ m.label }}</strong>
                <span v-if="m.full_automatico === true" class="badge enviado">FULL</span>
                <span v-else-if="m.full_automatico === false" class="badge pendente">Manual</span>
                <p class="text-muted m-0" style="font-size: 0.82rem">{{ m.descricao }}</p>
                <button type="button" class="btn btn-accent btn-sm mt-2" @click="aplicarModelo(m)">
                  Inserir bloco
                </button>
              </div>
            </div>
          </template>

          <template v-else>
            <p class="text-muted m-0 mb-2" style="font-size: 0.85rem">
              Crie trechos reutilizáveis — ficam guardados no servidor para toda a equipe.
            </p>
            <div v-if="personalizados.length" class="ph-botoes mb-2">
              <div
                v-for="a in personalizados"
                :key="a.id"
                class="atalho-personalizado-item"
              >
                <button type="button" class="btn btn-ghost btn-sm" @click="inserirHtml(a.html)">
                  {{ a.nome }}
                </button>
                <button
                  type="button"
                  class="btn btn-danger btn-sm"
                  title="Remover"
                  @click="removerAtalhoPersonalizado(a.id)"
                >
                  ×
                </button>
              </div>
            </div>
            <div class="card-inline criar-atalho-form">
              <h4 class="m-0 mb-2" style="font-size: 0.95rem">Criar atalho</h4>
              <div class="row">
                <div><label>Nome *</label><input v-model="novoAtalho.nome" maxlength="120" /></div>
                <div><label>Descrição</label><input v-model="novoAtalho.descricao" maxlength="255" /></div>
              </div>
              <div class="mt-2">
                <label>HTML *</label>
                <textarea v-model="novoAtalho.html" rows="4" placeholder="<p>…</p>" />
              </div>
              <button
                type="button"
                class="btn btn-primary btn-sm mt-2"
                :disabled="salvandoAtalhos"
                @click="adicionarAtalhoPersonalizado"
              >
                Guardar atalho
              </button>
            </div>
          </template>
        </div>

        <div class="mt-2 flex gap-2 items-center">
          <label class="m-0"><input type="checkbox" v-model="form.ativo" /> Ativo</label>
        </div>
        <div class="flex gap-2 mt-2">
          <button type="submit" class="btn btn-accent">{{ editandoId ? 'Salvar' : 'Cadastrar' }}</button>
          <button v-if="editandoId" type="button" class="btn btn-ghost" @click="cancelar">Cancelar</button>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="flex gap-2 items-center mb-2">
        <h3 class="m-0">Modelos salvos</h3>
        <span class="spacer"></span>
        <button class="btn btn-ghost btn-sm" :disabled="carregando" @click="carregar">Atualizar</button>
      </div>
      <table v-if="lista.length" class="table">
        <thead>
          <tr>
            <th>Nome</th>
            <th>Assunto</th>
            <th>Ativo</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in lista" :key="r.id">
            <td>{{ r.nome }}</td>
            <td>{{ r.assunto || '—' }}</td>
            <td>{{ r.ativo ? 'Sim' : 'Não' }}</td>
            <td>
              <button class="btn btn-ghost btn-sm" @click="editar(r)">Editar</button>
              <button class="btn btn-danger btn-sm" @click="remover(r)">Remover</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-muted">Nenhum modelo.</p>
    </div>
  </div>
</template>

<style scoped>
.corpo-vars-toolbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  margin-top: 1rem;
}
.card-inline {
  margin-top: 0.75rem;
  padding: 0.85rem 1rem;
  background: var(--terra-50, #f7faf9);
  border: 1px solid var(--border, #e0d8d0);
  border-radius: var(--radius, 8px);
}
.ph-grupo { margin-bottom: 0.75rem; }
.ph-grupo-titulo { font-size: 0.82rem; color: var(--tf-preto-musgo, #003c35); }
.ph-botoes { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.35rem; }
.ph-btn { text-align: left; }
.html-editor {
  width: 100%;
  font-family: ui-monospace, monospace;
  font-size: 0.88rem;
  line-height: 1.45;
}
.atalhos-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.75rem;
}
.atalhos-modelos-grid {
  display: grid;
  gap: 0.65rem;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
}
.atalho-modelo-card {
  padding: 0.65rem 0.75rem;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.atalho-modelo-card strong { display: block; margin-bottom: 0.25rem; }
.atalho-modelo-card .badge { margin-left: 0.35rem; font-size: 0.7rem; vertical-align: middle; }
.atalho-personalizado-item {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
}
.criar-atalho-form {
  background: #fff;
}

.switch-label {
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
  cursor: pointer;
  user-select: none;
  font-size: 0.92rem;
  padding: 0.3rem 0.45rem;
  border: 1px solid var(--border, #e0d8d0);
  border-radius: 999px;
  background: #fff;
}
.switch-input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.switch-slider {
  position: relative;
  width: 2.9rem;
  height: 1.55rem;
  background: linear-gradient(180deg, #d8d0ca 0%, #c2b7af 100%);
  border-radius: 999px;
  transition: background 0.2s ease, box-shadow 0.2s ease;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.08);
}
.switch-slider::after {
  content: '';
  position: absolute;
  top: 0.19rem;
  left: 0.19rem;
  width: 1.17rem;
  height: 1.17rem;
  background: #fff;
  border-radius: 50%;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.22);
  transition: transform 0.22s ease;
}
.switch-slider::before {
  content: none !important;
}
.switch-input:checked + .switch-slider {
  background: linear-gradient(180deg, #d08d60 0%, var(--accent, #c67b4a) 100%);
}
.switch-input:checked + .switch-slider::after {
  transform: translateX(1.35rem);
}
.switch-state {
  min-width: 7.8rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--tf-preto-musgo, #003c35);
}
</style>
