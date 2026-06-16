<script setup>
import { RouterLink } from 'vue-router'

const modelos = [
  {
    nome: 'Tokio Marine — Auto',
    full: true,
    pasta: 'auto/',
    layout: 'tokio_marine',
    dica: 'CPF e nº da apólice (ex.: 06548820) são lidos do PDF.',
  },
  {
    nome: 'Tokio Marine — Moto',
    full: true,
    pasta: 'moto/',
    layout: 'tokio_marine',
    dica: 'Mesmo layout; coloque os PDFs na subpasta moto/.',
  },
  {
    nome: 'Yelum — Auto Casco',
    full: true,
    pasta: 'auto_casco/',
    layout: 'yelum_casco',
    dica: 'Apólice no formato 31.09.2026.0907318.',
  },
  {
    nome: 'Porto / SulAmérica (PDF com senha)',
    full: false,
    pasta: '—',
    layout: 'porto_sulamerica_criptografado',
    dica: 'Use Envio Manual: escolha o cliente e informe o nº da apólice.',
  },
  {
    nome: 'PDF só imagem',
    full: false,
    pasta: '—',
    layout: 'sem_texto',
    dica: 'Impressão sem texto; cadastre cliente e apólice manualmente.',
  },
]

const passos = [
  {
    titulo: '1. Configure o básico',
    itens: [
      'Configure os corpos de e-mail e associe cada um ao tipo de envio correspondente.',
      'Envie a capa Terra Fértil em Capa (vira capa.pdf junto com cada apólice).',
      'Cadastre assinaturas em Assinaturas e vincule ao FULL se necessário.',
    ],
    rota: '/dashboard',
    rotulo: 'Ir ao Dashboard',
  },
  {
    titulo: '2. Clientes e veículos',
    itens: [
      'Cadastre cada cliente com CPF correto — o FULL identifica pelo documento.',
      'Em Autos, vincule placas aos clientes para preencher dados no e-mail.',
    ],
    rota: '/clientes',
    rotulo: 'Clientes',
  },
  {
    titulo: '3. Tipos de envio e corpos de e-mail',
    itens: [
      'Crie tipos (auto, moto, auto_casco) em Tipos de Envio — cada um ganha uma pasta no FULL.',
      'Em Corpos de E-mail, use os atalhos por modelo ou crie os seus.',
      'Associe cada corpo ao tipo correspondente.',
    ],
    rota: '/tipos-envio',
    rotulo: 'Tipos de Envio',
  },
  {
    titulo: '4. Modo FULL (automático)',
    itens: [
      'Ative o FULL no Dashboard e defina o horário de varredura.',
      'Coloque os PDFs nas subpastas (auto/, moto/, etc.) dentro da pasta monitorada.',
      'O sistema extrai dados, envia, faz backup e move para processados/.',
    ],
    rota: '/full-config',
    rotulo: 'Configuração FULL',
  },
  {
    titulo: '5. Envio manual',
    itens: [
      'Use para PDFs protegidos, só imagem ou envios pontuais.',
      'Atalhos no Dashboard levam direto ao envio com o modelo certo.',
    ],
    rota: '/envio',
    rotulo: 'Envio Manual',
  },
]
</script>

<template>
  <div class="tutorial-page">
    <div class="app-topbar">
      <h2>Tutorial do sistema</h2>
    </div>

    <p class="text-muted mb-4">
      Guia rápido para operar o envio de apólices Terra Fértil — do cadastro ao envio automático (FULL)
      e manual.
    </p>

    <section class="card">
      <h3>Modelos de apólice suportados</h3>
      <table class="table">
        <thead>
          <tr>
            <th>Modelo</th>
            <th>Modo FULL</th>
            <th>Pasta FULL sugerida</th>
            <th>Observação</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in modelos" :key="m.layout + m.nome">
            <td><strong>{{ m.nome }}</strong></td>
            <td>
              <span class="badge" :class="m.full ? 'enviado' : 'pendente'">
                {{ m.full ? 'Automático' : 'Manual' }}
              </span>
            </td>
            <td><code>{{ m.pasta }}</code></td>
            <td class="text-muted">{{ m.dica }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-for="p in passos" :key="p.titulo" class="card tutorial-passo">
      <h3>{{ p.titulo }}</h3>
      <ul class="tutorial-lista">
        <li v-for="(item, i) in p.itens" :key="i">{{ item }}</li>
      </ul>
      <RouterLink :to="p.rota" class="btn btn-ghost btn-sm">{{ p.rotulo }} →</RouterLink>
    </section>

    <section class="card">
      <h3>Atalhos e HTML nos corpos de e-mail</h3>
      <p class="text-muted">
        Em <RouterLink to="/corpos-email">Corpos de E-mail</RouterLink>, ative
        <strong>Atalhos visíveis</strong>. Use o tour guiado («Rever tour» no menu) para a mini-aula completa.
      </p>
      <h4 class="mt-3" style="font-size: 1rem">Três abas de atalhos</h4>
      <ul class="tutorial-lista">
        <li>
          <strong>Variáveis</strong> — clique para inserir
          <code v-pre>{{ nome }}</code>, CPF, placa, apólice, etc. O sistema substitui no envio.
        </li>
        <li>
          <strong>Por modelo</strong> — «Inserir bloco» cola HTML pronto (Tokio, Yelum, manual). Edite depois.
        </li>
        <li>
          <strong>Meus atalhos</strong> — nome + HTML, «Guardar atalho»; fica na base para toda a equipe.
        </li>
      </ul>
      <h4 class="mt-3" style="font-size: 1rem">HTML básico (resumo)</h4>
      <ul class="tutorial-lista">
        <li><code>&lt;p&gt;</code> parágrafo · <code>&lt;strong&gt;</code> negrito · <code>&lt;br/&gt;</code> quebra de linha</li>
        <li>
          Condicional:
          <code v-pre>{% if numero_apolice %}…{% endif %}</code> — não apague essas marcas.
        </li>
        <li>Não cole do Word; não use <code>&lt;html&gt;</code> / <code>&lt;body&gt;</code> no editor.</li>
        <li>Associe o corpo ao tipo em <RouterLink to="/tipos-envio">Tipos de Envio</RouterLink>.</li>
      </ul>
    </section>

    <section class="card">
      <h3>PDF com senha</h3>
      <p class="text-muted">
        Muitas seguradoras (Porto, SulAmérica, etc.) enviam o PDF protegido. A senha costuma ser o
        <strong>CPF do segurado</strong> (só números) ou um código enviado por SMS/e-mail.
      </p>
      <ul class="tutorial-lista">
        <li>
          <strong>Envio manual:</strong> ao carregar o PDF, informe a senha no campo amarelo e clique em
          «Aplicar senha e analisar».
        </li>
        <li>
          <strong>Modo FULL automático:</strong> na mesma pasta do PDF, crie um ficheiro
          <code>apolice.pdf.senha</code> (ou <code>apolice.senha.txt</code>) com a senha numa única linha.
          Exemplo: pasta <code>entrada/auto/</code> com <code>55207_....pdf</code> e <code>55207_....pdf.senha</code>.
        </li>
        <li>
          Se não tiver a senha, peça ao segurado ou à seguradora uma cópia <em>sem proteção</em> (PDF desbloqueado).
        </li>
      </ul>
      <p class="text-muted" style="font-size:0.9rem">
        A senha não é guardada na base de dados — só é usada na hora do envio.
      </p>
    </section>

    <section class="card">
      <h3>Tour guiado e OCR</h3>
      <p class="text-muted">
        Na primeira visita, um tour em 5 passos explica o painel. Use
        <strong>Rever tour guiado</strong> no rodapé do menu lateral para repetir.
      </p>
      <p class="text-muted">
        Para PDFs só imagem, instale o
        <a href="https://github.com/UB-Mannheim/tesseract/wiki" target="_blank" rel="noopener">Tesseract OCR</a>
        no servidor Windows e configure <code>TESSERACT_CMD</code> no <code>backend/.env</code>.
        O indicador <strong>OCR ativo</strong> aparece no topo quando disponível.
      </p>
    </section>

    <section class="card">
      <h3>Operação no servidor (Windows)</h3>
      <ul class="tutorial-lista">
        <li>
          <strong>Pastas persistentes</strong> — em <code>backend/.env</code>: <code>entrada/</code>,
          <code>backup/</code>, <code>processados/</code>, <code>data/envio.db</code> e <code>capas/capa.pdf</code>
          devem ficar num disco com cópia de segurança regular.
        </li>
        <li>
          <strong>Tesseract OCR</strong> — instale no servidor e, se necessário, defina
          <code>TESSERACT_CMD</code> no <code>.env</code>. Reinicie o serviço da API após alterar o
          <code>.env</code> ou <code>requirements.txt</code>:
          <code>Restart-Service EnvioApolices-API</code>
        </li>
        <li>
          <strong>PDF com senha no FULL</strong> — ficheiro auxiliar
          <code>nome.pdf.senha</code> na mesma pasta do PDF (uma linha com a senha).
        </li>
        <li>
          <strong>Auditoria no histórico</strong> — envio manual regista o utilizador logado; no FULL,
          opcional <code>nome.pdf.usuario</code> (uma linha com o nome) ou o dono do ficheiro no Windows.
        </li>
        <li>
          O indicador <strong>OCR ativo</strong> no menu confirma que o Tesseract está acessível.
        </li>
      </ul>
    </section>

    <section class="card">
      <h3>Qualidade dos envios automáticos</h3>
      <ul class="tutorial-lista">
        <li>
          Revise periodicamente os <strong>modelos FULL</strong> na tabela acima — PDFs protegidos ou só
          imagem exigem envio manual ou OCR.
        </li>
        <li>
          Em <RouterLink to="/clientes">Clientes</RouterLink>, use o painel
          <strong>Possíveis duplicados</strong> para unificar CPF/e-mail repetidos.
        </li>
        <li>
          Após alterar capa ou corpo de e-mail, faça um
          <strong>Demonstrar e-mail</strong> ou envio de teste antes de ativar o FULL em volume.
        </li>
        <li>
          Mantenha <code>backend/capas/capa.pdf</code> alinhada à identidade Terra Fértil (versão atual da corretora).
        </li>
      </ul>
    </section>

    <section class="card">
      <h3>LGPD e privacidade</h3>
      <ul class="tutorial-lista">
        <li>
          <strong>Backup de apólices</strong> (<code>backend/backup/</code>): estrutura
          <code>AAAA-MM/nome-cliente/arquivo.pdf</code>. Retenção recomendada: 24 meses
          (<code>BACKUP_RETENTION_MONTHS</code> no <code>.env</code>) — apague pastas antigas conforme política interna.
        </li>
        <li>
          Só administradores ou utilizadores com <strong>Acesso ao backup</strong> (em Utilizadores) podem abrir a área
          Backup no painel; os restantes veem aviso para contactar o administrador.
        </li>
        <li>
          <strong>Exclusão do titular:</strong> em Clientes, botão <strong>LGPD</strong> — remove cadastro,
          histórico e opcionalmente os ficheiros de backup (confirme digitando o nome).
        </li>
        <li>
          No <strong>envio manual</strong>, confirme o e-mail na janela de verificação antes de enviar.
        </li>
        <li>
          Exporte o histórico em CSV (<RouterLink to="/historico">Histórico</RouterLink>) para auditoria interna.
        </li>
      </ul>
    </section>

    <section class="card">
      <h3>Histórico, CSV e reenvio</h3>
      <p class="text-muted">
        Em <RouterLink to="/historico">Histórico</RouterLink> pode filtrar envios, exportar CSV e
        <strong>reenviar erros</strong> em lote (usa o PDF já guardado em backup, quando existir).
      </p>
    </section>

    <section class="card alert alert-warn">
      <strong>Dúvidas frequentes</strong>
      <ul class="tutorial-lista mt-2">
        <li>PDF com senha no FULL — use ficheiro <code>.senha</code> ou envio manual.</li>
        <li>Cliente não encontrado no FULL — confira se o CPF no cadastro é igual ao do PDF.</li>
        <li>E-mail não sai — verifique corpo de e-mail no tipo de envio e SMTP no servidor (ver instalador).</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.tutorial-lista {
  margin: 0 0 1rem 1.1rem;
  line-height: 1.55;
}
.tutorial-passo h3 {
  margin-bottom: 0.5rem;
}
</style>
