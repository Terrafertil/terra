<script setup>
import { ref, onMounted, reactive, computed, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { api } from '../api'
import { useUiStore } from '../stores/ui'
import { sanitizeEmailHtml } from '../utils/sanitizeEmail'
import { assuntoVinculado } from '../utils/assuntoEmail'
import {
  ANALISE_PDF_TIMEOUT_MS,
  ENVIO_EMAIL_TIMEOUT_MS,
  classeDeliveryStatus,
  destinatarioDoEnvio,
  feedbackDoEnvio,
  mensagemErroApi,
  rotuloDeliveryStatus,
  rotuloStatusEnvio,
} from '../utils/envioFeedback'

const ui = useUiStore()

const route = useRoute()

const MODELOS_ENVIO = {
  tokio_auto: {
    label: 'Tokio Marine — Auto',
    tipo: 'auto',
    dica: 'CPF e nº da apólice são extraídos do PDF quando possível.',
    extrair: true,
  },
  tokio_moto: {
    label: 'Tokio Marine — Moto',
    tipo: 'moto',
    dica: 'Mesmo layout Tokio; associe ao tipo moto no FULL.',
    extrair: true,
  },
  yelum_casco: {
    label: 'Yelum — Auto Casco',
    tipo: 'auto_casco',
    dica: 'Apólice no formato 31.09.2026.0907318.',
    extrair: true,
  },
  porto_criptografado: {
    label: 'PDF protegido (Porto/SulAmérica)',
    tipo: '',
    dica: 'Informe a senha do PDF abaixo (a que o segurado recebe por e-mail ou SMS).',
    extrair: true,
  },
  sem_texto: {
    label: 'PDF só imagem',
    tipo: '',
    dica: 'Cadastre cliente e apólice manualmente.',
    extrair: false,
  },
}

const modeloAtivo = computed(() => {
  const id = route.query.modelo
  return id && MODELOS_ENVIO[id] ? { id, ...MODELOS_ENVIO[id] } : null
})

const clientes = ref([])
const autos = ref([])
const tipos = ref([])
const corpos = ref([])
const assuntos = ref([])
const assinaturas = ref([])

const clienteId = ref(null)
const criarNovo = ref(false)
const novoCliente = reactive({ nome: '', email: '', cpf: '', cnpj: '', telefone: '' })
const numeroApolice = ref('')
const extrairDados = ref(true)
const tipoCodigo = ref('')
const autoId = ref(null)
const corpoEmailId = ref(null)
const assinaturaId = ref(null)
const arquivo = ref(null)
const boleto = ref(null)
const enviando = ref(false)
const demonstrando = ref(false)
const erro = ref('')
const ok = ref('')
const aviso = ref('')
const ultimoEnvio = ref(null)
const demo = ref(null)
const demoHtmlSeguro = computed(() => sanitizeEmailHtml(demo.value?.html))
const analise = ref(null)
const analisando = ref(false)
const pdfPreviewUrl = ref(null)
const usarOcr = ref(true)
const pdfSenha = ref('')
const mostrarConfirmacao = ref(false)
const confirmouEmail = ref(false)

const emailDestino = computed(() => {
  if (criarNovo.value) return (novoCliente.email || '').trim()
  const c = clientes.value.find((x) => x.id === clienteId.value)
  return c?.email?.trim() || ''
})

const nomeDestino = computed(() => {
  if (criarNovo.value) return (novoCliente.nome || '').trim()
  const c = clientes.value.find((x) => x.id === clienteId.value)
  return c?.nome?.trim() || ''
})

const mostrarCampoSenha = computed(
  () =>
    Boolean(
      analise.value?.requer_senha ||
        analise.value?.senha_invalida ||
        analise.value?.layout === 'porto_sulamerica_criptografado' ||
        modeloAtivo.value?.id === 'porto_criptografado'
    )
)

const autosCliente = computed(() =>
  clienteId.value ? autos.value.filter((a) => a.cliente_id === clienteId.value) : []
)

const tipoSelecionado = computed(() =>
  tipos.value.find((tipo) => tipo.codigo === tipoCodigo.value) || null
)

const corpoSelecionado = computed(() => {
  const id = corpoEmailId.value || tipoSelecionado.value?.corpo_email_id
  return corpos.value.find((corpo) => String(corpo.id) === String(id)) || null
})

const assuntoSelecionado = computed(() =>
  assuntoVinculado(tipoSelecionado.value, assuntos.value)
)

const assuntoPrevisto = computed(() => {
  const texto = assuntoSelecionado.value?.assunto || corpoSelecionado.value?.assunto
  if (!texto) return 'Padrão global do sistema'
  return texto.replaceAll('{numero_apolice}', numeroApolice.value || '')
})

const nomeOrigemAssunto = computed(() => {
  if (assuntoSelecionado.value?.nome) return assuntoSelecionado.value.nome
  if (corpoSelecionado.value?.assunto) return 'Legado do corpo de e-mail'
  return 'Padrão do sistema'
})

async function carregarOpcoes() {
  const [c, t, co, s, a, au] = await Promise.all([
    api.get('/api/clientes', { params: { ativo: true } }),
    api.get('/api/tipos-envio', { params: { ativo: true } }),
    // Assim como o backend, preservamos corpos que foram desativados depois
    // de vinculados, para a prévia e a confirmação permanecerem fiéis.
    api.get('/api/corpos-email'),
    // O backend preserva o assunto já vinculado ao tipo mesmo se ele for
    // desativado depois. Carregamos todos para a confirmação mostrar o texto
    // exato que será enviado.
    api.get('/api/assuntos-email'),
    api.get('/api/assinaturas', { params: { ativo: true } }),
    api.get('/api/autos', { params: { ativo: true } }),
  ])
  clientes.value = c.data
  tipos.value = t.data
  corpos.value = co.data
  assuntos.value = s.data
  assinaturas.value = a.data
  autos.value = au.data
}

watch(clienteId, () => {
  autoId.value = null
})

watch(emailDestino, () => {
  if (mostrarConfirmacao.value) {
    confirmouEmail.value = false
  }
})

watch(extrairDados, (habilitado) => {
  if (habilitado && arquivo.value) analisarArquivo()
  if (!habilitado) analise.value = null
})

function aplicarDadosDaAnalise(data) {
  if (data.numero_apolice) {
    numeroApolice.value = data.numero_apolice
  }
  // Mantém preview em blob: (mesmo origin do ficheiro local). A URL da API
  // só serve como fallback se o blob ainda não existir.

  if (data.cliente_sugerido_id) {
    criarNovo.value = false
    clienteId.value = data.cliente_sugerido_id
    return
  }

  // CPF/CNPJ no PDF, mas cliente ainda não cadastrado → muda para cadastro.
  if (data.cpf || data.cnpj || data.nome) {
    criarNovo.value = true
    clienteId.value = null
    if (data.nome && !novoCliente.nome) novoCliente.nome = data.nome
    if (data.cpf) novoCliente.cpf = data.cpf
    if (data.cnpj) novoCliente.cnpj = data.cnpj
    if (data.telefone && !novoCliente.telefone) novoCliente.telefone = data.telefone
  }
}

async function analisarArquivo() {
  if (!arquivo.value) {
    analise.value = null
    return
  }
  analisando.value = true
  analise.value = null
  erro.value = ''
  const fd = new FormData()
  fd.append('arquivo', arquivo.value)
  fd.append('usar_ocr', usarOcr.value ? 'true' : 'false')
  if (pdfSenha.value) fd.append('pdf_senha', pdfSenha.value)
  try {
    const { data } = await api.post('/api/envios/analisar-pdf', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: ANALISE_PDF_TIMEOUT_MS,
    })
    analise.value = data
    aplicarDadosDaAnalise(data)
  } catch (e) {
    erro.value =
      e.code === 'ECONNABORTED'
        ? 'A análise do PDF excedeu 5 minutos. Tente novamente sem OCR ou verifique o servidor.'
        : mensagemErroApi(e, 'Não foi possível analisar o PDF')
  } finally {
    analisando.value = false
  }
}

function onArquivo(e) {
  if (pdfPreviewUrl.value && String(pdfPreviewUrl.value).startsWith('blob:')) {
    URL.revokeObjectURL(pdfPreviewUrl.value)
  }
  arquivo.value = e.target.files[0] || null
  pdfSenha.value = ''
  if (arquivo.value) {
    // Preview temporário; após a análise troca pela URL same-origin da API.
    pdfPreviewUrl.value = URL.createObjectURL(arquivo.value)
    if (extrairDados.value) analisarArquivo()
  } else {
    pdfPreviewUrl.value = null
    analise.value = null
  }
}
function onBoleto(e)  { boleto.value  = e.target.files[0] || null }

function montarFormData() {
  const fd = new FormData()
  if (arquivo.value) fd.append('arquivo', arquivo.value)
  if (boleto.value)  fd.append('boleto', boleto.value)
  if (criarNovo.value) {
    fd.append('cliente_novo', JSON.stringify(novoCliente))
  } else if (clienteId.value) {
    fd.append('cliente_id', clienteId.value)
  }
  if (numeroApolice.value) fd.append('numero_apolice', numeroApolice.value)
  // A análise automática já ocorreu antes da confirmação e o número da apólice
  // é obrigatório no formulário. Evita repetir extração/OCR durante o POST SMTP.
  fd.append('extrair_dados', 'false')
  if (tipoCodigo.value)    fd.append('tipo_codigo', tipoCodigo.value)
  if (autoId.value)        fd.append('auto_id', autoId.value)
  if (corpoEmailId.value)  fd.append('corpo_email_id', corpoEmailId.value)
  if (assinaturaId.value)  fd.append('assinatura_id', assinaturaId.value)
  if (pdfSenha.value)      fd.append('pdf_senha', pdfSenha.value)
  return fd
}

function validar({ exigirArquivo }) {
  if (exigirArquivo && !arquivo.value) { erro.value = 'Selecione o PDF da apólice'; return false }
  if (!criarNovo.value && !clienteId.value) { erro.value = 'Selecione ou crie um cliente'; return false }
  if (criarNovo.value && (!novoCliente.nome || !novoCliente.email)) {
    erro.value = 'Nome e e-mail do novo cliente são obrigatórios'; return false
  }
  if (!(numeroApolice.value || '').trim()) {
    erro.value = 'Informe o número da apólice'
    return false
  }
  return true
}

function pedirConfirmacao() {
  erro.value = ''
  if (!validar({ exigirArquivo: true })) return
  if (!emailDestino.value) {
    erro.value = 'Informe o e-mail do destinatário'
    return
  }
  confirmouEmail.value = false
  mostrarConfirmacao.value = true
}

function fecharConfirmacao() {
  mostrarConfirmacao.value = false
}

async function enviar() {
  erro.value = ''; ok.value = ''; aviso.value = ''; ultimoEnvio.value = null
  if (!validar({ exigirArquivo: true })) {
    mostrarConfirmacao.value = false
    return
  }
  if (analisando.value) {
    erro.value = 'Aguarde o fim da análise do PDF antes de enviar'
    mostrarConfirmacao.value = false
    return
  }
  enviando.value = true
  const destinoConfirmado = emailDestino.value
  let recebeuResposta = false
  try {
    const { data } = await api.post('/api/envios/manual', montarFormData(), {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: ENVIO_EMAIL_TIMEOUT_MS,
    })
    recebeuResposta = true
    ultimoEnvio.value = data
    const feedback = feedbackDoEnvio(data, { fallbackDestinatario: destinoConfirmado })
    if (feedback.tipo === 'erro') erro.value = feedback.texto
    else if (feedback.tipo === 'aviso') aviso.value = feedback.texto
    else ok.value = feedback.texto
  } catch (e) {
    erro.value =
      e.code === 'ECONNABORTED'
        ? 'O servidor não confirmou o resultado em 5 minutos. Consulte o Histórico antes de tentar novamente, pois o SMTP pode ter aceitado o envio.'
        : mensagemErroApi(e, 'Falha no envio')
  } finally {
    enviando.value = false
    mostrarConfirmacao.value = false
  }

  if (recebeuResposta) {
    try {
      await carregarOpcoes()
    } catch {
      const msg = 'O resultado acima é válido, mas não foi possível atualizar as opções da tela.'
      aviso.value = aviso.value ? `${aviso.value} ${msg}` : msg
    }
  }
}

async function confirmarEEnviar() {
  if (!confirmouEmail.value) {
    erro.value = 'Marque a confirmação do e-mail antes de enviar'
    return
  }
  await enviar()
}

async function demonstrar() {
  erro.value = ''; ok.value = ''; aviso.value = ''; demo.value = null; ultimoEnvio.value = null
  if (!validar({ exigirArquivo: false })) return
  demonstrando.value = true
  try {
    const { data } = await api.post('/api/envios/demonstrar', montarFormData(), {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    demo.value = data
  } catch (e) {
    erro.value = mensagemErroApi(e, 'Não foi possível gerar a demonstração')
  } finally {
    demonstrando.value = false
  }
}

function aplicarModeloDaUrl() {
  const m = modeloAtivo.value
  if (!m) return
  if (m.tipo) tipoCodigo.value = m.tipo
  extrairDados.value = m.extrair
}

watch(() => route.query.modelo, aplicarModeloDaUrl)

onMounted(async () => {
  await carregarOpcoes()
  aplicarModeloDaUrl()
  if (modeloAtivo.value?.id === 'sem_texto') usarOcr.value = true
})
</script>

<template>
  <div>
    <h2>Envio Manual</h2>
    <p class="text-muted">
      Selecione um cliente existente (ou cadastre na hora), envie o PDF e o sistema dispara o e-mail imediatamente.
      <RouterLink to="/tutorial">Tutorial</RouterLink>
    </p>

    <div v-if="modeloAtivo" class="alert alert-warn">
      <strong>Modelo: {{ modeloAtivo.label }}</strong> — {{ modeloAtivo.dica }}
    </div>

    <div v-if="erro" class="alert alert-err">{{ erro }}</div>
    <div v-if="ok"   class="alert alert-ok">{{ ok }}</div>
    <div v-if="aviso" class="alert alert-warn">{{ aviso }}</div>

    <form @submit.prevent="pedirConfirmacao">
      <div class="card">
        <h3>Cliente</h3>
        <div class="flex gap-4 mb-2">
          <label style="display:flex; align-items:center; gap:.4rem;">
            <input type="radio" :value="false" v-model="criarNovo" /> Selecionar existente
          </label>
          <label style="display:flex; align-items:center; gap:.4rem;">
            <input type="radio" :value="true" v-model="criarNovo" /> Cadastrar novo agora
          </label>
        </div>

        <div v-if="!criarNovo">
          <label>Cliente</label>
          <select v-model="clienteId">
            <option :value="null">— selecione —</option>
            <option v-for="c in clientes" :key="c.id" :value="c.id">
              {{ c.nome }} — {{ c.email }}
            </option>
          </select>
        </div>

        <div v-else class="row">
          <div><label>Nome *</label><input v-model="novoCliente.nome" required /></div>
          <div><label>E-mail *</label><input v-model="novoCliente.email" type="email" required /></div>
          <div><label>CPF</label><input v-model="novoCliente.cpf" /></div>
          <div><label>CNPJ</label><input v-model="novoCliente.cnpj" /></div>
          <div><label>Telefone</label><input v-model="novoCliente.telefone" /></div>
        </div>
      </div>

      <div class="card">
        <h3>Arquivo &amp; mensagem</h3>
        <div class="row">
          <div>
            <label>PDF da apólice *</label>
            <input type="file" accept="application/pdf" @change="onArquivo" />
            <label v-if="ui.ocrDisponivel" class="ocr-toggle mt-2" style="display:flex;align-items:center;gap:.4rem;font-weight:500">
              <input
                v-model="usarOcr"
                type="checkbox"
                @change="arquivo && extrairDados && analisarArquivo()"
              />
              Usar OCR se o PDF for só imagem
            </label>
          </div>
          <div v-if="mostrarCampoSenha" class="senha-pdf-box">
            <label>Senha do PDF *</label>
            <input
              v-model="pdfSenha"
              type="password"
              autocomplete="off"
              placeholder="Senha enviada pelo segurado/seguradora"
              @keyup.enter="analisarArquivo"
            />
            <button type="button" class="btn btn-ghost btn-sm mt-2" :disabled="analisando" @click="analisarArquivo">
              Aplicar senha e analisar
            </button>
            <p class="text-muted m-0 mt-2" style="font-size:0.85rem">
              Modo FULL: crie <code>nome-do-arquivo.pdf.senha</code> na mesma pasta, com a senha numa linha.
            </p>
          </div>
          <div>
            <label>Boleto (opcional)</label>
            <input type="file" accept="application/pdf" @change="onBoleto" />
          </div>
          <div>
            <label>Nº da apólice *</label>
            <input
              v-model="numeroApolice"
              required
              placeholder="Preenchido automaticamente quando o PDF permitir"
            />
          </div>
          <div>
            <label>Tipo de envio</label>
            <select v-model="tipoCodigo">
              <option value="">Sem tipo específico</option>
              <option v-for="t in tipos" :key="t.id" :value="t.codigo">{{ t.nome }}</option>
            </select>
          </div>
        </div>

        <div class="row mt-2">
          <div>
            <label>Extrair dados do PDF?</label>
            <select v-model="extrairDados">
              <option :value="true">Sim</option>
              <option :value="false">Não</option>
            </select>
          </div>
          <div v-if="autosCliente.length">
            <label>Veículo (auto)</label>
            <select v-model="autoId">
              <option :value="null">— nenhum —</option>
              <option v-for="a in autosCliente" :key="a.id" :value="a.id">
                {{ a.placa }} {{ a.marca ? '· ' + a.marca : '' }} {{ a.modelo ? '· ' + a.modelo : '' }}
              </option>
            </select>
          </div>
          <div>
            <label>Corpo de e-mail</label>
            <select v-model="corpoEmailId">
              <option :value="null">Padrão (do tipo de envio)</option>
              <option v-for="c in corpos" :key="c.id" :value="c.id">
                {{ c.nome }}{{ c.ativo ? '' : ' (inativo)' }}
              </option>
            </select>
          </div>
          <div>
            <label>Assinatura</label>
            <select v-model="assinaturaId">
              <option :value="null">Sem assinatura</option>
              <option v-for="a in assinaturas" :key="a.id" :value="a.id">{{ a.nome }}</option>
            </select>
          </div>
        </div>

        <div v-if="pdfPreviewUrl || analisando || analise" class="pdf-preview-panel mt-4">
          <h4 class="m-0 mb-2">Pré-visualização do PDF</h4>
          <p v-if="analisando" class="text-muted">A analisar layout e dados…</p>
          <div v-if="pdfPreviewUrl" class="pdf-preview-row">
            <div class="pdf-preview-frame">
              <iframe :src="pdfPreviewUrl" class="pdf-iframe" title="Pré-visualização do PDF" />
              <p class="text-muted pdf-preview-fallback">
                Se o PDF não aparecer aqui,
                <a :href="pdfPreviewUrl" target="_blank" rel="noopener">abra em nova aba</a>.
              </p>
            </div>
            <div v-if="analise" class="pdf-analise-dados">
              <p><strong>Layout:</strong> {{ analise.layout }}</p>
              <p v-if="analise.seguradora"><strong>Seguradora:</strong> {{ analise.seguradora }}</p>
              <p v-if="analise.produto"><strong>Produto:</strong> {{ analise.produto }}</p>
              <p><strong>Nome:</strong> {{ analise.nome || '—' }}</p>
              <p><strong>CPF:</strong> {{ analise.cpf || '—' }}</p>
              <p><strong>CNPJ:</strong> {{ analise.cnpj || '—' }}</p>
              <p><strong>Telefone:</strong> {{ analise.telefone || '—' }}</p>
              <p><strong>Apólice:</strong> {{ analise.numero_apolice || '—' }}</p>
              <p v-if="analise.cliente_sugerido_nome">
                <strong>Cliente sugerido:</strong> {{ analise.cliente_sugerido_nome }}
              </p>
              <p v-else-if="analise.cpf || analise.cnpj || analise.nome" class="text-muted">
                Cliente não encontrado — formulário mudou para <strong>Cadastrar novo</strong>.
              </p>
              <p v-if="analise.ocr_usado" class="badge enviado">OCR utilizado</p>
              <p v-if="analise.requer_senha" class="badge pendente">Senha necessária</p>
              <p v-if="analise.senha_invalida" class="badge erro">Senha incorreta</p>
              <ul v-if="analise.avisos?.length" class="analise-avisos">
                <li v-for="(av, i) in analise.avisos" :key="i">{{ av }}</li>
              </ul>
              <details v-if="analise.amostra_texto" class="mt-2">
                <summary class="text-muted">Amostra do texto extraído</summary>
                <pre class="amostra-texto">{{ analise.amostra_texto }}</pre>
              </details>
            </div>
          </div>
        </div>

        <p class="text-muted mt-2" style="font-size: 0.9rem">
          O corpo e o assunto são definidos separadamente no tipo de envio.
          Administre-os em <RouterLink to="/corpos-email">Corpos de E-mail</RouterLink>,
          <RouterLink to="/assuntos">Assuntos</RouterLink> e
          <RouterLink to="/tipos-envio">Tipos de Envio</RouterLink>.
        </p>
        <div v-if="tipoSelecionado" class="card-inline configuracao-email-resumo">
          <strong>Configuração herdada de “{{ tipoSelecionado.nome }}”</strong>
          <span>
            Corpo:
            <strong>{{ corpoSelecionado?.nome || 'Padrão do sistema' }}</strong>
            <template v-if="corpoEmailId"> (substituído manualmente)</template>
          </span>
          <span>
            Assunto:
            <strong>{{ nomeOrigemAssunto }}</strong>
            — {{ assuntoPrevisto }}
          </span>
        </div>
      </div>

      <div class="flex gap-2">
        <button type="submit" class="btn btn-accent" :disabled="enviando || analisando">
          {{ enviando ? 'Enviando...' : analisando ? 'A analisar PDF…' : 'Enviar agora' }}
        </button>
        <button type="button" class="btn btn-ghost" :disabled="demonstrando || analisando" @click="demonstrar">
          {{ demonstrando ? 'Gerando...' : 'Demonstrar e-mail' }}
        </button>
      </div>
      <p class="text-muted mt-2" style="font-size: 0.85rem">
        <strong>Demonstrar e-mail</strong> só mostra a prévia na tela — não envia nada.
        Para disparar de verdade, use <strong>Enviar agora</strong>.
      </p>
    </form>

    <div v-if="mostrarConfirmacao" class="modal-backdrop" @click.self="fecharConfirmacao">
      <div class="modal-card" role="dialog" aria-labelledby="confirmar-envio-titulo">
        <h3 id="confirmar-envio-titulo">Confirmar envio</h3>
        <p>Verifique o destinatário antes de enviar a apólice:</p>
        <p><strong>Cliente:</strong> {{ nomeDestino || '—' }}</p>
        <p class="confirm-email">{{ emailDestino }}</p>
        <p><strong>Assunto:</strong> {{ assuntoPrevisto }}</p>
        <label style="display: flex; align-items: flex-start; gap: 0.5rem; font-weight: 500; margin-top: 1rem">
          <input v-model="confirmouEmail" type="checkbox" />
          Confirmo que o e-mail acima está correto
        </label>
        <div class="flex gap-2 mt-4">
          <button
            type="button"
            class="btn btn-accent"
            :disabled="enviando || !confirmouEmail"
            @click="confirmarEEnviar"
          >
            {{ enviando ? 'Enviando…' : 'Enviar para este e-mail' }}
          </button>
          <button type="button" class="btn btn-ghost" @click="fecharConfirmacao">Voltar</button>
        </div>
      </div>
    </div>

    <div v-if="demo" class="card mt-4">
      <h3>Demonstração do e-mail</h3>
      <p class="text-muted" style="font-size: 0.9rem">
        Esta é apenas uma prévia. Nenhum e-mail foi enviado.
      </p>
      <p><strong>De:</strong> {{ demo.de }}</p>
      <p><strong>Para:</strong> {{ demo.para }}</p>
      <p><strong>Assunto:</strong> {{ demo.assunto }}</p>
      <hr />
      <div class="email-preview" v-html="demoHtmlSeguro"></div>
    </div>

    <div v-if="ultimoEnvio" class="card mt-4">
      <h3>Último envio</h3>
      <p>ID: <strong>{{ ultimoEnvio.id }}</strong></p>
      <p>Para: <strong>{{ destinatarioDoEnvio(ultimoEnvio) }}</strong></p>
      <p>Assunto: {{ ultimoEnvio.assunto_email || '—' }}</p>
      <p>
        Envio SMTP:
        <span class="badge" :class="ultimoEnvio.status">
          {{ rotuloStatusEnvio(ultimoEnvio.status) }}
        </span>
      </p>
      <p v-if="ultimoEnvio.deduplicado" class="alert alert-warn">
        Registro já existente; nenhum novo e-mail foi disparado nesta tentativa.
      </p>
      <p v-if="ultimoEnvio.delivery_status">
        Entrega (Brevo):
        <span class="badge" :class="classeDeliveryStatus(ultimoEnvio.delivery_status)">
          {{ rotuloDeliveryStatus(ultimoEnvio.delivery_status) }}
        </span>
      </p>
      <p v-else class="text-muted">Entrega (Brevo): sem confirmação.</p>
      <p v-if="ultimoEnvio.delivery_updated_at" class="text-muted">
        Atualizado em {{ new Date(ultimoEnvio.delivery_updated_at).toLocaleString() }}
      </p>
      <p v-if="ultimoEnvio.erro_msg" class="text-muted">Erro: {{ ultimoEnvio.erro_msg }}</p>
    </div>
  </div>
</template>

<style scoped>
.email-preview {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem;
  background: #fafafa;
}
.card-inline {
  margin-top: 0.75rem;
  padding: 0.85rem 1rem;
  background: var(--terra-50, #f7faf9);
  border: 1px solid var(--border, #e0d8d0);
  border-radius: var(--radius, 8px);
}
.configuracao-email-resumo {
  display: grid;
  gap: 0.35rem;
  font-size: 0.9rem;
}
</style>
