<script setup>
import { ref, onMounted, reactive, computed, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { api } from '../api'
import { useUiStore } from '../stores/ui'
import { sanitizeEmailHtml } from '../utils/sanitizeEmail'
import { assuntoVinculado } from '../utils/assuntoEmail'
import { renderizarAssunto, rotuloParcelamento } from '../utils/templateEmail'
import {
  erroNomeAnexoPdf,
  montarNomeAnexoPdf,
  normalizarExtensaoPdf,
} from '../utils/nomeArquivoPdf'
import EmailListInput from '../components/EmailListInput.vue'
import CapaOrderSelector from '../components/CapaOrderSelector.vue'
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
const capas = ref([])
const configuracaoEmail = ref({ smtp_from_name: '', email_subject_default: '' })

const clienteId = ref(null)
const criarNovo = ref(false)
const novoCliente = reactive({
  nome: '',
  email: '',
  destinatarios_adicionais: [],
  cpf: '',
  cnpj: '',
  telefone: '',
})
const destinatariosManuais = ref([])
const numeroApolice = ref('')
const formaPagamento = ref('')
const parcelamento = ref(null)
const numeroProposta = ref('')
const itemSegurado = ref('')
const extrairDados = ref(true)
const tipoCodigo = ref('')
const autoId = ref(null)
const corpoEmailId = ref(null)
const assinaturaId = ref(null)
const arquivo = ref(null)
const boleto = ref(null)
const nomeArquivoApolice = ref('')
const nomeArquivoBoleto = ref('')
const nomeApoliceEditado = ref(false)
const nomeBoletoEditado = ref(false)
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
const capasIniciaisIds = ref([])
const capasFinaisIds = ref([])

const clienteSelecionado = computed(() =>
  clientes.value.find((x) => x.id === clienteId.value) || null
)

function emailsUnicos(...listas) {
  const vistos = new Set()
  const resultado = []
  for (const email of listas.flat()) {
    const normalizado = String(email || '').trim()
    const chave = normalizado.toLocaleLowerCase()
    if (!normalizado || vistos.has(chave)) continue
    vistos.add(chave)
    resultado.push(normalizado)
  }
  return resultado
}

const destinatariosFixos = computed(() => {
  if (criarNovo.value) {
    return emailsUnicos(novoCliente.email, novoCliente.destinatarios_adicionais)
  }
  return emailsUnicos(
    clienteSelecionado.value?.email,
    clienteSelecionado.value?.destinatarios_adicionais || [],
  )
})

const destinatariosEnvio = computed(() =>
  emailsUnicos(destinatariosFixos.value, destinatariosManuais.value)
)

const limiteDestinatariosManuais = computed(() =>
  Math.max(0, 20 - destinatariosFixos.value.length)
)

const emailDestino = computed(() => destinatariosEnvio.value.join(', '))

const nomeDestino = computed(() => {
  if (criarNovo.value) return (novoCliente.nome || '').trim()
  return clienteSelecionado.value?.nome?.trim() || ''
})

const nomeApoliceAutomatico = computed(() =>
  montarNomeAnexoPdf(nomeDestino.value, 'Apólice', numeroApolice.value),
)

const nomeBoletoAutomatico = computed(() =>
  montarNomeAnexoPdf(nomeDestino.value, 'Boleto', numeroApolice.value),
)

const nomeApoliceFinal = computed(() =>
  normalizarExtensaoPdf(nomeArquivoApolice.value || nomeApoliceAutomatico.value),
)

const nomeBoletoFinal = computed(() =>
  normalizarExtensaoPdf(nomeArquivoBoleto.value || nomeBoletoAutomatico.value),
)

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

const autoSelecionado = computed(() =>
  autos.value.find((auto) => String(auto.id) === String(autoId.value)) || null
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

const contextoAssunto = computed(() => ({
  nome: nomeDestino.value,
  email: destinatariosFixos.value[0] || '',
  cpf: criarNovo.value ? novoCliente.cpf || '' : clienteSelecionado.value?.cpf || '',
  cnpj: criarNovo.value ? novoCliente.cnpj || '' : clienteSelecionado.value?.cnpj || '',
  telefone: criarNovo.value ? novoCliente.telefone || '' : clienteSelecionado.value?.telefone || '',
  numero_apolice: numeroApolice.value || '',
  forma_pagamento: formaPagamento.value || '',
  parcelamento: rotuloParcelamento(parcelamento.value),
  numero_proposta: numeroProposta.value || '',
  item_segurado: itemSegurado.value || analise.value?.produto || '',
  seguradora: analise.value?.seguradora || '',
  produto: analise.value?.produto || '',
  layout_apolice: analise.value?.layout || '',
  tipo_codigo: tipoCodigo.value || '',
  tipo_envio: 'MANUAL',
  data_envio: new Intl.DateTimeFormat('pt-BR').format(new Date()),
  placa: autoSelecionado.value?.placa || '',
  marca: autoSelecionado.value?.marca || '',
  modelo: autoSelecionado.value?.modelo || '',
  ano: autoSelecionado.value?.ano || '',
  from_name: configuracaoEmail.value.smtp_from_name || '',
}))

const assuntoPrevisto = computed(() => {
  const texto = assuntoSelecionado.value?.assunto || corpoSelecionado.value?.assunto
  if (!texto) {
    return renderizarAssunto(
      configuracaoEmail.value.email_subject_default || 'Envio de Apólice - {numero_apolice}',
      contextoAssunto.value,
    )
  }
  return renderizarAssunto(texto, contextoAssunto.value)
})

const nomeOrigemAssunto = computed(() => {
  if (assuntoSelecionado.value?.nome) return assuntoSelecionado.value.nome
  if (corpoSelecionado.value?.assunto) return 'Legado do corpo de e-mail'
  return 'Padrão do sistema'
})

function nomesCapas(ids) {
  return ids.map((id) => capas.value.find((capa) => Number(capa.id) === Number(id))?.nome || `#${id}`)
}

async function carregarOpcoes() {
  const [c, t, co, s, a, au, cp, status] = await Promise.all([
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
    api.get('/api/capas', { params: { ativo: true } }),
    api.get('/api/status'),
  ])
  clientes.value = c.data
  tipos.value = t.data
  corpos.value = co.data
  assuntos.value = s.data
  assinaturas.value = a.data
  autos.value = au.data
  capas.value = cp.data
  configuracaoEmail.value = status.data || configuracaoEmail.value
}

watch(clienteId, () => {
  autoId.value = null
})

watch(
  nomeApoliceAutomatico,
  (nome) => {
    if (!nomeApoliceEditado.value) nomeArquivoApolice.value = nome
  },
  { immediate: true },
)

watch(
  nomeBoletoAutomatico,
  (nome) => {
    if (!nomeBoletoEditado.value) nomeArquivoBoleto.value = nome
  },
  { immediate: true },
)

watch(tipoCodigo, () => {
  capasIniciaisIds.value = [...(tipoSelecionado.value?.capas_iniciais_ids || [])]
  capasFinaisIds.value = [...(tipoSelecionado.value?.capas_finais_ids || [])]
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

function normalizarSenhaPdf(valor) {
  return String(valor || '').replace(/\s+/g, '')
}

function onSenhaInput(event) {
  pdfSenha.value = normalizarSenhaPdf(event.target.value)
}

function restaurarCapasDoTipo() {
  capasIniciaisIds.value = [...(tipoSelecionado.value?.capas_iniciais_ids || [])]
  capasFinaisIds.value = [...(tipoSelecionado.value?.capas_finais_ids || [])]
}

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
  const senha = normalizarSenhaPdf(pdfSenha.value)
  if (senha) fd.append('pdf_senha', senha)
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
function onBoleto(e) {
  boleto.value = e.target.files[0] || null
  if (boleto.value && !nomeBoletoEditado.value) {
    nomeArquivoBoleto.value = nomeBoletoAutomatico.value
  }
}

function usarNomeAutomatico(tipo) {
  if (tipo === 'apolice') {
    nomeApoliceEditado.value = false
    nomeArquivoApolice.value = nomeApoliceAutomatico.value
    return
  }
  nomeBoletoEditado.value = false
  nomeArquivoBoleto.value = nomeBoletoAutomatico.value
}

function finalizarEdicaoNome(tipo) {
  if (tipo === 'apolice') {
    if (!nomeArquivoApolice.value.trim()) return usarNomeAutomatico('apolice')
    nomeArquivoApolice.value = normalizarExtensaoPdf(nomeArquivoApolice.value)
    return
  }
  if (!nomeArquivoBoleto.value.trim()) return usarNomeAutomatico('boleto')
  nomeArquivoBoleto.value = normalizarExtensaoPdf(nomeArquivoBoleto.value)
}

function montarFormData() {
  const fd = new FormData()
  if (arquivo.value) fd.append('arquivo', arquivo.value)
  if (boleto.value)  fd.append('boleto', boleto.value)
  if (arquivo.value) fd.append('nome_arquivo_apolice', nomeApoliceFinal.value)
  if (boleto.value)  fd.append('nome_arquivo_boleto', nomeBoletoFinal.value)
  if (criarNovo.value) {
    fd.append('cliente_novo', JSON.stringify(novoCliente))
  } else if (clienteId.value) {
    fd.append('cliente_id', clienteId.value)
  }
  if (numeroApolice.value) fd.append('numero_apolice', numeroApolice.value)
  fd.append('destinatarios_adicionais', JSON.stringify(destinatariosManuais.value))
  if (formaPagamento.value) fd.append('forma_pagamento', formaPagamento.value)
  if (parcelamento.value) fd.append('parcelamento', String(parcelamento.value))
  if (numeroProposta.value) fd.append('numero_proposta', numeroProposta.value.trim())
  if (itemSegurado.value) fd.append('item_segurado', itemSegurado.value.trim())
  if (analise.value?.seguradora) fd.append('seguradora', analise.value.seguradora)
  if (analise.value?.produto) fd.append('produto', analise.value.produto)
  if (analise.value?.layout) fd.append('layout_apolice', analise.value.layout)
  fd.append('capas_iniciais_ids', JSON.stringify(capasIniciaisIds.value))
  fd.append('capas_finais_ids', JSON.stringify(capasFinaisIds.value))
  // A análise automática já ocorreu antes da confirmação e o número da apólice
  // é obrigatório no formulário. Evita repetir extração/OCR durante o POST SMTP.
  fd.append('extrair_dados', 'false')
  if (tipoCodigo.value)    fd.append('tipo_codigo', tipoCodigo.value)
  if (autoId.value)        fd.append('auto_id', autoId.value)
  if (corpoEmailId.value)  fd.append('corpo_email_id', corpoEmailId.value)
  if (assinaturaId.value)  fd.append('assinatura_id', assinaturaId.value)
  const senha = normalizarSenhaPdf(pdfSenha.value)
  if (senha)               fd.append('pdf_senha', senha)
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
  const erroNomeApolice = erroNomeAnexoPdf(nomeApoliceFinal.value)
  if (erroNomeApolice) {
    erro.value = `Nome do PDF da apólice: ${erroNomeApolice}`
    return false
  }
  if (boleto.value) {
    const erroNomeBoleto = erroNomeAnexoPdf(nomeBoletoFinal.value)
    if (erroNomeBoleto) {
      erro.value = `Nome do PDF do boleto: ${erroNomeBoleto}`
      return false
    }
  }
  if (destinatariosEnvio.value.length > 20) {
    erro.value = 'Use no máximo 20 destinatários no total'
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
          <p v-if="clienteSelecionado?.destinatarios_adicionais?.length" class="text-muted mt-2 m-0">
            Fixos deste cliente: {{ clienteSelecionado.destinatarios_adicionais.join(', ') }}
          </p>
        </div>

        <div v-else class="row">
          <div><label>Nome *</label><input v-model="novoCliente.nome" required /></div>
          <div><label>E-mail *</label><input v-model="novoCliente.email" type="email" required /></div>
          <div><label>CPF</label><input v-model="novoCliente.cpf" /></div>
          <div><label>CNPJ</label><input v-model="novoCliente.cnpj" /></div>
          <div><label>Telefone</label><input v-model="novoCliente.telefone" /></div>
        </div>
        <div v-if="criarNovo" class="mt-2">
          <EmailListInput
            v-model="novoCliente.destinatarios_adicionais"
            label="Destinatários adicionais fixos do novo cliente"
            hint="Ficarão salvos no cadastro e receberão os próximos envios deste cliente."
            :max="19"
          />
        </div>
        <div class="mt-2">
          <EmailListInput
            v-model="destinatariosManuais"
            label="Destinatários adicionais somente deste envio"
            hint="Não serão gravados no cadastro do cliente."
            :max="limiteDestinatariosManuais"
          />
        </div>
        <div v-if="destinatariosEnvio.length" class="destinatarios-resumo mt-2">
          <strong>Receberão este e-mail ({{ destinatariosEnvio.length }}):</strong>
          <span v-for="email in destinatariosEnvio" :key="email.toLocaleLowerCase()">{{ email }}</span>
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
              :value="pdfSenha"
              type="password"
              autocomplete="off"
              placeholder="Senha enviada pelo segurado/seguradora"
              @input="onSenhaInput"
              @keydown.enter.prevent="analisarArquivo"
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

        <div class="nomes-anexos mt-2">
          <div>
            <label>Nome do PDF da apólice enviado *</label>
            <div class="nome-anexo-edicao">
              <input
                v-model="nomeArquivoApolice"
                maxlength="180"
                required
                @input="nomeApoliceEditado = true"
                @blur="finalizarEdicaoNome('apolice')"
              />
              <button type="button" class="btn btn-ghost btn-sm" @click="usarNomeAutomatico('apolice')">
                Usar nome + apólice
              </button>
            </div>
            <small class="text-muted">Nome que o cliente verá no anexo e que será usado no backup.</small>
          </div>
          <div v-if="boleto">
            <label>Nome do PDF do boleto enviado *</label>
            <div class="nome-anexo-edicao">
              <input
                v-model="nomeArquivoBoleto"
                maxlength="180"
                required
                @input="nomeBoletoEditado = true"
                @blur="finalizarEdicaoNome('boleto')"
              />
              <button type="button" class="btn btn-ghost btn-sm" @click="usarNomeAutomatico('boleto')">
                Usar nome + apólice
              </button>
            </div>
            <small class="text-muted">O boleto continua como um anexo separado.</small>
          </div>
        </div>

        <h4 class="mt-4 mb-2">Dados da proposta</h4>
        <div class="row">
          <div>
            <label>Forma de pagamento</label>
            <select v-model="formaPagamento">
              <option value="">— não informada —</option>
              <option value="À vista">À vista</option>
              <option value="Boleto">Boleto</option>
              <option value="Débito">Débito</option>
              <option value="Cartão">Cartão</option>
            </select>
          </div>
          <div>
            <label>Parcelamento</label>
            <select v-model="parcelamento">
              <option :value="null">— não informado —</option>
              <option v-for="quantidade in 12" :key="quantidade" :value="quantidade">
                {{ quantidade === 1 ? '1 vez' : quantidade + ' vezes' }}
              </option>
            </select>
          </div>
          <div>
            <label>Nº da proposta</label>
            <input v-model="numeroProposta" maxlength="100" />
          </div>
          <div>
            <label>Item segurado</label>
            <input
              v-model="itemSegurado"
              list="itens-segurados"
              maxlength="150"
              placeholder="Ex.: veículo, trator, colheitadeira"
            />
            <datalist id="itens-segurados">
              <option value="Veículo" />
              <option value="Trator" />
              <option value="Colheitadeira" />
              <option value="Escavadeira" />
              <option value="Imóvel" />
              <option value="Máquina agrícola" />
            </datalist>
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

        <div class="capas-envio mt-4">
          <div class="flex items-center gap-2 mb-2">
            <h4 class="m-0">Composição do PDF</h4>
            <span class="spacer" />
            <button type="button" class="btn btn-ghost btn-sm" @click="restaurarCapasDoTipo">
              Restaurar padrão do tipo
            </button>
          </div>
          <p class="text-muted m-0 mb-2">
            Escolha vários padrões e organize a ordem. A apólice ficará entre os dois grupos.
            <RouterLink to="/capa">Gerenciar biblioteca</RouterLink>
          </p>
          <div class="capas-envio-grid">
            <CapaOrderSelector
              v-model="capasIniciaisIds"
              :capas="capas"
              label="Antes da apólice"
            />
            <CapaOrderSelector
              v-model="capasFinaisIds"
              :capas="capas"
              label="Depois da apólice (capa final)"
            />
          </div>
          <p class="ordem-pdf text-muted m-0 mt-2">
            Ordem final:
            {{ [...nomesCapas(capasIniciaisIds), nomeApoliceFinal, ...nomesCapas(capasFinaisIds)].join(' → ') }}
          </p>
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
        <p>Verifique todos os destinatários antes de enviar a apólice:</p>
        <p><strong>Cliente:</strong> {{ nomeDestino || '—' }}</p>
        <ul class="confirm-email-list">
          <li v-for="email in destinatariosEnvio" :key="email.toLocaleLowerCase()">{{ email }}</li>
        </ul>
        <p><strong>Assunto:</strong> {{ assuntoPrevisto }}</p>
        <p v-if="formaPagamento || parcelamento || numeroProposta || itemSegurado">
          <strong>Proposta:</strong>
          {{ [numeroProposta, itemSegurado, formaPagamento, rotuloParcelamento(parcelamento)].filter(Boolean).join(' · ') }}
        </p>
        <p>
          <strong>PDF da apólice:</strong> {{ nomeApoliceFinal }}
          ({{ capasIniciaisIds.length }} capa(s) antes · apólice · {{ capasFinaisIds.length }} capa(s) depois)
        </p>
        <p v-if="boleto"><strong>PDF do boleto:</strong> {{ nomeBoletoFinal }}</p>
        <label style="display: flex; align-items: flex-start; gap: 0.5rem; font-weight: 500; margin-top: 1rem">
          <input v-model="confirmouEmail" type="checkbox" />
          Confirmo que todos os e-mails acima estão corretos
        </label>
        <div class="flex gap-2 mt-4">
          <button
            type="button"
            class="btn btn-accent"
            :disabled="enviando || !confirmouEmail"
            @click="confirmarEEnviar"
          >
            {{ enviando ? 'Enviando…' : 'Enviar para estes destinatários' }}
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
      <p>PDF da apólice: {{ ultimoEnvio.nome_arquivo_final || '—' }}</p>
      <p v-if="ultimoEnvio.nome_boleto">PDF do boleto: {{ ultimoEnvio.nome_boleto }}</p>
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
.destinatarios-resumo {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
  padding: 0.65rem;
  border-radius: var(--radius);
  background: var(--terra-50);
}
.destinatarios-resumo span {
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  font-size: 0.82rem;
}
.capas-envio {
  padding: 0.9rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--terra-50);
}
.capas-envio-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}
.nomes-anexos {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}
.nome-anexo-edicao { display: flex; gap: 0.5rem; align-items: center; }
.nome-anexo-edicao input { flex: 1; }
.nome-anexo-edicao button { white-space: nowrap; }
.ordem-pdf { overflow-wrap: anywhere; }
.confirm-email-list {
  padding: 0.65rem 0.65rem 0.65rem 2rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--terra-50);
  font-weight: 700;
}
@media (max-width: 850px) {
  .capas-envio-grid, .nomes-anexos { grid-template-columns: 1fr; }
  .nome-anexo-edicao { align-items: stretch; flex-direction: column; }
}
</style>
