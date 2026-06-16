<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'

const emit = defineEmits(['fechar'])
const ui = useUiStore()
const auth = useAuthStore()
const router = useRouter()
const passo = ref(0)

const passos = [
  {
    titulo: 'Bem-vindo ao painel Terra Fértil',
    texto:
      'Este sistema envia apólices por e-mail no modo automático (FULL) ou manual. O tour mostra o essencial — incluindo como montar os e-mails com atalhos e HTML.',
    rota: '/dashboard',
    largo: false,
  },
  {
    titulo: 'Dashboard e modo FULL',
    texto: 'Acompanhe estatísticas, alertas do FULL e o interruptor do envio automático.',
    rota: '/dashboard',
    dicas: [
      'Defina o horário de execução do FULL no cartão abaixo dos indicadores.',
      'Os alertas do FULL aparecem aqui quando um PDF não puder ser processado.',
    ],
  },
  {
    titulo: 'Modo SOC — resposta a incidente de segurança',
    texto:
      'O Modo SOC (Security Operations Center) é o «botão de emergência» do sistema. Não é para uso diário: serve quando há suspeita de invasão, acesso indevido ao servidor ou PDF malicioso na pasta de envios.',
    rota: '/dashboard',
    soc: true,
    largo: true,
    dicas: [
      'Apenas administradores podem ativar o SOC. Utilizadores normais veem se está ativo ou inativo e por quem foi ativado.',
      'Ao ativar: todos os envios param (FULL e manual) e os dados dos clientes são recifrados com chave de emergência — diferente da senha do .env.',
      'Só o Admin Diretor (utilizador admindiretor) pode desativar o modo SOC, com a chave de emergência guardada no cofre.',
      'PDFs suspeitos na pasta não serão enviados enquanto o bloqueio estiver ativo.',
    ],
    avisos: [
      'Guarde a chave de emergência fora do servidor (cofre da equipe de TI). Sem ela, não há como voltar à operação normal.',
      'Desative o SOC assim que o incidente estiver controlado — os dados voltam à criptografia padrão do .env.',
    ],
  },
  {
    titulo: 'Envio manual e modelos de PDF',
    texto:
      'Em Envio Manual, escolha o modelo (Tokio Auto/Moto, Yelum, PDF com senha, etc.). O sistema analisa o PDF e sugere cliente e apólice.',
    rota: '/envio',
    dicas: [
      'PDF protegido: informe a senha no campo amarelo antes de analisar.',
      'O Tutorial no menu lista todos os layouts suportados.',
    ],
  },
  {
    titulo: 'Corpos de e-mail — visão geral',
    texto:
      'Cada tipo de envio (auto, moto, residencial…) pode ter um HTML próprio. O painel Corpos de E-mail é onde você monta esse texto.',
    rota: '/corpos-email',
    dicas: [
      'Cadastre um corpo com nome claro (ex.: «Tokio Auto — padrão 2026»).',
      'Depois associe o corpo ao tipo em Tipos de Envio — assim o FULL usa o HTML certo.',
    ],
  },
  {
    titulo: 'Atalhos: variáveis automáticas',
    texto:
      'Ative «Atalhos visíveis» no editor. Na aba Variáveis, cada botão insere um campo que o sistema preenche no envio.',
    rota: '/corpos-email',
    largo: true,
    dicas: [
      'Formato: chaves duplas com o nome do campo (veja exemplos abaixo).',
      'Exemplos úteis: nome do cliente, número da apólice, placa, remetente.',
      'Clique no botão — o texto é inserido onde estiver o cursor no campo HTML.',
    ],
    exemplos: [
      {
        titulo: 'Variável simples',
        codigo: '<p>Prezado(a) <strong>{{ nome }}</strong>,</p>',
      },
      {
        titulo: 'Apólice opcional (só aparece se existir)',
        codigo:
          '{% if numero_apolice %}Apólice nº <strong>{{ numero_apolice }}</strong>{% endif %}',
      },
    ],
  },
  {
    titulo: 'Atalhos: blocos por modelo de apólice',
    texto:
      'Na aba «Por modelo», use «Inserir bloco» para colar um e-mail já adaptado ao layout (Tokio, Yelum, manual…).',
    rota: '/corpos-email',
    dicas: [
      'Ajuste o texto depois de inserir — o bloco é ponto de partida, não regra fixa.',
      'Badges FULL / Manual indicam se o layout costuma rodar na pasta automática.',
      'Mantenha as variáveis e os trechos {% if … %} — o sistema usa Jinja2 para montar o e-mail.',
    ],
  },
  {
    titulo: 'Atalhos: criar os seus (HTML)',
    texto:
      'Na aba «Meus atalhos», crie trechos HTML reutilizáveis (rodapé, aviso LGPD, texto da corretora…).',
    rota: '/corpos-email',
    largo: true,
    dicas: [
      'Preencha Nome e HTML, clique «Guardar atalho» — fica disponível para toda a equipe.',
      'Use nomes descritivos: «Rodapé padrão», «Aviso sinistro 0800», etc.',
      'Para inserir num corpo: clique no nome do atalho com o cursor no editor HTML.',
      'Evite colar direto do Word — traz formatação estranha e aspas curvas que quebram o HTML.',
    ],
  },
  {
    titulo: 'Mini-aula: HTML para e-mail',
    texto:
      'O corpo do e-mail é HTML simples (não é página web completa). Algumas tags bastam para um texto profissional.',
    rota: '/corpos-email',
    largo: true,
    aula: true,
    dicas: [
      'Parágrafo: tag p de abertura e fechamento — um por ideia.',
      'Destaque: tag strong para nome ou número da apólice.',
      'Quebra de linha na assinatura: tag br (auto-fechada).',
      'Não use html, head ou body — o sistema já envolve o seu conteúdo.',
    ],
    exemplos: [
      {
        titulo: 'Estrutura mínima recomendada',
        codigo: `<p>Prezado(a) <strong>{{ nome }}</strong>,</p>
<p>Segue em anexo sua apólice{% if numero_apolice %} nº <strong>{{ numero_apolice }}</strong>{% endif %}.</p>
<p>Atenciosamente,<br/>{{ from_name }}</p>`,
      },
      {
        titulo: 'Destaque opcional (caixa colorida)',
        codigo: `<div style="margin:1em 0;padding:.85em 1em;background:#f7faf9;border-left:3px solid #00B94E;">
  Texto fixo ou variável {{ nome }} conforme o seu modelo.
</div>`,
      },
    ],
    avisos: [
      'Feche todas as tags (cada p precisa de fechamento).',
      'Não apague {% if %} nem {% endif %} — são condicionais do sistema.',
      'Use aspas retas do teclado — evite aspas tipográficas do Word.',
    ],
  },
  {
    titulo: 'Ligar corpo ao tipo de envio',
    texto:
      'Um corpo bonito só entra em ação quando está ligado ao tipo certo — senão o sistema usa o template padrão.',
    rota: '/tipos-envio',
    dicas: [
      'Em Tipos de Envio, edite o tipo (auto, moto…) e escolha o Corpo de e-mail.',
      'O código do tipo deve bater com a pasta do FULL (ex.: pasta entrada/auto/).',
    ],
  },
  {
    titulo: 'Tutorial e histórico',
    texto:
      'Consulte o Tutorial para tabelas de modelos, PDF com senha e auditoria. O Histórico regista quem enviou e quem colocou ficheiros no FULL.',
    rota: '/tutorial',
    dicas: [
      'O Tutorial no menu lateral reúne guias por modelo de apólice.',
      'No Histórico vê data, cliente, tipo de envio e quem executou a ação.',
    ],
  },
  {
    titulo: 'Backup de apólices — acesso restrito',
    texto:
      'A área Backup guarda cópias das apólices já enviadas. Por segurança e LGPD, o acesso a essa pasta e ao menu Backup é limitado.',
    rota: '/dashboard',
    largo: true,
    dicas: [
      'Por defeito, só administradores acedem ao Backup.',
      'Um administrador pode conceder acesso a outros utilizadores em Utilizadores (opção «Acesso a backup»).',
      'Se o menu Backup não aparecer no seu utilizador, fale com um administrador da equipe — ele pode ativar o acesso para si.',
    ],
    avisos: [
      'Não partilhe a sua senha; o acesso ao backup é individual e controlado.',
    ],
    aula: false,
    fechamento: true,
  },
]

function tourUserId() {
  if (!auth.authEnabled) return 'anon'
  const id = auth.user?.id
  return id != null ? String(id) : null
}

function concluirTour() {
  const uid = tourUserId()
  if (uid) ui.marcarTourConcluido(uid)
}

const atual = computed(() => passos[passo.value])
const ultimo = computed(() => passo.value >= passos.length - 1)
const cardLargo = computed(() => atual.value?.largo || atual.value?.aula || atual.value?.soc)
const isSocStep = computed(() => Boolean(atual.value?.soc))

function irParaPasso() {
  if (atual.value?.rota) router.push(atual.value.rota)
}

function proximo() {
  if (ultimo.value) {
    concluirTour()
    emit('fechar')
    return
  }
  passo.value += 1
  irParaPasso()
}

function anterior() {
  if (passo.value > 0) {
    passo.value -= 1
    irParaPasso()
  }
}

function pular() {
  concluirTour()
  emit('fechar')
}

onMounted(irParaPasso)
</script>

<template>
  <div class="tour-overlay" role="dialog" aria-modal="true" aria-labelledby="tour-titulo">
    <div
      class="tour-card"
      :class="{ 'tour-card--largo': cardLargo, 'tour-card--soc': isSocStep }"
    >
      <p class="tour-step-label" :class="{ 'tour-step-label--soc': isSocStep }">
        {{ isSocStep ? 'Segurança' : 'Tour' }} · Passo {{ passo + 1 }} de {{ passos.length }}
      </p>
      <h3 id="tour-titulo">{{ atual.titulo }}</h3>
      <div class="tour-body">
        <div v-if="isSocStep" class="tour-soc-intro">
          <p class="tour-soc-oque">
            <strong>O que é?</strong> Modo de contenção após suspeita de ataque ou falha grave de segurança.
          </p>
          <p class="tour-soc-para">
            <strong>Para que serve?</strong> Parar envios de imediato, proteger dados dos clientes com outra chave
            e impedir que PDFs na pasta sejam processados até o incidente estar resolvido.
          </p>
          <p class="tour-soc-onde text-muted">
            No Dashboard, cartão <strong>Modo SOC</strong> — use «Ativar» só em emergência real.
          </p>
        </div>
        <p class="tour-lead" :class="{ 'tour-lead--soc': isSocStep }">{{ atual.texto }}</p>

        <ul v-if="atual.dicas?.length" class="tour-lista">
          <li v-for="(d, i) in atual.dicas" :key="i">{{ d }}</li>
        </ul>

        <div v-if="atual.exemplos?.length" class="tour-exemplos">
          <div v-for="(ex, i) in atual.exemplos" :key="i" class="tour-exemplo">
            <p class="tour-exemplo-titulo">{{ ex.titulo }}</p>
            <pre class="tour-code"><code>{{ ex.codigo }}</code></pre>
          </div>
        </div>

        <ul v-if="atual.avisos?.length" class="tour-avisos">
          <li v-for="(a, i) in atual.avisos" :key="'a' + i">{{ a }}</li>
        </ul>

        <p v-if="atual.fechamento" class="tour-nota text-muted">
          Pode rever este tour quando quiser: use <strong>Rever tour guiado</strong> no rodapé do menu lateral.
        </p>
        <p v-if="atual.aula" class="tour-nota text-muted">
          Variáveis <code v-pre>{{ nome }}</code> são trocadas no envio. Trechos
          <code v-pre>{% if … %}</code> mostram ou escondem partes conforme os dados do PDF.
        </p>
      </div>

      <div class="tour-dots" aria-hidden="true">
        <span
          v-for="(_, i) in passos"
          :key="i"
          class="tour-dot"
          :class="{ active: i === passo }"
        />
      </div>
      <div class="tour-actions">
        <button type="button" class="btn btn-ghost" @click="pular">Pular tour</button>
        <span class="spacer" />
        <button v-if="passo > 0" type="button" class="btn btn-ghost" @click="anterior">
          Anterior
        </button>
        <button type="button" class="btn btn-accent" @click="proximo">
          {{ ultimo ? 'Concluir' : 'Próximo' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tour-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(46, 26, 14, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}
.tour-card {
  background: var(--surface);
  border-radius: var(--radius);
  padding: 1.5rem 1.75rem;
  max-width: 480px;
  width: 100%;
  max-height: min(90vh, 720px);
  display: flex;
  flex-direction: column;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.25);
}
.tour-card--largo {
  max-width: 560px;
}
.tour-card--soc {
  border: 1px solid var(--err);
  box-shadow: 0 0 0 1px rgba(197, 48, 48, 0.2), 0 16px 48px rgba(0, 0, 0, 0.25);
}
.tour-step-label--soc {
  color: var(--err);
}
.tour-soc-intro {
  margin: 0 0 1rem;
  padding: 0.85rem 1rem;
  background: rgba(197, 48, 48, 0.08);
  border-left: 3px solid var(--err);
  border-radius: 0 8px 8px 0;
}
.tour-soc-intro p {
  margin: 0 0 0.55rem;
  font-size: 0.9rem;
  line-height: 1.5;
}
.tour-soc-intro p:last-child {
  margin-bottom: 0;
}
.tour-lead--soc {
  font-size: 0.9rem;
}
.tour-body {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  margin-bottom: 0.5rem;
  padding-right: 0.25rem;
}
.tour-step-label {
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--accent-2);
  margin: 0 0 0.5rem;
  font-weight: 700;
}
.tour-lead {
  margin: 0 0 0.75rem;
  color: var(--text);
  line-height: 1.5;
  font-size: 0.95rem;
}
.tour-lista {
  margin: 0 0 0.75rem;
  padding-left: 1.2rem;
  font-size: 0.9rem;
  line-height: 1.55;
  color: var(--muted);
}
.tour-exemplos {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  margin-bottom: 0.75rem;
}
.tour-exemplo-titulo {
  margin: 0 0 0.25rem;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--accent-2);
}
.tour-code {
  margin: 0;
  padding: 0.65rem 0.75rem;
  background: #1e1e1e;
  color: #e8e6e3;
  border-radius: 8px;
  font-size: 0.72rem;
  line-height: 1.45;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.tour-avisos {
  margin: 0 0 0.5rem;
  padding: 0.65rem 0.85rem 0.65rem 1.1rem;
  background: rgba(197, 48, 48, 0.08);
  border-left: 3px solid var(--err);
  font-size: 0.85rem;
  line-height: 1.5;
}
.tour-nota {
  font-size: 0.82rem;
  margin: 0.5rem 0 0;
  line-height: 1.45;
}
.tour-dots {
  display: flex;
  gap: 0.35rem;
  margin: 0.75rem 0;
  flex-shrink: 0;
}
.tour-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--terra-300);
}
.tour-dot.active {
  background: var(--accent);
  width: 20px;
  border-radius: 4px;
}
.tour-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  flex-shrink: 0;
}
</style>
