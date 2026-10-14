'use strict';
// Farol: tela do aviso de desligamento. Entrar, enviar a planilha, ver os municípios e as
// comunidades no mapa, gerar o roteiro (PDF) para a rádio, consultar o histórico e administrar
// usuários e empresas, conforme o perfil. Só fala com a própria API; quem decide o que cada perfil
// pode é o servidor (a tela só esconde o que não serve ao perfil).
// Organização: Model (estado e regras puras), View (desenha a partir do estado) e Controller (eventos).

// ======================= Model: estado da tela e regras puras (não toca no HTML) =======================
const estado = {
  usuario: null,           // /api/eu (perfil, empresa, ações permitidas)
  tela: 'carregando',      // carregando | entrar | senha | app
  vista: 'aviso',          // aviso | historico | painel | usuarios | empresas | registro
  passo: 1,                // funil do novo aviso: 1 planilha, 2 quando, 3 conferir, 4 avisos
  config: null, concessao: null,
  arquivo: null, enviando: false,
  mensagem: '', erro: false,
  resultado: null,         // resposta de /api/planilha (conferência), de /api/avisos (gerado) ou um aviso do histórico
  conferi: false,          // a caixa "Conferi os números e o mapa" do passo 3
  radios: [],              // rádios da empresa (para o envio), com o valor sugerido
  sugestao: {},            // codigo_ibge -> { radios: [{ radio_id, comunidades, municipio_inteiro }], sem_radio: [...] }
  envios: [],              // envios do aviso aberto (e-mail, WhatsApp, cópia), com valor, economia e situação
  escolha: {},             // codigo_ibge -> { radioId, valor, cobranca, antigo, nova: {...} }: o formulário de envio
  justificativa: '',       // obrigatória quando as rejeitadas passam do limite da empresa
  abas: [], aba: '',       // quando mais de uma aba da planilha serve, a escolhida
  origem: null,            // 'novo' | 'historico'
  avisos: {},              // codigo_ibge -> texto do aviso (editável)
  finais: {},              // codigo_ibge -> texto final já guardado no histórico
  territorios: {},         // codigo_ibge -> GeoJSON das comunidades
  audios: {},              // codigo_ibge -> { texto, url (blob local), segundos }: o MP3 do texto atual
  audiosHoje: {},          // codigo_ibge -> { url, segundos }: o MP3 do aviso de hoje (comparativo)
  verUcs: true,            // camada dos pontos das UCs (só logo depois do envio; o histórico não tem pontos)
  verRede: true,           // rede elétrica FICTÍCIA (demonstração), de perto; o botão esconde
  legendaMinimizada: false, // lembrada neste navegador (só conveniência)
  redes: {},               // codigo_ibge -> rede fictícia do município (null: sem rede no banco)
  formulario: null,        // { data: '20/11', dataLonga: '20/11/2026', horario: '8h às 14h', idioma: 'pt-BR' }
  historico: [], usuarios: [], perfis: {}, empresas: [], registro: [],
  filtroHistorico: { busca: '', periodo: '' },
  painel: null,            // /api/painel: números do histórico da empresa (e o bloco do mês)
  radiosAdmin: [],         // rádios da empresa (Admin da empresa), com as inativas
  radioEditando: null,     // a rádio no formulário (null: nova)
  alcanceComunidades: [],  // comunidades escolhidas no formulário da rádio: { municipio, nome, distrito }
  configuracao: null,      // /api/empresa/configuracao
  relatorio: null,         // /api/relatorios/mensal: o relatório do período com os filtros
};

// o menu de cada perfil (a matriz de perfis do plano); quem decide o que pode é o servidor, a tela só mostra o que serve
const MENUS = {
  admin_farol: [['empresas', 'Empresas'], ['registro', 'Auditoria geral']],
  admin_empresa: [['aviso', 'Novo aviso'], ['historico', 'Histórico'], ['relatorios', 'Relatórios'], ['usuarios', 'Usuários'],
    ['radios', 'Rádios'], ['configuracoes', 'Configurações'], ['registro', 'Auditoria']],
  operador: [['aviso', 'Novo aviso'], ['historico', 'Histórico'], ['relatorios', 'Relatórios']],
  consulta: [['painel', 'Mapa'], ['historico', 'Histórico'], ['relatorios', 'Relatórios']],
};
const RELATORIOS = [['painel', 'Painel do mês'], ['relatorios', 'Do período'], ['comparativo', 'Comparativo']];
const VISTAS = ['aviso', 'historico', 'painel', 'relatorios', 'comparativo', 'usuarios', 'radios', 'configuracoes', 'empresas', 'registro'];
const pode = acao => !!estado.usuario?.acoes.includes(acao);
const vistasDoPerfil = () => MENUS[estado.usuario?.perfil] || [];
const menuAtual = v => vistasDoPerfil().some(([x]) => x === v) ? v : RELATORIOS.some(([x]) => x === v) ? 'relatorios' : v;

// a ajuda de cada perfil: o caminho, na ordem em que se usa
const AJUDA = {
  operador: [
    ['Novo aviso', 'Escolha a planilha das UCs afetadas (.xlsx ou .csv, até 10 MB) e, no passo 2, a data, o horário e o tipo do desligamento.'],
    ['Conferir', 'O Farol lê a planilha, corrige o que é seguro corrigir (em roxo no mapa) e mostra os números. Vermelho bloqueia (equipamento vital com problema); amarelo pede atenção. Marque "Conferi os números e o mapa" e gere o aviso.'],
    ['Avisos', 'Ajuste a mensagem da rádio, ouça, baixe o PDF e envie à rádio (e-mail com confirmação, WhatsApp ou cópia), informando o valor.'],
    ['Histórico e relatórios', 'No histórico ficam os avisos, os envios e os comprovantes; mude a data ou cancele quando preciso. Os relatórios mostram custo, economia e prazo do mês.'],
  ],
  consulta: [
    ['Mapa', 'Os municípios pintados pela quantidade de avisos e os próximos desligamentos.'],
    ['Histórico', 'Abra um aviso para ver as comunidades, a mensagem, quem pediu e os envios; baixe o comprovante.'],
    ['Relatórios', 'Os números do mês, por rádio e por comunidade, em PDF ou CSV com o código de verificação.'],
  ],
  admin_farol: [
    ['Empresas', 'Cadastre a empresa com o primeiro admin (a senha temporária aparece uma vez) e suspenda ou reative quando preciso.'],
    ['Auditoria geral', 'Os acessos de todas as empresas, com a conferência da integridade da corrente.'],
  ],
};
AJUDA.admin_empresa = [...AJUDA.operador,
  ['Usuários', 'Convide pessoas da empresa (só e-mail do domínio), escolha o perfil e os municípios; bloqueie quando sair. O último admin não pode ser bloqueado.'],
  ['Rádios e configurações', 'Cadastre as rádios e o que cada uma alcança; ajuste o modelo da mensagem, o telefone, o limite de rejeição, o fuso UTM e a antecedência.'],
  ['Auditoria', 'Tudo o que cada pessoa fez, com o nome e o perfil, sem nada apagado; baixe o relatório de auditoria.']];

// os termos que confundem: um "?" ao lado mostra a explicação
const DICAS = {
  uc: 'UC (unidade consumidora): cada ligação de energia (uma casa, um sítio, um comércio). A planilha traz uma linha por UC; o número nunca aparece na tela.',
  vital: 'Equipamento vital: alguém na UC depende de aparelho elétrico para viver. O aviso precisa de 5 dias úteis de antecedência (REN 1.000/2021, art. 436), e qualquer problema nessas linhas bloqueia o aviso.',
  corrigida: 'Corrigida: latitude e longitude vieram trocadas ou sem o sinal; o Farol corrigiu só porque o ponto corrigido cai na área de concessão. Fica em roxo no mapa.',
  rejeitada: 'Rejeitada: a linha não entra no aviso (sem UC, sem coordenada, fora da concessão, UC repetida…). O motivo aparece pela linha, sem a UC.',
  limite: 'Limite de rejeição: se mais linhas que o limite da empresa (padrão 2%) forem rejeitadas, o aviso só sai com uma justificativa, que fica na auditoria.',
  vizinha: 'Localidade vizinha: um pedaço pequeno de outra comunidade ficou na área; o aviso cita "localidades vizinhas" em vez de nomear uma por uma.',
  codigo: 'Código de verificação (FRL-…): sai do registro da auditoria que guardou o aviso ou o relatório. Com ele, a empresa confere quem gerou e quando, e que nada foi mudado.',
  economia: 'Economia calculada: pelo tempo no ar (aviso de hoje, fazenda a fazenda, menos a mensagem do Farol) vezes o valor por minuto. Informada: o custo antigo que quem enviou digitou. Sem um dos dois, o Farol não estima.',
};

// a mensagem pelo modelo (a mesma regra de nucleo/mensagem.py), para a prévia nas configurações
function montarMensagem(modelo, v) {
  const valor = c => String(v[c] ?? '').trim();
  return modelo.replace(/\[([^\[\]]*)\]/g, (_, trecho) => [...trecho.matchAll(/\{([^{}]*)\}/g)].some(m => !valor(m[1])) ? '' : trecho)
    .replace(/\{([^{}]*)\}/g, (_, c) => valor(c)).replace(/[ \t]+/g, ' ').replace(/ +([.,;:!?])/g, '$1').trim();
}
const FUSOS_UTM = [[31978, 'UTM 18S'], [31979, 'UTM 19S'], [31980, 'UTM 20S'], [31981, 'UTM 21S'], [31982, 'UTM 22S'], [31983, 'UTM 23S'],
  [31984, 'UTM 24S'], [31985, 'UTM 25S']];
const municipiosDaConcessao = () => (estado.concessao?.features || []).map(f => [f.properties.codigo_ibge, `${f.properties.nome}/${f.properties.uf}`])
  .sort((a, b) => a[1].localeCompare(b[1], 'pt-BR'));
const nomeMunicipio = cod => municipiosDaConcessao().find(([c]) => c === cod)?.[1] || cod;
const temaAtual = () => document.documentElement.dataset.tema || (matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro');

const fmt = n => Number(n).toLocaleString('pt-BR');
const dataHora = iso => new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });

// "08:00" -> "8h", "08:30" -> "8h30" (como o aviso fala)
function horaTexto(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  return `${h}h${m ? String(m).padStart(2, '0') : ''}`;
}
// "2026-11-12" -> "12/11"
const dataTexto = iso => { const [, m, d] = iso.split('-'); return `${d}/${m}`; };
const dataLonga = iso => { const [a, m, d] = iso.split('-'); return `${d}/${m}/${a}`; };

function validarArquivo(arquivo) {
  if (!arquivo) return 'Escolha a planilha das UCs afetadas.';
  if (!/\.(csv|xlsx)$/i.test(arquivo.name)) return 'A planilha tem de ser .csv ou .xlsx.';
  if (estado.config && arquivo.size > estado.config.limites.bytes) return 'A planilha passa de 10 MB.';
  return null;
}

function validarFormulario({ arquivo, data, inicio, fim, tipo, tipoOutro }) {
  const problema = validarArquivo(arquivo);
  if (problema) return problema;
  if (!data) return 'Informe a data do desligamento.';
  if (!inicio || !fim) return 'Informe o horário de início e de fim.';
  if (fim <= inicio) return 'O fim tem de ser depois do início.';
  if (tipo === 'outro' && tipoOutro.trim().length < 3) return 'Descreva o motivo do desligamento (de 3 a 200 caracteres).';
  return null;
}

// "Solicitado por Fulana (Operador) em 14/10/2026 às 10:32 · código de verificação FRL-…" (o nome vem do login)
function solicitadoTexto(r) {
  if (!r?.id || !r.criado_em) return '';
  const q = new Date(r.criado_em);
  return `Solicitado por ${r.usuario || '—'}${r.usuario_perfil ? ` (${r.usuario_perfil})` : ''} em ${q.toLocaleDateString('pt-BR')} às `
    + `${q.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}${r.codigo ? ` · código de verificação ${r.codigo}` : ''}`;
}

function validarSenhaNova(nova, repetida) {
  if (nova.length < 12) return 'A senha nova precisa ter pelo menos 12 caracteres.';
  if (nova !== repetida) return 'As duas senhas novas não são iguais.';
  return null;
}

// o áudio vale enquanto o texto não muda; só em português por enquanto
const audioAtual = codigo => estado.audios[codigo]?.texto === estado.avisos[codigo] ? estado.audios[codigo] : null;
// o servidor pode estar sem a voz (FAROL_AUDIO=0, em produção no plano gratuito)
const audioLigado = () => estado.config?.audio !== false;
// gerar o áudio é de quem gera o aviso (Consulta só lê; a API também recusa)
const temAudio = () => audioLigado() && pode('gerar_aviso') && estado.formulario?.idioma === 'pt-BR';

// 754 s -> "12 min 34 s"
const tempoNoAr = s => s < 60 ? `${fmt(s)} s` : `${fmt(Math.floor(s / 60))} min${s % 60 ? ` ${s % 60} s` : ''}`;

const palavras = texto => texto.trim().split(/\s+/).filter(Boolean).length;
const segundos = texto => Math.round(palavras(texto) / (estado.config?.palavras_por_segundo || 2.5));

// como a comunidade entra no aviso: inteira, parte ou localidade vizinha (fragmento)
const situacao = c => c.fragmento ? 'vizinha' : c.parcial ? 'parte' : 'inteira';
const ROTULO = { inteira: 'inteira', parte: 'parte', vizinha: 'localidade vizinha' };
// homônimos vêm como "Piacatuba (Tebas)"; na tela, o nome sem o sufixo e o distrito uma vez só
// (o distrito com o nome do município é a "Sede", como no aviso)
const semSufixo = nome => nome.replace(/ \(.*\)$/, '');
const distritoTexto = (c, m) => c.distrito === m.nome ? 'Sede' : c.distrito;
const nomeComDistrito = (c, m) => `${semSufixo(c.nome)} (${distritoTexto(c, m)})`;
const homonimo = c => / \(.*\)$/.test(c.nome);

// funil: até onde dá para ir (o 2 pede a planilha; o 3, a conferência; o 4, o aviso já gerado)
const temResultadoNovo = () => !!estado.resultado && estado.origem === 'novo';
const gerado = () => temResultadoNovo() && !!estado.resultado.id;
const passoMaximo = () => gerado() ? 4 : temResultadoNovo() ? 3 : estado.arquivo && !validarArquivo(estado.arquivo) ? 2 : 1;

// o mesmo que o servidor confere antes de gerar (nucleo/travas.problema_para_gerar); a tela só antecipa
const MAX_JUSTIFICATIVA = 300;
function problemaParaGerar() {
  const c = estado.resultado?.conferencia;
  if (!c || !estado.resultado.pacote) return 'Confira a planilha primeiro.';
  if (c.vital_bloqueio.length) return 'Bloqueado: há equipamento vital com problema. Corrija a planilha e importe de novo.';
  const j = estado.justificativa.trim();
  if (c.rejeicao.acima && !j) return `Mais de ${pct(c.rejeicao.limite)} das linhas foram rejeitadas: escreva a justificativa.`;
  if (j.length > MAX_JUSTIFICATIVA) return `A justificativa pode ter no máximo ${MAX_JUSTIFICATIVA} caracteres.`;
  if (!estado.conferi) return 'Marque "Conferi os números e o mapa" para gerar o aviso.';
  return null;
}
const pct = f => `${(f * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`;

// o texto da rádio: o final guardado, a mensagem pelo modelo da empresa ou (em outro idioma) o aviso do algoritmo
const textoGerado = m => m.mensagem || m.aviso;
const textoAviso = m => m.texto_final || textoGerado(m);

// custo e economia do envio: a mesma conta do servidor (nucleo/economia.py); nunca inventa número
function reaisNumero(t) {
  const s = String(t ?? '').replace(/R\$|\s/g, '');
  if (!s) return null;
  const n = Number(s.includes(',') ? s.replace(/\./g, '').replace(',', '.') : s);
  return Number.isFinite(n) && n >= 0 && n <= 100000 ? Math.round(n * 100) / 100 : NaN;
}
function previaEconomia({ cobranca, valor, segundosFarol, segundosHoje, custoAntigo }) {
  const tempo = segundosHoje == null ? null : segundosHoje - segundosFarol;
  if (cobranca === 'minuto') {
    const custo = Math.round(valor * segundosFarol / 60 * 100) / 100;
    if (segundosHoje != null) return { custo, economia: Math.round((segundosHoje - segundosFarol) * valor / 60 * 100) / 100, tipo: 'calculada', tempo };
    if (custoAntigo != null) return { custo, economia: Math.round((custoAntigo - custo) * 100) / 100, tipo: 'informada', tempo };
    return { custo, economia: null, tipo: null, tempo };
  }
  return { custo: valor, economia: custoAntigo != null ? Math.round((custoAntigo - valor) * 100) / 100 : null,
    tipo: custoAntigo != null ? 'informada' : null, tempo };
}
const dinheiro = v => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
// os últimos 12 meses ("2026-10"), do mais recente ao mais antigo, para os filtros dos relatórios
function ultimosMeses(hoje = new Date()) {
  const saida = [];
  for (let i = 0; i < 12; i++) {
    const d = new Date(hoje.getFullYear(), hoje.getMonth() - i, 1);
    saida.push([`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`, d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })]);
  }
  return saida;
}
const filtrosRelatorio = () => Object.fromEntries([['mes', $('relMes').value], ['municipio', $('relMunicipio').value], ['tipo', $('relTipo').value],
  ['radio', $('relRadio').value], ['pessoa', $('relPessoa').value]].filter(([, v]) => v));
const consulta = f => new URLSearchParams(f).toString();
const COBRANCA = { fechado: 'valor fechado pelo aviso', minuto: 'por minuto no ar' };
const CANAL = { email: 'e-mail', whatsapp: 'WhatsApp', copia: 'cópia da mensagem' };
const SITUACAO_ENVIO = { preparando: 'preparando', enviado: 'enviado', entregue: 'entregue ao servidor de e-mail', falhou: 'falhou',
  confirmado: 'a rádio confirmou' };
const tempoArTexto = s => s == null ? '' : s >= 0 ? `${tempoNoAr(s)} a menos no ar` : `${tempoNoAr(-s)} a mais no ar`;
function economiaTexto(e) {
  const partes = [`custo ${dinheiro(e.custo)}`];
  if (e.economia != null) partes.push(`economia ${e.economia_tipo || e.tipo} ${dinheiro(e.economia)}`);
  else partes.push('economia: só com o aviso de hoje ou o custo antigo informado');
  if ((e.tempo_economizado ?? e.tempo) != null) partes.push(tempoArTexto(e.tempo_economizado ?? e.tempo));
  return partes.join(' · ');
}

// histórico: busca por município ou comunidade (sem acento) e período pela data em que foi gerado
const normalizar = t => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
function historicoFiltrado() {
  const { busca, periodo } = estado.filtroHistorico, termo = normalizar(busca.trim());
  const desde = periodo ? Date.now() - Number(periodo) * 86400000 : 0;
  return estado.historico.filter(a => new Date(a.criado_em).getTime() >= desde && (!termo || a.municipios.some(m =>
    normalizar(m.nome).includes(termo) || m.comunidades.some(c => normalizar(semSufixo(c.nome)).includes(termo)))));
}

const MES_CURTO = mes => { const [a, m] = mes.split('-').map(Number);
  return `${new Date(a, m - 1, 1).toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')}/${String(a).slice(2)}`; };

function grupos(m) {
  const g = { inteira: [], parte: [], vizinha: [] };
  for (const c of m.comunidades) g[situacao(c)].push(c);
  return g;
}

// um aviso do histórico no mesmo formato da resposta de /api/avisos
function doHistorico(a) {
  const r = a.resumo;
  return {
    id: a.id, aviso_ficticio: estado.config.aviso_ficticio, municipios: a.municipios, prazo: r.prazo,
    planilha: { linhas: r.linhas, validas: r.validas, total_problemas: r.problemas, problemas: [], problemas_por_motivo: {} },
    fora_da_concessao: { ucs: r.fora_da_concessao, linhas: [] },
    criado_em: a.criado_em, usuario: a.usuario, usuario_perfil: a.usuario_perfil, codigo: a.codigo, status: a.status,
    desligamento: a.desligamento,
  };
}

// ======================= View: desenha a partir do estado (não muda o estado) =======================
const $ = id => document.getElementById(id);

// todo texto vindo da API ou da planilha entra como texto, nunca como HTML
function no(tag, props = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'classe') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k === 'estilo') Object.assign(e.style, v);  // pelo CSSOM: a CSP não deixa atributo style
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  e.append(...filhos.flat().filter(f => f !== null && f !== undefined && f !== false));
  return e;
}

function desenharTema() {
  const escuro = temaAtual() === 'escuro';
  $('botaoTema').textContent = escuro ? 'Tema claro' : 'Tema escuro';
  $('botaoTema').setAttribute('aria-pressed', String(escuro));
}

function desenharAjuda() {
  const passos = AJUDA[estado.usuario?.perfil] || [];
  $('ajudaTitulo').textContent = `Ajuda · ${estado.usuario?.perfil_nome || ''}`;
  $('ajudaCorpo').replaceChildren(no('ol', { classe: 'passos-ajuda' }, passos.map(([t, d]) => no('li', {}, no('strong', { texto: t }), no('span', { texto: ` ${d}` })))),
    no('p', { classe: 'ajuda', texto: 'Os botões "?" ao lado dos termos explicam cada um. Tudo o que você faz fica na auditoria com o seu nome.' }),
    no('p', { classe: 'ajuda', texto: estado.config?.aviso_ficticio || '' }));
}

// um "?" ao lado de um termo: o botão (alvo de 44 px) e a explicação em DICAS
const dica = (chave, termo) => no('button', { type: 'button', classe: 'dica', 'data-dica': chave, 'aria-label': `O que é ${termo}?`, texto: '?' });

function desenharTela() {
  $('telaEntrar').hidden = estado.tela !== 'entrar';
  $('telaSenha').hidden = estado.tela !== 'senha';
  $('telaApp').hidden = estado.tela !== 'app';
  $('conta').hidden = !estado.usuario;
  if (estado.usuario) {
    const u = estado.usuario;
    $('contaNome').textContent = `${u.nome} · ${u.perfil_nome}${u.empresa_sigla ? ' · ' + u.empresa_sigla : ''}`;
  }
}

function desenharAbas() {
  const atual = menuAtual(estado.vista);
  $('abas').replaceChildren(...vistasDoPerfil().map(([v, rotulo]) =>
    no('button', { type: 'button', 'data-vista': v, 'aria-current': atual === v ? 'page' : null, texto: rotulo })));
  const noGrupo = RELATORIOS.some(([v]) => v === estado.vista) && pode('ver_historico') && !(estado.usuario?.perfil === 'consulta' && estado.vista === 'painel');
  $('subabas').hidden = !noGrupo;
  $('subabas').replaceChildren(...(noGrupo ? RELATORIOS.map(([v, rotulo]) =>
    no('button', { type: 'button', 'data-vista': v, 'aria-current': estado.vista === v ? 'page' : null, texto: rotulo })) : []));
  for (const v of VISTAS) $(`vista-${v}`).hidden = estado.vista !== v;
  // o resultado aparece só na vista de onde veio (um aviso novo em "Novo aviso", um antigo no "Histórico");
  // no funil, o passo 3 mostra a conferência e o 4, os avisos
  const vistaDoResultado = { novo: 'aviso', historico: 'historico' }[estado.origem];
  const r = $('resultado');
  if (vistaDoResultado && r.parentElement.id !== `lugar-${vistaDoResultado}`) $(`lugar-${vistaDoResultado}`).append(r);
  r.dataset.modo = estado.origem === 'novo' ? `passo${estado.passo}` : 'completo';
  r.hidden = !estado.resultado || estado.vista !== vistaDoResultado || (estado.origem === 'novo' && estado.passo < 3);
  desenharFunil();
}

function desenharFunil() {
  if (estado.passo > passoMaximo()) estado.passo = passoMaximo();
  const n = estado.passo, max = passoMaximo();
  for (const b of $('funil').querySelectorAll('button[data-passo]')) {
    const k = Number(b.dataset.passo);
    b.setAttribute('aria-current', k === n ? 'step' : 'false');
    b.classList.toggle('feito', k < n);
    b.disabled = k > max;
  }
  $('form').hidden = n >= 3;
  $('passo-1').hidden = n !== 1;
  $('passo-2').hidden = n !== 2;
  $('voltar').hidden = n !== 2;
  $('avancar').hidden = n !== 1;
  $('gerar').hidden = n !== 2;
  $('navResultado').hidden = n < 3 || !temResultadoNovo();
  $('avancarResultado').hidden = n !== 3;
  // passo 3: antes de gerar, o botão gera (se as travas deixarem); depois, só leva aos avisos
  $('avancarResultado').textContent = gerado() ? 'Avançar para os avisos' : estado.enviando ? 'Gerando…' : 'Gerar aviso';
  $('avancarResultado').disabled = !gerado() && (estado.enviando || !!problemaParaGerar());
  const motivo = $('motivoGerar');
  if (motivo) motivo.textContent = n === 3 && !gerado() ? (problemaParaGerar() || 'Tudo conferido: pode gerar o aviso.') : '';
  $('abaRotulo').hidden = !estado.abas.length;
  $('novoAviso').hidden = n !== 4;
  $('verComparativo').hidden = n !== 4 || !pode('ver_historico');
  $('passo2Arquivo').textContent = estado.arquivo ? `Planilha: ${estado.arquivo.name}` : '';
  if (estado.resultado && estado.origem === 'novo') $('tituloResultado').textContent = tituloResultado();
}

function desenharEstado() {
  $('estado').textContent = estado.mensagem;
  $('estado').classList.toggle('erro', estado.erro);
  $('gerar').disabled = estado.enviando;
  $('gerar').textContent = estado.enviando ? 'Gerando…' : 'Gerar aviso';
  $('arquivoNome').textContent = estado.arquivo
    ? `${estado.arquivo.name} (${fmt(Math.ceil(estado.arquivo.size / 1024))} KB)`
    : 'Escolha ou arraste o arquivo (.csv ou .xlsx, até 10 MB)';
  $('zona').classList.toggle('escolhido', !!estado.arquivo);
  desenharFunil();
}

function mensagemEm(id, texto, erro) {
  $(id).textContent = texto;
  $(id).classList.toggle('erro', !!erro);
}

function desenharResumo() {
  const r = estado.resultado, p = r.planilha;
  const ucs = r.municipios.reduce((s, m) => s + m.ucs, 0);
  const dl = no('dl', { classe: 'numeros' },
    [['linhas lidas', p.linhas], ['UCs localizadas', ucs], ['com problema', p.total_problemas], ['fora da concessão', r.fora_da_concessao.ucs]]
      .map(([t, v]) => no('div', {}, no('dt', { texto: t }), no('dd', { texto: fmt(v) }))));
  const filhos = [dl, no('p', { classe: 'prazo', texto: `Antecedência mínima do aviso: ${r.prazo.antecedencia_minima} (${r.prazo.norma}).` })];
  if (!r.municipios.length) filhos.push(no('p', { classe: 'alerta', texto: 'Nenhuma UC da planilha caiu na área de concessão. Confira as coordenadas.' }));
  if (r.fora_da_concessao.ucs && r.fora_da_concessao.linhas.length) {
    const mais = r.fora_da_concessao.ucs > r.fora_da_concessao.linhas.length ? '…' : '';
    filhos.push(no('p', { classe: 'alerta', texto: `${fmt(r.fora_da_concessao.ucs)} UC(s) fora da área de concessão, sem aviso: linha(s) ${r.fora_da_concessao.linhas.join(', ')}${mais}.` }));
  }
  filhos.push(no('p', { classe: 'ajuda', texto: r.aviso_ficticio }));
  $('resumo').replaceChildren(...filhos);
}

const tempoTexto = texto => `${fmt(palavras(texto))} palavras · cerca de ${fmt(segundos(texto))} s no ar`;

function desenharMunicipios() {
  const editavel = pode('gerar_aviso');
  const cartoes = estado.resultado.municipios.map(m => {
    const g = grupos(m), cod = m.codigo_ibge, texto = estado.avisos[cod];
    const area = no('textarea', { id: `aviso-${cod}`, 'aria-label': `Aviso de ${m.nome}`, 'data-codigo': cod, readonly: !editavel });
    area.value = texto;
    const vital = m.equipamento_vital;
    const listas = no('div', { classe: 'listas' },
      ['inteira', 'parte', 'vizinha'].filter(s => g[s].length).map(s => no('p', {},
        no('span', { classe: `etiqueta ${s}`, texto: { inteira: 'Inteiras', parte: 'Em parte', vizinha: 'Vizinhas' }[s] }),
        g[s].map(c => `${homonimo(c) ? nomeComDistrito(c, m) : c.nome}: ${fmt(c.afetadas)}`).join(', '))),
      no('p', { classe: 'ajuda', texto: `Equipamento vital: ${fmt(vital.sim)} sim, ${fmt(vital.nao)} não` + (vital.a_confirmar ? `, ${fmt(vital.a_confirmar)} a confirmar` : '') + '. Depois do nome, UCs afetadas da comunidade.' }));
    return no('article', { classe: 'cartao municipio', 'data-codigo': cod },
      no('div', { classe: 'mun-cab' }, no('h3', { texto: `${m.nome}/${m.uf}` }),
        no('span', { classe: 'meta', texto: `${fmt(m.ucs)} UCs · ${fmt(m.comunidades.length)} comunidades` })),
      listas,
      no('div', { classe: 'bloco-aviso' },
      no('label', { for: area.id, texto: editavel ? 'Aviso para a rádio (pode editar)' : 'Aviso para a rádio' }), area,
      no('p', { classe: 'tempo', id: `tempo-${cod}`, texto: tempoTexto(texto) }),
      no('p', { id: `final-${cod}`, classe: 'ajuda' }),
      no('div', { classe: 'acoes' },
        editavel && estado.resultado.id && no('button', { type: 'button', classe: 'prim', 'data-acao': 'pdf', 'data-codigo': cod, texto: 'Baixar PDF para a rádio' }),
        no('button', { type: 'button', 'data-acao': 'copiar', 'data-codigo': cod, texto: 'Copiar texto' }),
        temAudio() && no('button', { type: 'button', 'data-acao': 'ouvir', 'data-codigo': cod, texto: 'Ouvir' }),
        temAudio() && no('button', { type: 'button', 'data-acao': 'audio', 'data-codigo': cod, texto: 'Baixar áudio (MP3)' }),
        editavel && no('button', { type: 'button', 'data-acao': 'restaurar', 'data-codigo': cod, texto: 'Desfazer edição' })),
      no('div', { id: `tocador-${cod}`, classe: 'tocador' }),
      temAudio() || !pode('gerar_aviso') ? null : no('p', { classe: 'ajuda', texto: audioLigado() ? 'Áudio só para avisos em português, por enquanto.'
        : 'O áudio do aviso está desligado neste servidor.' }),
      no('section', { id: `envio-${cod}`, classe: 'envio-radio', 'data-codigo': cod, 'aria-label': `Envio para a rádio: ${m.nome}` })));
  });
  $('municipios').replaceChildren(...cartoes);
  for (const m of estado.resultado.municipios) { desenharFinal(m.codigo_ibge); desenharTocador(m.codigo_ibge); desenharEnvio(m); }
}

// ---- Envio para a rádio (um município): a rádio, o valor, a economia e os envios já feitos ----
function desenharEnvio(m) {
  const cod = m.codigo_ibge, lugar = $(`envio-${cod}`), r = estado.resultado;
  if (!lugar) return;
  const feitos = estado.envios.filter(e => e.municipio === cod);
  const lista = feitos.length ? [no('h4', { texto: 'Envios para a rádio' }), no('ul', { classe: 'envios' }, feitos.map(e => no('li', {},
    no('span', { classe: `chip envio ${e.status}`, texto: SITUACAO_ENVIO[e.status] + (e.confirmado_em ? ` em ${dataHora(e.confirmado_em)}` : '') }),
    no('span', { texto: `${e.radio_nome} · ${CANAL[e.canal]}${e.destino && e.canal !== 'copia' ? ` (${e.destino})` : ''}` }),
    no('span', { classe: 'meta', texto: `${dinheiro(e.valor)} (${COBRANCA[e.cobranca]}) · ${economiaTexto(e)} · por ${e.por} em ${dataHora(e.criado_em)}` }),
    e.arquivos.length ? no('span', { classe: 'acoes' }, e.arquivos.map(t => no('button', { type: 'button', 'data-arquivo': t, 'data-envio-id': e.id,
      texto: t === 'pdf' ? 'PDF enviado' : 'MP3 enviado' }))) : null)))] : [];
  if (!(r.id && pode('gerar_aviso') && r.status !== 'cancelado')) return lugar.replaceChildren(...lista);
  const s = estado.sugestao[cod] || { radios: [], sem_radio: [] }, cobrem = new Map(s.radios.map(x => [x.radio_id, x]));
  const ordem = [...estado.radios].sort((a, b) => (cobrem.has(b.id) - cobrem.has(a.id)) || a.nome.localeCompare(b.nome, 'pt-BR'));
  const e = estado.escolha[cod] ||= escolhaPadrao(ordem[0]);
  const alcance = x => cobrem.has(x.id) ? (cobrem.get(x.id).municipio_inteiro ? ' · alcança o município' : ` · alcança ${cobrem.get(x.id).comunidades} comunidade(s)`)
    : ' · fora do alcance cadastrado';
  const sel = no('select', { 'data-envio': 'radioId', id: `radio-${cod}` },
    ordem.map(x => no('option', { value: String(x.id), texto: x.nome + alcance(x), selected: String(x.id) === String(e.radioId) })),
    no('option', { value: 'nova', texto: '+ Nova rádio', selected: e.radioId === 'nova' }));
  const campo = (rotulo, nome, extra = {}) => no('label', { texto: rotulo }, no('input', { 'data-envio': nome, value: e[nome] ?? '', autocomplete: 'off', ...extra }));
  const blocos = [no('h4', { texto: 'Enviar para a rádio' })];
  if (s.sem_radio.length) blocos.push(no('p', { classe: 'alerta-amarelo', role: 'status', texto: `Sem rádio cadastrada para: ${s.sem_radio.join(', ')}.` }));
  blocos.push(no('label', { for: `radio-${cod}`, texto: 'Rádio' }), sel);
  if (e.radioId === 'nova') blocos.push(formNovaRadio(m, e));
  else if (ordem.length) blocos.push(
    no('div', { classe: 'campos' }, campo('Valor (R$)', 'valor', { inputmode: 'decimal', placeholder: '0,00' }),
      no('label', { texto: 'Cobrança' }, no('select', { 'data-envio': 'cobranca' },
        Object.entries(COBRANCA).map(([k, t]) => no('option', { value: k, texto: t, selected: k === e.cobranca })))),
      campo('Quanto custaria do jeito antigo (R$, opcional)', 'antigo', { inputmode: 'decimal', placeholder: 'opcional' })),
    no('p', { classe: 'economia-linha' }, no('span', { classe: 'economia', id: `previa-${cod}`, 'aria-live': 'polite' }), dica('economia', 'economia calculada e informada')),
    no('div', { classe: 'acoes' },
      estado.config?.email !== false ? no('button', { type: 'button', classe: 'prim', 'data-envio-acao': 'email', texto: 'Enviar por e-mail' }) : null,
      no('button', { type: 'button', 'data-envio-acao': 'whatsapp', texto: 'Enviar por WhatsApp' }),
      no('button', { type: 'button', 'data-envio-acao': 'copia', texto: 'Copiar mensagem' })),
    estado.config?.email === false ? no('p', { classe: 'ajuda', texto: 'O envio por e-mail está desligado neste servidor.' }) : null);
  else blocos.push(no('p', { classe: 'ajuda', texto: 'Nenhuma rádio cadastrada ainda: use "+ Nova rádio".' }));
  lugar.replaceChildren(...blocos, ...lista);
  desenharPrevia(cod);
}

function escolhaPadrao(radio) {
  return radio ? { radioId: String(radio.id), valor: radio.valor_sugerido ? Number(radio.valor_sugerido).toFixed(2).replace('.', ',') : '',
    cobranca: radio.cobranca_sugerida || 'fechado', antigo: '' } : { radioId: 'nova', valor: '', cobranca: 'fechado', antigo: '' };
}

function formNovaRadio(m, e) {
  const n = e.nova ||= { nome: '', email: '', whatsapp: '', valor: '', cobranca: 'fechado', alcance: 'municipio' };
  const campo = (rotulo, nome, extra = {}) => no('label', { texto: rotulo }, no('input', { 'data-nova': nome, value: n[nome], autocomplete: 'off', ...extra }));
  return no('div', { classe: 'nova-radio' },
    campo('Nome da rádio', 'nome', { maxlength: '80' }), campo('E-mail da rádio', 'email', { type: 'email' }),
    campo('WhatsApp da rádio (com DDD)', 'whatsapp', { inputmode: 'tel' }),
    no('div', { classe: 'campos' }, campo('Valor padrão (R$)', 'valor', { inputmode: 'decimal' }),
      no('label', { texto: 'Cobrança' }, no('select', { 'data-nova': 'cobranca' },
        Object.entries(COBRANCA).map(([k, t]) => no('option', { value: k, texto: t, selected: k === n.cobranca }))))),
    no('label', { texto: 'O que a rádio alcança' }, no('select', { 'data-nova': 'alcance' },
      no('option', { value: 'municipio', texto: `${m.nome} inteiro`, selected: n.alcance === 'municipio' }),
      no('option', { value: 'comunidades', texto: 'Só as comunidades deste aviso', selected: n.alcance === 'comunidades' }))),
    no('p', { classe: 'ajuda', texto: 'Contato da rádio (empresa), nunca de cliente. Fica na lista da empresa e na auditoria.' }),
    no('div', { classe: 'acoes' }, no('button', { type: 'button', classe: 'prim', 'data-envio-acao': 'salvar-radio', texto: 'Cadastrar rádio' })));
}

function desenharPrevia(cod) {
  const lugar = $(`previa-${cod}`), e = estado.escolha[cod];
  if (!lugar || !e) return;
  const m = estado.resultado.municipios.find(x => x.codigo_ibge === cod), valor = reaisNumero(e.valor), antigo = reaisNumero(e.antigo);
  if (valor === null || Number.isNaN(valor)) return lugar.textContent = 'Informe o valor do envio em R$.';
  if (Number.isNaN(antigo)) return lugar.textContent = 'O custo antigo tem de ser um valor em R$.';
  lugar.textContent = economiaTexto(previaEconomia({ cobranca: e.cobranca, valor, segundosFarol: segundos(estado.avisos[cod]),
    segundosHoje: m.hoje?.segundos ?? null, custoAntigo: antigo }));
}

function desenharFinal(codigo) {
  const f = estado.finais[codigo];
  $(`final-${codigo}`).replaceChildren(...(f ? [no('span', { classe: 'selo final', texto: 'Texto final guardado no histórico' }),
    f !== estado.avisos[codigo] ? ' (o texto mudou depois; baixe o PDF ou copie de novo para guardar)' : ''] : []));
}

function desenharTempo(codigo) {
  $(`tempo-${codigo}`).textContent = tempoTexto(estado.avisos[codigo]);
  desenharFinal(codigo);
  desenharTocador(codigo);
  desenharPrevia(codigo);
}

// o tocador aparece com o áudio do texto atual; se o texto mudou, some (o áudio antigo não vale mais)
function desenharTocador(codigo) {
  const a = audioAtual(codigo), lugar = $(`tocador-${codigo}`);
  if (!lugar) return;
  if (!a) return lugar.replaceChildren();
  if (lugar.querySelector('audio')?.src === a.url) return;
  lugar.replaceChildren(no('audio', { controls: true, src: a.url, preload: 'auto', 'aria-label': 'Áudio do aviso' }),
    no('span', { classe: 'ajuda', texto: `${fmt(Math.round(a.segundos))} s de áudio (voz sintetizada)` }));
}

function desenharProblemas() {
  const p = estado.resultado.planilha;
  $('problemas').hidden = !p.problemas.length;
  if (!p.problemas.length) return;
  $('problemasTitulo').textContent = `${fmt(p.total_problemas)} linha(s) com problema`;
  const motivos = no('ul', {}, Object.entries(p.problemas_por_motivo).map(([m, n]) => no('li', { texto: `${m}: ${fmt(n)}` })));
  const tabela = no('table', {}, no('thead', {}, no('tr', {}, no('th', { texto: 'Linha' }), no('th', { texto: 'Problema' }))),
    no('tbody', {}, p.problemas.map(x => no('tr', {}, no('td', { texto: String(x.linha) }), no('td', { texto: x.motivo })))));
  $('problemasCorpo').replaceChildren(motivos, tabela,
    p.total_problemas > p.problemas.length ? no('p', { classe: 'ajuda', texto: `Mostrando as primeiras ${fmt(p.problemas.length)}.` }) : '');
}

// ---- Conferência humana (passo 3 de um aviso novo): números, travas, correções e a caixa "Conferi" ----
function desenharConferencia() {
  const r = estado.resultado, c = r?.conferencia, lugar = $('conferencia');
  lugar.hidden = !c || estado.origem !== 'novo';
  if (lugar.hidden) return lugar.replaceChildren();
  const t = r.traducao, n = c.numeros, ja = gerado();
  const numeros = no('dl', { classe: 'numeros' }, [['clientes no aviso', n.clientes], ['municípios', n.municipios], ['comunidades', n.comunidades],
    ['com equipamento vital', n.equipamento_vital], ['corrigidas', n.corrigidas], ['rejeitadas', n.rejeitadas]]
    .map(([rot, v]) => no('div', {}, no('dt', { texto: rot }), no('dd', { texto: fmt(v) }))));
  const arquivo = no('p', { classe: 'ajuda', texto: `Arquivo ${t.arquivo.nome}` + (t.arquivo.aba ? `, aba ${t.arquivo.aba}` : '')
    + ` · ${fmt(t.arquivo.linhas)} linhas · colunas reconhecidas: ${t.colunas.join(', ')} · ${fmt(t.arquivo.colunas_ignoradas)} coluna(s) ignorada(s)`
    + ` · tradutor ${t.versao}` });
  const blocos = [no('h3', { texto: 'Conferência da planilha' }), arquivo, numeros,
    no('p', { classe: 'dicas' }, no('span', { classe: 'ajuda', texto: 'O que é: ' }),
      no('span', { texto: 'UC' }), dica('uc', 'UC'), no('span', { texto: 'equipamento vital' }), dica('vital', 'equipamento vital'),
      no('span', { texto: 'corrigida' }), dica('corrigida', 'linha corrigida'), no('span', { texto: 'rejeitada' }), dica('rejeitada', 'linha rejeitada'),
      no('span', { texto: 'limite de rejeição' }), dica('limite', 'limite de rejeição'))];
  if (n.vital_a_confirmar) blocos.push(no('p', { classe: 'ajuda', texto: `${fmt(n.vital_a_confirmar)} cliente(s) sem a informação de equipamento vital (a confirmar).` }));
  if (c.vital_bloqueio.length) blocos.push(no('div', { classe: 'alerta-vermelho', role: 'alert' },
    no('strong', { texto: `Bloqueado: ${fmt(c.vital_bloqueio.length)} linha(s) com equipamento vital rejeitada(s), corrigida(s) ou fora da concessão` }),
    no('ul', {}, c.vital_bloqueio.map(x => no('li', { texto: `Linha ${x.linha}: ${x.texto}${x.motivo ? ` (${x.motivo})` : ''}` }))),
    no('p', { texto: 'Quem usa equipamento vital tem de ser avisado com certeza. Corrija essas linhas na planilha e importe de novo.' })));
  if (c.suspeitos.length) blocos.push(no('div', { classe: 'alerta-amarelo' },
    no('strong', { texto: 'Pontos suspeitos: confira no mapa antes de marcar "Conferi"' }),
    no('ul', {}, c.suspeitos.map(x => no('li', { texto: `${x.texto}${x.municipio ? ` · ${x.municipio} (a maioria em ${x.maioria})` : ''}: `
      + `${fmt(x.ucs)} UC(s), linha(s) ${x.linhas.slice(0, 30).join(', ')}${x.linhas.length > 30 ? '…' : ''}` })))));
  if (t.corrigidas.length) blocos.push(no('details', { classe: 'corrigidas' },
    no('summary', { texto: `${fmt(n.corrigidas)} linha(s) com a coordenada corrigida (em roxo no mapa)` }),
    no('ul', {}, t.corrigidas.map(x => no('li', { texto: `Linha ${x.linha}: ${x.correcao}` })))));
  if (c.rejeicao.acima) {
    const area = no('textarea', { id: 'justificativa', maxlength: String(MAX_JUSTIFICATIVA), rows: '3', readonly: ja,
      'aria-describedby': 'contaJustificativa' });
    area.value = estado.justificativa;
    blocos.push(no('div', { classe: 'alerta-amarelo' },
      no('strong', { texto: `${fmt(c.rejeicao.rejeitadas)} de ${fmt(c.rejeicao.total)} linhas rejeitadas (${pct(c.rejeicao.fracao)}), acima do limite de ${pct(c.rejeicao.limite)}` }),
      no('label', { for: 'justificativa', texto: 'Justificativa para continuar (fica na auditoria com o seu nome)' }), area,
      no('p', { classe: 'ajuda', id: 'contaJustificativa', texto: `${estado.justificativa.length} de ${MAX_JUSTIFICATIVA} caracteres` })));
  }
  const caixa = no('input', { type: 'checkbox', id: 'conferi', disabled: ja || !!c.vital_bloqueio.length });
  caixa.checked = estado.conferi || ja;
  blocos.push(no('label', { classe: 'confirmar', for: 'conferi' }, caixa, no('span', { texto: 'Conferi os números e o mapa' })));
  blocos.push(no('p', { classe: 'ajuda', id: 'motivoGerar', 'aria-live': 'polite' }));
  blocos.push(no('div', { classe: 'acoes' },
    ja ? null : no('button', { type: 'button', 'data-conf': 'relatorio', texto: 'Baixar relatório (CSV)' }),
    pode('baixar_json') ? no('button', { type: 'button', 'data-conf': 'json', texto: 'Baixar JSON (com as UCs)' }) : null));
  if (!ja && r.pacote_vence) blocos.push(no('p', { classe: 'ajuda', texto: `A conferência vale até ${new Date(r.pacote_vence).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}; depois, importe a planilha de novo.` }));
  lugar.replaceChildren(...blocos);
  desenharFunil();
}

// quem pediu, quando e o código; no histórico, mudar a data ou cancelar (quem gera aviso)
function desenharSolicitado() {
  const r = estado.resultado;
  const partes = r ? [solicitadoTexto(r), r.desligamento ? `Tipo: ${r.desligamento.rotulo} (${r.desligamento.motivo})` : ''].filter(Boolean) : [];
  $('solicitado').replaceChildren(...partes.map(t => no('span', { texto: t })), r?.codigo ? dica('codigo', 'código de verificação') : '',
    r?.status === 'cancelado' ? no('span', { classe: 'chip cancelado', texto: 'Desligamento cancelado' }) : '');
  if (r?.id && pode('ver_historico')) $('solicitado').append(no('button', { type: 'button', id: 'baixarComprovante', texto: 'Comprovante (PDF)' }));
  const lugar = $('acoesAviso');
  lugar.hidden = !(r && estado.origem === 'historico' && pode('gerar_aviso') && r.status !== 'cancelado');
  if (lugar.hidden) return lugar.replaceChildren();
  lugar.replaceChildren(no('h3', { texto: 'Mudou alguma coisa?' }),
    no('div', { classe: 'campos' },
      no('label', { texto: 'Nova data ' }, no('input', { type: 'date', id: 'novaData' })),
      no('label', { texto: 'Início ' }, no('input', { type: 'time', id: 'novoInicio', value: '08:00', step: '900' })),
      no('label', { texto: 'Fim ' }, no('input', { type: 'time', id: 'novoFim', value: '14:00', step: '900' }))),
    no('div', { classe: 'acoes' }, no('button', { type: 'button', 'data-aviso': 'data', texto: 'Mudar a data' })),
    no('label', { texto: 'Motivo do cancelamento (vai para a auditoria; sem nome de cliente)' },
      no('input', { id: 'motivoCancelar', maxlength: '200', autocomplete: 'off' })),
    no('div', { classe: 'acoes' }, no('button', { type: 'button', classe: 'perigo', 'data-aviso': 'cancelar', texto: 'Cancelar o desligamento' })));
}

function desenharResultado() {
  desenharAbas();
  desenharConferencia();
  desenharSolicitado();
  if (!estado.resultado) return;
  const r = estado.resultado, f = estado.formulario;
  $('tituloResultado').textContent = estado.origem === 'historico'
    ? `Aviso de ${f.data}, ${f.horario} · gerado em ${dataHora(r.criado_em)}${r.usuario ? ' por ' + r.usuario : ''}`
    : tituloResultado();
  desenharResumo(); desenharMunicipios(); desenharProblemas(); desenharComparativo();
}

function tituloResultado() {
  const f = estado.formulario;
  return `${estado.passo === 4 ? 'Avisos para a rádio' : 'Conferir o resultado'} · ${f.data}, ${f.horario}`
    + (estado.resultado?.id ? ` · aviso nº ${estado.resultado.id}` : '');
}

function desenharHistorico() {
  const lista = historicoFiltrado();
  const itens = lista.map(a => {
    const ucs = a.municipios.reduce((s, m) => s + m.ucs, 0), com = a.municipios.reduce((s, m) => s + m.comunidades.length, 0);
    const seg = a.municipios.reduce((s, m) => s + (m.segundos || 0), 0), [dia, mes] = a.data.split('/');
    return no('button', { type: 'button', classe: 'item item-hist', 'data-historico': a.id,
      'aria-current': estado.resultado?.id === a.id && estado.origem === 'historico' ? 'true' : null },
      no('span', { classe: 'data-bloco', 'aria-hidden': 'true' }, no('span', { classe: 'dia', texto: dia || a.data }),
        mes ? no('span', { classe: 'mes', texto: MES_CURTO(`2000-${mes}`).split('/')[0] }) : null),
      no('span', { classe: 'hist-corpo' },
        no('strong', { texto: `${a.data}, ${a.horario}` }),
        no('span', { classe: 'chips' }, a.municipios.length ? a.municipios.map(m => no('span', { classe: 'chip', texto: `${m.nome}/${m.uf}` }))
          : no('span', { classe: 'chip vazio', texto: 'nenhum município' })),
        no('span', { classe: 'meta', texto: `${fmt(ucs)} UCs · ${fmt(com)} comunidades · cerca de ${fmt(seg)} s no ar` }),
        no('span', { classe: 'meta', texto: `${solicitadoTexto(a) || `Gerado em ${dataHora(a.criado_em)}`} · aviso nº ${a.id}` }),
        no('span', { classe: 'chips' }, a.desligamento ? no('span', { classe: 'chip tipo', texto: a.desligamento.rotulo }) : null,
          a.status === 'cancelado' ? no('span', { classe: 'chip cancelado', texto: 'Cancelado' }) : null,
          a.municipios.some(m => m.texto_final) ? no('span', { classe: 'selo final', texto: 'Texto final guardado' }) : null)));
  });
  const total = estado.historico.length;
  $('contagemHistorico').textContent = total ? (lista.length === total ? `${fmt(total)} aviso(s).` : `${fmt(lista.length)} de ${fmt(total)} aviso(s).`) : '';
  $('listaHistorico').replaceChildren(...(itens.length ? itens
    : [no('p', { classe: 'ajuda', texto: total ? 'Nenhum aviso com esse filtro.' : 'Nenhum aviso gerado ainda.' })]));
}

// ---- Comparativo: o aviso de hoje (fazenda a fazenda) x o aviso por comunidade ----
function desenharComparativo() {
  const c = estado.painel?.comparativo;
  $('comparativoTotal').replaceChildren(...(c && c.municipios ? [no('div', { classe: 'cartao comp-total' },
    no('h2', { texto: 'Em todo o histórico da empresa' }),
    no('p', { texto: `${fmt(c.municipios)} aviso(s) por município com o aviso de hoje: ${tempoNoAr(c.segundos_hoje)} no ar fazenda a fazenda `
      + `(${fmt(c.locais)} locais citados) contra ${tempoNoAr(c.segundos_farol)} por comunidade (${fmt(c.comunidades)} comunidades).` }),
    no('p', { classe: 'comp-economia', texto: `${fmt(Math.round(100 * (1 - c.segundos_farol / Math.max(1, c.segundos_hoje))))}% menos tempo no ar` }))] : []));
  const r = estado.resultado;
  if (!r) return $('comparativo').replaceChildren(no('p', { classe: 'ajuda cartao',
    texto: 'Gere um aviso em "Novo aviso" (com a coluna local na planilha) ou abra um aviso do Histórico para comparar.' }));
  $('comparativo').replaceChildren(...r.municipios.map(m => {
    const cod = m.codigo_ibge, hoje = m.hoje, texto = estado.avisos[cod], seg = segundos(texto);
    const lado = (classe, titulo, numeros, corpo, acao) => no('section', { classe: `comp-lado ${classe}` },
      no('h3', { texto: titulo }), no('p', { classe: 'comp-numeros', texto: numeros }), corpo,
      acao && temAudio() ? no('button', { type: 'button', 'data-comp': acao, 'data-codigo': cod, texto: 'Ouvir' }) : null,
      acao ? no('div', { id: `tocador-${acao}-${cod}`, classe: 'tocador' }) : null);
    const caixa = t => no('div', { classe: 'texto-longo', tabindex: '0', texto: t });
    const ladoHoje = hoje
      ? lado('hoje', 'Hoje: fazenda a fazenda', `${fmt(hoje.locais)} locais · ${fmt(hoje.palavras)} palavras · cerca de ${tempoNoAr(hoje.segundos)} no ar`,
        hoje.texto ? caixa(hoje.texto) : no('p', { classe: 'ajuda', texto: 'O histórico guarda só as contagens do aviso de hoje (o texto lista imóveis e ruas).' }),
        hoje.texto ? 'hoje' : null)
      : lado('hoje', 'Hoje: fazenda a fazenda', 'sem o aviso de hoje',
        no('p', { classe: 'ajuda', texto: 'A planilha não trouxe a coluna local (o que o aviso de hoje cita para cada UC: o imóvel no rural, a rua no urbano). Sem ela não dá para montar o aviso de hoje.' }), null);
    const ladoFarol = lado('farol', 'Farol: por comunidade', `${fmt(m.comunidades.length)} comunidades · ${fmt(palavras(texto))} palavras · cerca de ${tempoNoAr(seg)} no ar`,
      caixa(texto), 'farol');
    const barras = hoje ? no('div', { classe: 'comp-barras', role: 'img', 'aria-label': `Hoje ${tempoNoAr(hoje.segundos)}, Farol ${tempoNoAr(seg)}` },
      no('span', { classe: 'comp-rotulo', texto: 'Hoje' }), no('span', { classe: 'comp-barra hoje' }, no('span', { estilo: { width: '100%' } })),
      no('span', { classe: 'comp-tempo', texto: tempoNoAr(hoje.segundos) }),
      no('span', { classe: 'comp-rotulo', texto: 'Farol' }),
      no('span', { classe: 'comp-barra farol' }, no('span', { estilo: { width: `${Math.max(1, Math.round(100 * seg / Math.max(1, hoje.segundos)))}%` } })),
      no('span', { classe: 'comp-tempo', texto: tempoNoAr(seg) })) : null;
    return no('article', { classe: 'cartao comp', 'data-codigo': cod },
      no('div', { classe: 'mun-cab' }, no('h2', { texto: `${m.nome}/${m.uf}` }),
        hoje ? no('span', { classe: 'comp-economia', texto: `${fmt(Math.round(100 * (1 - seg / Math.max(1, hoje.segundos))))}% menos tempo no ar` }) : null),
      barras, no('div', { classe: 'comp-lados' }, ladoHoje, ladoFarol));
  }));
}

// ---- Relatório do período (mensal) ----
function desenharFiltrosRelatorio() {
  const r = estado.relatorio, op = r?.opcoes;
  if (!$('relMes').options.length) $('relMes').replaceChildren(...ultimosMeses().map(([v, t]) => no('option', { value: v, texto: t })));
  if (!op) return;
  const preencher = (id, todos, itens) => {
    const atual = $(id).value;
    $(id).replaceChildren(no('option', { value: '', texto: todos }), ...itens.map(([v, t]) => no('option', { value: String(v), texto: t, selected: String(v) === atual })));
  };
  preencher('relMunicipio', 'Todos', op.municipios);
  preencher('relTipo', 'Todos', op.tipos.map(t => [t, op.rotulos_tipos[t] || t]));
  preencher('relRadio', 'Todas', op.radios);
  preencher('relPessoa', 'Todas', op.pessoas.map(p => [p, p]));
}

function desenharRelatorio() {
  desenharFiltrosRelatorio();
  const r = estado.relatorio;
  if (!r) return $('relatorio').replaceChildren();
  const s = r.resumo, tabela = (cab, linhas, vazio = 'Nada neste período.') => linhas.length
    ? no('div', { classe: 'rolagem' }, no('table', { classe: 'tabela' }, no('thead', {}, no('tr', {}, cab.map(t => no('th', { texto: t })))),
      no('tbody', {}, linhas.map(l => no('tr', {}, l.map(v => no('td', { texto: v == null ? '—' : String(v) })))))))
    : no('p', { classe: 'ajuda', texto: vazio });
  const bloco = (titulo, ...filhos) => no('section', { classe: 'cartao dash-bloco' }, no('h2', { texto: titulo }), ...filhos);
  const kpi = (rotulo, valor, extra) => no('div', { classe: 'kpi' }, no('span', { classe: 'kpi-rotulo', texto: rotulo }),
    no('strong', { classe: 'kpi-valor', texto: valor }), extra ? no('span', { classe: 'kpi-extra', texto: extra }) : null);
  const comp = r.comparacao ? bloco(`Comparação com ${r.comparacao.periodo}`, tabela(['Número', 'Este período', 'Anterior', 'Diferença'],
    Object.entries(r.comparacao.numeros).map(([k, v]) => [{ desligamentos: 'Desligamentos', avisos: 'Avisos', ucs: 'UCs', envios: 'Envios',
      confirmados: 'Confirmados', segundos_no_ar: 'Segundos no ar', custo: 'Custo (R$)', economia_calculada: 'Economia calculada (R$)',
      economia_informada: 'Economia informada (R$)', tempo_economizado: 'Segundos economizados', pct_no_prazo: '% no prazo' }[k], v.atual, v.anterior, v.diferenca]))) : null;
  $('relatorio').replaceChildren(
    no('h2', { classe: 'subtitulo', texto: `${r.periodo.rotulo[0].toUpperCase()}${r.periodo.rotulo.slice(1)}` + (Object.keys(r.filtros).length ? ' (com filtros)' : '') }),
    no('div', { classe: 'kpis' },
      kpi('Desligamentos', fmt(s.desligamentos), `${fmt(s.cancelados)} cancelado(s)`),
      kpi('Avisos e comunidades', `${fmt(s.avisos)} · ${fmt(s.comunidades)}`, `${fmt(s.ucs)} UCs, ${fmt(s.equipamento_vital)} com equipamento vital`),
      kpi('Envios às rádios', fmt(s.envios), `${fmt(s.confirmados)} confirmado(s), ${fmt(s.falharam)} falha(s)`),
      kpi('Tempo no ar', tempoNoAr(s.segundos_no_ar), tempoArTexto(s.tempo_economizado)),
      kpi('Custo', dinheiro(s.custo)),
      kpi('Economia', dinheiro(Number(s.economia_calculada) + Number(s.economia_informada)),
        `${dinheiro(s.economia_calculada)} calculada · ${dinheiro(s.economia_informada)} informada`),
      kpi('No prazo', s.pct_no_prazo == null ? '—' : `${s.pct_no_prazo.toLocaleString('pt-BR')}%`, `${fmt(s.no_prazo)} de ${fmt(s.com_envio)} com envio`)),
    comp,
    bloco('Por tipo de desligamento', tabela(['Tipo', 'Desligamentos', 'UCs'], r.por_tipo.map(x => [x.rotulo, fmt(x.desligamentos), fmt(x.ucs)]))),
    bloco('Por rádio', tabela(['Rádio', 'Envios', 'Confirmados', 'Tempo no ar', 'Custo', 'Economia'],
      r.por_radio.map(x => [x.radio, fmt(x.envios), fmt(x.confirmados), tempoNoAr(x.segundos), dinheiro(x.custo), dinheiro(x.economia)]))),
    bloco('Comunidades mais afetadas', tabela(['Comunidade', 'Distrito', 'Município', 'Avisos', 'UCs'],
      r.por_comunidade.map(x => [semSufixo(x.comunidade), x.distrito, x.municipio, fmt(x.avisos), fmt(x.ucs)]))),
    bloco('Avisos fora do prazo', tabela(['Aviso', 'Desligamento', 'Municípios', 'Regra', 'Atraso'],
      r.fora_do_prazo.map(x => [`nº ${x.aviso}`, `${x.data}, ${x.horario}`, x.municipios, x.regra, `${x.atraso_horas} h`]), 'Nenhum aviso fora do prazo.'),
      r.sem_envio.length ? no('p', { classe: 'ajuda', texto: `Sem envio registrado (fora da conta do prazo): ${r.sem_envio.map(x => `nº ${x.aviso}`).join(', ')}.` }) : null),
    bloco('Como a economia foi calculada', dica('economia', 'economia calculada e informada'), no('ul', { classe: 'como' }, r.como_calculado.map(t => no('li', { texto: t })))),
    bloco('Lista detalhada', tabela(['Aviso', 'Desligamento', 'Tipo', 'Municípios', 'UCs', 'Rádios', 'Envios', 'Custo', 'No prazo', 'Pedido por', 'Situação'],
      r.lista.map(x => [`nº ${x.aviso}`, `${x.data}, ${x.horario}`, x.tipo, x.municipios, fmt(x.ucs), x.radios, `${x.confirmados}/${x.envios}`,
        dinheiro(x.custo), x.no_prazo == null ? '—' : x.no_prazo ? 'sim' : 'não', x.por, x.status]))));
}

// ---- Dashboard: só números do histórico da empresa ----
function desenharPainel() {
  const d = estado.painel;
  if (!d) return $('painelDash').replaceChildren();
  const t = d.totais;
  const kpi = (rotulo, valor, extra) => no('div', { classe: 'kpi' }, no('span', { classe: 'kpi-rotulo', texto: rotulo }),
    no('strong', { classe: 'kpi-valor', texto: valor }), extra ? no('span', { classe: 'kpi-extra', texto: extra }) : null);
  const mesKpi = d.mes ? no('div', { classe: 'cartao dash-bloco' }, no('h2', { texto: `Este mês (${d.mes.mes})` }),
    no('div', { classe: 'kpis' },
      kpi('Gasto com rádio', dinheiro(d.mes.gasto), `${fmt(d.mes.envios)} envio(s), ${fmt(d.mes.confirmados)} confirmado(s)`),
      kpi('Economizado', dinheiro(Number(d.mes.economia_calculada) + Number(d.mes.economia_informada)),
        `${dinheiro(d.mes.economia_calculada)} calculada · ${dinheiro(d.mes.economia_informada)} informada`),
      kpi('Desligamentos', fmt(d.mes.desligamentos), tempoArTexto(d.mes.tempo_economizado)),
      kpi('No prazo', d.mes.pct_no_prazo == null ? '—' : `${d.mes.pct_no_prazo.toLocaleString('pt-BR')}%`, `${fmt(d.mes.com_envio)} com envio`))) : null;
  const kpis = no('div', { classe: 'kpis' },
    kpi('Avisos gerados', fmt(t.avisos), `${fmt(t.ultimos_30_dias)} nos últimos 30 dias`),
    kpi('UCs avisadas', fmt(t.ucs)),
    kpi('Comunidades citadas', fmt(t.comunidades)),
    kpi('Municípios', fmt(t.municipios)),
    kpi('Com equipamento vital', fmt(t.com_equipamento_vital), 'avisos com prazo de 5 dias úteis'),
    kpi('Tempo médio no ar', `${fmt(t.segundos_medio)} s`, `${fmt(t.textos_finais)} de ${fmt(t.avisos_municipio)} textos finais guardados`));
  const maxMes = Math.max(1, ...d.por_mes.map(m => m.avisos));
  const meses = no('div', { classe: 'cartao dash-bloco' }, no('h2', { texto: 'Avisos por mês' }),
    no('div', { classe: 'barras', role: 'img', 'aria-label': d.por_mes.map(m => `${MES_CURTO(m.mes)}: ${m.avisos}`).join(', ') },
      d.por_mes.map(m => no('div', { classe: 'barra-mes', title: `${MES_CURTO(m.mes)}: ${fmt(m.avisos)} aviso(s), ${fmt(m.ucs)} UCs` },
        no('span', { classe: 'barra-valor', texto: m.avisos ? fmt(m.avisos) : '' }),
        no('span', { classe: 'barra', estilo: { height: `${Math.round(m.avisos / maxMes * 100)}%` } }),
        no('span', { classe: 'barra-mes-rotulo', texto: MES_CURTO(m.mes) })))));
  const ranking = (titulo, itens, rotulo, vazio) => {
    const max = Math.max(1, ...itens.map(i => i.avisos));
    return no('div', { classe: 'cartao dash-bloco' }, no('h2', { texto: titulo }),
      itens.length ? no('ol', { classe: 'ranking' }, itens.map(i => no('li', {},
        no('span', { classe: 'ranking-nome', texto: rotulo(i) }),
        no('span', { classe: 'ranking-barra' }, no('span', { estilo: { width: `${Math.round(i.avisos / max * 100)}%` } })),
        no('span', { classe: 'ranking-valor', texto: `${fmt(i.avisos)} · ${fmt(i.ucs)} UCs` }))))
        : no('p', { classe: 'ajuda', texto: vazio }));
  };
  const proximos = no('div', { classe: 'cartao dash-bloco' }, no('h2', { texto: 'Próximos desligamentos' }),
    d.proximos.length ? no('ul', { classe: 'proximos' }, d.proximos.map(x => no('li', {},
      no('span', { classe: 'chip', texto: dataLonga(x.data) }),
      no('span', { texto: `${x.horario} · ${x.municipios.join(', ') || 'nenhum município'} · ${fmt(x.ucs)} UCs` }))))
      : no('p', { classe: 'ajuda', texto: 'Nenhum desligamento com data a partir de hoje.' }));
  $('painelDash').replaceChildren(...[mesKpi].filter(Boolean), kpis, meses, proximos,
    ranking('Municípios com mais avisos', d.municipios, i => `${i.nome}/${i.uf}`, 'Nenhum aviso ainda.'),
    ranking('Comunidades mais citadas', d.comunidades, i => `${semSufixo(i.nome)} (${i.municipio})`, 'Nenhum aviso ainda.'));
}

function desenharUsuarios() {
  $('novoPerfil').replaceChildren(...Object.entries(estado.perfis).map(([k, n]) => no('option', { value: k, texto: n, selected: k === 'operador' })));
  if (!$('novoMunicipios').options.length) $('novoMunicipios').replaceChildren(...municipiosDaConcessao().map(([c, n]) => no('option', { value: c, texto: n })));
  $('listaUsuarios').replaceChildren(...estado.usuarios.map(x => no('div', { classe: 'item usuario-linha', 'data-usuario': x.id },
    no('div', {}, no('strong', { texto: x.nome }), no('br'),
      no('span', { classe: 'meta', texto: `${x.email} · ${x.ultimo_acesso ? 'último acesso ' + dataHora(x.ultimo_acesso) : 'nunca entrou'}`
        + (x.trocar_senha ? ' · senha temporária' : '') }), no('br'),
      no('span', { classe: 'meta', texto: `Municípios: ${x.municipios.length ? x.municipios.map(nomeMunicipio).join(', ') : 'todos (nenhum escolhido)'}` })),
    no('div', { classe: 'controles' },
      no('select', { 'aria-label': `Perfil de ${x.nome}`, 'data-campo': 'perfil' },
        Object.entries(estado.perfis).map(([k, n]) => no('option', { value: k, texto: n, selected: k === x.perfil }))),
      no('select', { 'aria-label': `Situação de ${x.nome}`, 'data-campo': 'status' },
        [['ativo', 'Ativo'], ['bloqueado', 'Bloqueado']].map(([k, n]) => no('option', { value: k, texto: n, selected: k === x.status }))),
      no('select', { 'aria-label': `Municípios de ${x.nome}`, 'data-campo': 'municipios', multiple: true, size: '3' },
        municipiosDaConcessao().map(([c, n]) => no('option', { value: c, texto: n, selected: x.municipios.includes(c) }))),
      no('button', { type: 'button', 'data-acao-usuario': 'salvar', texto: 'Salvar' }),
      no('button', { type: 'button', 'data-acao-usuario': 'senha', texto: 'Nova senha temporária' })))));
}

function desenharEmpresas() {
  const linhas = estado.empresas.map(e => no('tr', { 'data-empresa': e.id }, no('td', { texto: e.nome }), no('td', { texto: e.sigla }),
    no('td', { classe: 'codigo', texto: e.cnpj || '—' }), no('td', { texto: e.dominio }),
    no('td', {}, no('span', { classe: `chip ${e.status === 'suspensa' ? 'cancelado' : ''}`, texto: e.status === 'suspensa' ? 'Suspensa' : 'Ativa' })),
    no('td', { texto: fmt(e.usuarios) }), no('td', { texto: fmt(e.avisos) }),
    no('td', {}, no('button', { type: 'button', classe: e.status === 'ativa' ? 'perigo' : '', 'data-empresa-acao': e.status === 'ativa' ? 'suspensa' : 'ativa',
      texto: e.status === 'ativa' ? 'Suspender' : 'Reativar' }))));
  $('listaEmpresas').replaceChildren(no('div', { classe: 'rolagem' }, no('table', { classe: 'tabela' },
    no('thead', {}, no('tr', {}, ['Empresa', 'Sigla', 'CNPJ', 'Domínio', 'Situação', 'Usuários', 'Avisos', 'Ações'].map(t => no('th', { texto: t })))),
    no('tbody', {}, linhas))));
}

// ---- Rádios (Admin da empresa) ----
function desenharRadios() {
  const r = estado.radioEditando;
  $('formRadioTitulo').textContent = r ? `Editar ${r.nome}` : 'Cadastrar rádio';
  $('radSalvar').textContent = r ? 'Salvar alterações' : 'Cadastrar rádio';
  $('radCancelar').hidden = !r;
  if (!$('radMunicipios').options.length) {
    $('radMunicipios').replaceChildren(...municipiosDaConcessao().map(([c, n]) => no('option', { value: c, texto: n })));
    $('radMunCom').replaceChildren(no('option', { value: '', texto: 'Escolha o município' }), ...municipiosDaConcessao().map(([c, n]) => no('option', { value: c, texto: n })));
  }
  desenharComunidadesRadio();
  $('listaRadios').replaceChildren(...(estado.radiosAdmin.length ? estado.radiosAdmin.map(x => no('div', { classe: 'item', 'data-radio': x.id },
    no('strong', { texto: x.nome + (x.ativa ? '' : ' (inativa)') }),
    no('span', { classe: 'meta', texto: [x.email, x.whatsapp].filter(Boolean).join(' · ') }),
    no('span', { classe: 'meta', texto: `${x.valor_padrao ? dinheiro(x.valor_padrao) : 'sem valor padrão'} (${COBRANCA[x.cobranca]}) · alcança `
      + [x.alcance.municipios.map(nomeMunicipio).join(', '), x.alcance.comunidades.length ? `${x.alcance.comunidades.length} comunidade(s)` : '']
        .filter(Boolean).join(' e ') || 'nada cadastrado' }),
    no('div', { classe: 'acoes' }, no('button', { type: 'button', 'data-radio-acao': 'editar', texto: 'Editar' }))))
    : [no('p', { classe: 'ajuda', texto: 'Nenhuma rádio cadastrada.' })]));
}

function desenharComunidadesRadio() {
  const cod = $('radMunCom').value, terr = estado.territorios[cod];
  const marcadas = new Set(estado.alcanceComunidades.map(c => `${c.municipio}|${c.nome}|${c.distrito}`));
  const resumo = no('p', { classe: 'ajuda', id: 'radResumo', texto: resumoComunidades() });
  if (!cod || !terr) return $('radComunidades').replaceChildren(resumo);
  const vistas = new Set(), lista = [];
  for (const f of terr.features) {
    const nome = semSufixo(f.properties.nome), dist = f.properties.distrito, chave = `${cod}|${nome}|${dist}`;
    if (vistas.has(chave)) continue;
    vistas.add(chave);
    lista.push([chave, nome, dist]);
  }
  lista.sort((a, b) => a[1].localeCompare(b[1], 'pt-BR'));
  $('radComunidades').replaceChildren(resumo, ...lista.map(([chave, nome, dist]) => no('label', { classe: 'check' },
    no('input', { type: 'checkbox', 'data-comunidade': chave, checked: marcadas.has(chave) }),
    no('span', { texto: `${nome} (${dist === nomeMunicipio(cod).split('/')[0] ? 'Sede' : dist})` }))));
}

const resumoComunidades = () => estado.alcanceComunidades.length ? `Comunidades escolhidas: ${estado.alcanceComunidades
  .map(c => `${c.nome} (${c.distrito === nomeMunicipio(c.municipio).split('/')[0] ? 'Sede' : c.distrito})`).join(', ')}.` : '';

// ---- Configurações da empresa (Admin da empresa) ----
function desenharConfig() {
  const c = estado.configuracao;
  if (!c) return;
  if (!$('cfgFuso').options.length) $('cfgFuso').replaceChildren(...FUSOS_UTM.map(([k, t]) => no('option', { value: String(k), texto: `${t} (EPSG:${k})` })));
  $('cfgModelo').value = c.modelo_mensagem;
  $('cfgNome').value = c.nome_mensagem;
  $('cfgTelefone').value = c.telefone || '';
  $('cfgLimite').value = String(Math.round(c.limite_rejeicao * 1000) / 10);
  $('cfgFuso').value = String(c.epsg_utm);
  $('cfgAntecedencia').value = String(c.antecedencia_dias);
  $('cfgCampos').textContent = `Campos: ${c.campos.map(x => `{${x}}`).join(' ')}. Trecho entre [colchetes] some se algum campo dentro dele ficar vazio.`;
  desenharPreviaConfig();
}

function desenharPreviaConfig() {
  $('cfgPrevia').textContent = 'Exemplo: ' + montarMensagem($('cfgModelo').value, { distribuidora: $('cfgNome').value, municipio: 'Leopoldina', data: '20/11',
    inicio: '8h', fim: '14h', motivo: 'manutenção preventiva na rede', comunidades: 'Graminha, Boa Sorte e São Pedro',
    comunidades_parciais: 'Tomé Nogueira', telefone_atendimento: $('cfgTelefone').value, codigo: 'FRL-0000-0000-0000' });
}

function desenharRegistro() {
  const linhas = estado.registro.map(r => no('tr', {}, no('td', { texto: dataHora(r.quando) }),
    no('td', { texto: r.usuario ? `${r.usuario}${r.perfil ? ` (${r.perfil})` : ''}` : '—' }),
    no('td', { texto: r.empresa || '—' }), no('td', { texto: r.acao }), no('td', { texto: r.detalhe }),
    no('td', { classe: 'codigo', texto: r.codigo || '' })));
  $('listaRegistro').replaceChildren(no('table', { classe: 'tabela' },
    no('thead', {}, no('tr', {}, ['Quando', 'Quem', 'Empresa', 'O quê', 'Detalhe', 'Código'].map(t => no('th', { texto: t })))),
    no('tbody', {}, linhas)));
}

function mostrarSenhaTemporaria(texto, senha) {
  $('caixaTexto').textContent = texto;
  $('caixaSenhaValor').textContent = senha;
  $('caixaSenha').hidden = false;
  $('caixaFechar').focus();
}

// ---- Mapa ----
const escuro = () => temaAtual() === 'escuro';
const COR = { ambar: '#F5B83D', ambarForte: '#B07800', cinza: '#93A1AF', info: '#1663C7', erro: '#B42318', verde: '#D99A16', corrigida: '#7A4FD1' };
let mapa, camadaConcessao, camadaComunidades, camadaUcs, telaUcs, camadaBase, camadaNomes, camadaRede, telaRede, atribuicao;
// a partir deste zoom, o contorno das comunidades dos municípios na tela; a partir do outro, os nomes escritos
const ZOOM_COMUNIDADES = 11, ZOOM_NOMES = 13, ZOOM_TRAFOS = 14;
const CREDITO_REDE = 'Rede fictícia sobre as vias do © OpenStreetMap';
const CORES_ALIMENTADOR = ['#1663C7', '#7A4FD1', '#0F8F86', '#C2410C', '#9D174D', '#4D7C0F', '#0E7490', '#A16207'];
const buscando = new Set();   // municípios cujas comunidades estão sendo buscadas

let fundoDoMapa;
function trocarFundoDoMapa() {
  if (!mapa) return;
  fundoDoMapa?.remove();
  fundoDoMapa = L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${escuro() ? 'Dark' : 'Light'}_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
    { attribution: 'Fundo &copy; Esri', maxZoom: 16, noWrap: true }).addTo(mapa);
  fundoDoMapa.bringToBack();
}

function iniciarMapa() {
  if (mapa) return;
  mapa = L.map('mapa', { zoomControl: true, attributionControl: false, minZoom: 5, maxZoom: 16 });
  atribuicao = L.control.attribution({ prefix: 'Concessão e comunidades: IBGE · Leaflet' }).addTo(mapa);
  trocarFundoDoMapa();
  mapa.setView([-21.0, -42.6], 8);
  mapa.on('moveend', aoMoverMapa);
}

// municípios da concessão que aparecem na tela (pelo retângulo do contorno)
const municipiosNaTela = () => !camadaConcessao ? [] : camadaConcessao.getLayers()
  .filter(l => mapa.getBounds().intersects(l.getBounds())).map(l => l.feature.properties);
const distritoDe = (distrito, municipio) => distrito === municipio ? 'Sede' : distrito;

// comunidades dos municípios na tela, fora os do aviso (esses a desenharComunidades destaca)
function desenharBase() {
  camadaBase?.remove();
  camadaBase = null;
  if (!mapa || mapa.getZoom() < ZOOM_COMUNIDADES) return;
  const doAviso = new Set((estado.resultado?.municipios || []).map(m => m.codigo_ibge));
  const feicoes = municipiosNaTela().filter(m => !doAviso.has(m.codigo_ibge) && estado.territorios[m.codigo_ibge])
    .flatMap(m => estado.territorios[m.codigo_ibge].features.map(f => ({ ...f, properties: { ...f.properties, municipio: m.nome } })));
  if (!feicoes.length) return;
  camadaBase = L.geoJSON({ type: 'FeatureCollection', features: feicoes }, {
    style: { color: COR.cinza, weight: .8, fillOpacity: 0 },
    onEachFeature: (f, l) => l.bindTooltip(() => no('span', {
      texto: `${semSufixo(f.properties.nome)} (${distritoDe(f.properties.distrito, f.properties.municipio)}) · ${f.properties.municipio}` }), { sticky: true }),
  }).addTo(mapa);
  camadaBase.bringToBack();
  camadaConcessao?.bringToBack();
}

// nome escrito de cada comunidade na tela (só de perto), num ponto sempre dentro dela; o nome entra como texto.
// As maiores (mais endereços) primeiro; um nome que encostaria em outro já escrito fica para um zoom maior.
function desenharNomes() {
  camadaNomes?.remove();
  camadaNomes = null;
  if (!mapa || mapa.getZoom() < ZOOM_NOMES) return;
  const tela = mapa.getBounds().pad(.2), marcas = [], ocupado = [];
  const candidatas = municipiosNaTela().flatMap(m => estado.territorios[m.codigo_ibge]?.features || [])
    .filter(f => f.properties.rotulo && tela.contains(f.properties.rotulo))
    .sort((a, b) => b.properties.enderecos - a.properties.enderecos);
  for (const f of candidatas) {
    const nome = semSufixo(f.properties.nome), c = mapa.latLngToContainerPoint(f.properties.rotulo);
    const caixa = { x0: c.x - nome.length * 3.4 - 4, x1: c.x + nome.length * 3.4 + 4, y0: c.y - 9, y1: c.y + 9 };  // ~6,8 px por letra
    if (ocupado.some(o => caixa.x0 < o.x1 && o.x0 < caixa.x1 && caixa.y0 < o.y1 && o.y0 < caixa.y1)) continue;
    ocupado.push(caixa);
    marcas.push(L.marker(f.properties.rotulo, { interactive: false, keyboard: false,
      icon: L.divIcon({ className: 'rotulo', html: no('span', { texto: nome }), iconSize: null }) }));
  }
  if (marcas.length) camadaNomes = L.layerGroup(marcas).addTo(mapa);
}

// rede elétrica FICTÍCIA dos municípios na tela (de perto): média tensão por alimentador, subestação,
// chaves e, mais de perto, os trafos. Só demonstração; nada de cliente.
function desenharRede() {
  camadaRede?.remove();
  camadaRede = null;
  const botao = $('botaoRede');
  botao.textContent = estado.verRede ? 'Esconder rede fictícia' : 'Mostrar rede fictícia';
  botao.setAttribute('aria-pressed', String(estado.verRede));
  $('legendaRede').hidden = !estado.verRede;
  atribuicao?.removeAttribution(CREDITO_REDE);
  if (!mapa || !estado.verRede || mapa.getZoom() < ZOOM_COMUNIDADES) return;
  telaRede ||= L.canvas({ padding: .3 });
  const partes = [];
  for (const m of municipiosNaTela()) {
    const r = estado.redes[m.codigo_ibge];
    if (!r) continue;
    const cor = a => CORES_ALIMENTADOR[(parseInt(a.split('-').pop(), 10) - 1) % CORES_ALIMENTADOR.length] || COR.info;
    partes.push(L.geoJSON(r.alimentadores, {
      style: f => ({ color: cor(f.properties.alimentador), weight: 2.2, opacity: .9 }),
      onEachFeature: (f, l) => l.bindTooltip(() => no('span', { texto: `Alimentador ${f.properties.alimentador} (fictício) · ${m.nome}` }), { sticky: true }),
    }));
    if (mapa.getZoom() >= ZOOM_TRAFOS)
      for (const [lat, lon] of r.trafos)
        partes.push(L.circleMarker([lat, lon], { renderer: telaRede, radius: 2.5, weight: 0, fillColor: COR.cinza, fillOpacity: .9, interactive: false }));
    for (const [lat, lon, codigo, alim, jusante] of r.chaves)
      partes.push(L.circleMarker([lat, lon], { radius: 4.5, weight: 1.5, color: '#FFFFFF', fillColor: cor(alim), fillOpacity: 1 })
        .bindTooltip(() => no('span', { texto: `Chave ${codigo} (fictícia) · alimentador ${alim} · ${fmt(jusante)} unidades a jusante` })));
    const se = r.subestacao;
    partes.push(L.marker(se.ponto, { keyboard: false, icon: L.divIcon({ className: 'subestacao', html: no('span'), iconSize: [16, 16] }) })
      .bindTooltip(() => no('span', { texto: se.nome })));
  }
  if (!partes.length) return;
  camadaRede = L.layerGroup(partes).addTo(mapa);
  atribuicao.addAttribution(CREDITO_REDE);
}

function desenharLegenda() {
  const min = estado.legendaMinimizada;
  $('legenda').classList.toggle('minimizada', min);
  $('botaoLegenda').setAttribute('aria-expanded', String(!min));
  $('botaoLegendaTexto').textContent = min ? 'Legenda' : 'Minimizar legenda';
  $('botaoLegenda').querySelector('.seta').textContent = min ? '▸' : '▾';
}

function alternarLegenda() {
  estado.legendaMinimizada = !estado.legendaMinimizada;
  try { localStorage.setItem('farol.legenda', estado.legendaMinimizada ? 'minimizada' : 'aberta'); } catch (e) { /* sem armazenamento: só nesta visita */ }
  desenharLegenda();
}

// busca (uma vez) o que falta dos municípios na tela: comunidades e, com a rede ligada, a rede fictícia
async function buscarNaTela() {
  const tarefas = [];
  for (const m of municipiosNaTela()) {
    const c = m.codigo_ibge;
    if (!estado.territorios[c] && !buscando.has(c))
      tarefas.push([c, async () => { estado.territorios[c] = await api(`/api/municipios/${c}/comunidades`); }]);
    if (estado.verRede && !(c in estado.redes) && !buscando.has(`rede ${c}`))
      tarefas.push([`rede ${c}`, async () => {
        try { estado.redes[c] = await api(`/api/municipios/${c}/rede`); } catch (e) { if (e.status === 404) estado.redes[c] = null; else throw e; }
      }]);
  }
  await Promise.all(tarefas.map(async ([chave, fazer]) => {
    buscando.add(chave);
    try { await fazer(); } catch (e) { /* tenta de novo no próximo movimento */ }
    buscando.delete(chave);
  }));
}

async function aoMoverMapa() {
  if (mapa.getZoom() >= ZOOM_COMUNIDADES && estado.tela === 'app') await buscarNaTela();
  desenharBase(); desenharNomes(); desenharRede();
  document.documentElement.dataset.mapa = `z${mapa.getZoom()}`;
}

async function alternarRede() {
  estado.verRede = !estado.verRede;
  desenharRede();
  if (estado.verRede && mapa.getZoom() >= ZOOM_COMUNIDADES) { await buscarNaTela(); desenharRede(); }
  else if (estado.verRede) avisar('A rede fictícia aparece de perto: aproxime num município (ou clique nele).');
}

function desenharConcessao() {
  if (!estado.concessao) return;
  const afetados = new Set((estado.resultado?.municipios || []).map(m => m.codigo_ibge));
  const contagem = estado.vista === 'painel' && estado.painel ? estado.painel.por_municipio : null;
  const maxAvisos = contagem ? Math.max(1, ...Object.values(contagem)) : 1;
  $('mapa').closest('.mapa-area').querySelector('.legenda-painel').hidden = !contagem;
  camadaConcessao?.remove();
  camadaConcessao = L.geoJSON(estado.concessao, {
    style: f => contagem
      ? { color: contagem[f.properties.codigo_ibge] ? COR.verde : COR.cinza, weight: contagem[f.properties.codigo_ibge] ? 1.5 : .8,
          fillColor: COR.verde, fillOpacity: contagem[f.properties.codigo_ibge] ? .15 + .55 * contagem[f.properties.codigo_ibge] / maxAvisos : .03 }
      : afetados.has(f.properties.codigo_ibge)
        ? { color: COR.info, weight: 2.5, fillOpacity: 0 }
        : { color: COR.cinza, weight: .8, fillColor: COR.cinza, fillOpacity: .05 },
    onEachFeature: (f, l) => {
      l.bindTooltip(() => no('span', { texto: `${f.properties.nome}/${f.properties.uf}`
        + (contagem ? ` · ${fmt(contagem[f.properties.codigo_ibge] || 0)} aviso(s)` : '') }), { sticky: true });
      // de longe, clicar no município aproxima nele (e aparecem as comunidades)
      l.on('click', () => { if (mapa.getZoom() < ZOOM_COMUNIDADES) mapa.fitBounds(l.getBounds(), { padding: [20, 20] }); });
    },
  }).addTo(mapa);
  camadaConcessao.bringToBack();
}

function desenharComunidades() {
  camadaComunidades?.remove();
  camadaComunidades = null;
  const r = estado.resultado;
  if (!r) return;
  // as afetadas preenchidas; as outras comunidades dos mesmos municípios só com o contorno, por baixo
  const feicoes = [], outras = [];
  for (const m of r.municipios) {
    const terr = estado.territorios[m.codigo_ibge];
    if (!terr) continue;
    const porNome = new Map(m.comunidades.map(c => [c.nome, c]));
    for (const f of terr.features) {
      const c = porNome.get(f.properties.nome);
      if (c) feicoes.push({ ...f, properties: { ...f.properties, m, c } });
      else outras.push(f);
    }
  }
  if (!feicoes.length) return;
  camadaComunidades = L.geoJSON({ type: 'FeatureCollection', features: [...outras, ...feicoes] }, {
    style: f => !f.properties.c ? { color: COR.cinza, weight: .8, fillOpacity: 0 } : ({
      inteira: { color: COR.ambarForte, weight: 1.5, fillColor: COR.ambar, fillOpacity: .55 },
      parte: { color: COR.ambarForte, weight: 1.5, dashArray: '5 4', fillColor: COR.ambar, fillOpacity: .22 },
      vizinha: { color: COR.cinza, weight: 1, fillColor: COR.cinza, fillOpacity: .25 },
    })[situacao(f.properties.c)],
    onEachFeature: (f, l) => {
      const { c, m } = f.properties;
      if (!c) return l.bindTooltip(() => no('span', { texto: `${semSufixo(f.properties.nome)} · fora do aviso` }), { sticky: true });
      l.bindTooltip(() => no('span', {}, no('strong', { texto: nomeComDistrito(c, m) }), ` · ${ROTULO[situacao(c)]}`, no('br'),
        `${fmt(c.afetadas)} UCs afetadas · ${fmt(c.total)} endereços na comunidade`), { sticky: true });
    },
  }).addTo(mapa);
  mapa.fitBounds(camadaComunidades.getBounds(), { padding: [30, 30], maxZoom: 13 });
}

// pontos das UCs da planilha: só os do envio atual, desenhados num canvas (nada no HTML) e sem o
// número da UC; a dica mostra só a comunidade
const temPontos = () => !!estado.resultado && (estado.resultado.municipios.some(m => m.pontos?.length) || !!estado.resultado.pontos_fora?.length
  || !!estado.resultado.pontos_corrigidos?.length);

function desenharUcs() {
  camadaUcs?.remove();
  camadaUcs = null;
  const r = estado.resultado, botao = $('botaoUcs');
  botao.closest('li').hidden = !temPontos();
  botao.textContent = estado.verUcs ? 'Esconder UCs' : 'Mostrar UCs';
  botao.setAttribute('aria-pressed', String(estado.verUcs));
  if (!temPontos() || !estado.verUcs) return;
  telaUcs ||= L.canvas({ padding: .3 });
  const ponto = (lat, lon, cor, dica) => L.circleMarker([lat, lon], { renderer: telaUcs, radius: 3.5, weight: 1, color: '#FFFFFF', fillColor: cor, fillOpacity: .95 })
    .bindTooltip(() => no('span', { texto: dica }));   // nó de texto: o Leaflet poria uma string como HTML
  const marcas = [];
  for (const m of r.municipios) {
    for (const [lat, lon, i] of m.pontos || []) {
      const c = m.comunidades[i];
      marcas.push(ponto(lat, lon, c && situacao(c) !== 'vizinha' ? COR.ambarForte : COR.cinza,
        c ? `UC da planilha · ${nomeComDistrito(c, m)}` : `UC da planilha · ${m.nome}`));
    }
  }
  for (const [lat, lon] of r.pontos_fora || []) marcas.push(ponto(lat, lon, COR.erro, 'UC fora da concessão'));
  // as corrigidas por último (por cima), com a cor própria
  for (const [lat, lon] of r.pontos_corrigidos || []) marcas.push(ponto(lat, lon, COR.corrigida, 'UC com coordenada corrigida (confira)'));
  camadaUcs = L.layerGroup(marcas).addTo(mapa);
  if (!camadaComunidades && marcas.length) mapa.fitBounds(L.featureGroup(marcas).getBounds(), { padding: [30, 30], maxZoom: 13 });
}

// ======================= Controller: eventos e chamadas à API (atualiza o estado e redesenha) =======================
class ErroApi extends Error {
  constructor(status, mensagem, dados = {}) { super(mensagem); this.status = status; this.dados = dados; }
}

async function api(url, opcoes = {}) {
  const r = await fetch(url, { credentials: 'same-origin', ...opcoes,
    headers: opcoes.json ? { 'Content-Type': 'application/json' } : undefined,
    body: opcoes.json ? JSON.stringify(opcoes.json) : opcoes.body });
  const j = await r.json().catch(() => ({}));
  if (r.status === 401 && estado.tela === 'app') { sessaoAcabou(); throw new ErroApi(401, 'A sessão acabou. Entre de novo.'); }
  if (!r.ok) throw new ErroApi(r.status, typeof j.detail === 'string' ? j.detail : 'Não foi possível concluir. Tente de novo.', j);
  return j;
}

// pedido que devolve um arquivo (CSV, JSON): baixa com o nome que o servidor sugere; nada fica na página
// rádios sugeridas e envios do aviso aberto (só depois de gerado; quem só consulta vê os envios)
async function carregarEnvios() {
  const r = estado.resultado;
  if (!r?.id) return;
  try {
    const [envs, sug] = await Promise.all([pode('ver_historico') ? api(`/api/historico/${r.id}/envios`) : { envios: [] },
      pode('gerar_aviso') ? api(`/api/historico/${r.id}/radios`) : null]);
    estado.envios = envs.envios;
    if (sug) { estado.radios = sug.radios; estado.sugestao = Object.fromEntries(sug.municipios.map(x => [x.codigo_ibge, x])); }
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
  for (const m of r.municipios) desenharEnvio(m);
}

function editarEnvio(evento) {
  const alvo = evento.target, sec = alvo.closest('section.envio-radio');
  if (!sec || !(alvo.dataset.envio || alvo.dataset.nova)) return;
  const cod = sec.dataset.codigo, e = estado.escolha[cod];
  if (alvo.dataset.nova) { e.nova[alvo.dataset.nova] = alvo.value; return; }
  e[alvo.dataset.envio] = alvo.value;
  if (alvo.dataset.envio === 'radioId' && evento.type === 'change') {   // outra rádio: o valor sugerido dela
    const radio = estado.radios.find(x => String(x.id) === alvo.value);
    Object.assign(e, alvo.value === 'nova' ? {} : escolhaPadrao(radio));
    return desenharEnvio(estado.resultado.municipios.find(x => x.codigo_ibge === cod));
  }
  desenharPrevia(cod);
}

async function acaoEnvio(evento) {
  const b = evento.target.closest('button[data-envio-acao], button[data-arquivo]');
  if (!b) return;
  if (b.dataset.arquivo) {
    try { await baixarDaApi(`/api/envios/${b.dataset.envioId}/arquivos/${b.dataset.arquivo}`, { method: 'GET' }, `farol-envio.${b.dataset.arquivo}`); }
    catch (e) { if (e.status !== 401) avisar(e.message, true); }
    return;
  }
  const cod = b.closest('section.envio-radio').dataset.codigo, m = estado.resultado.municipios.find(x => x.codigo_ibge === cod);
  b.disabled = true;
  try {
    if (b.dataset.envioAcao === 'salvar-radio') await cadastrarRadio(m);
    else await enviarParaRadio(m, b.dataset.envioAcao);
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    b.disabled = false;
  }
}

async function cadastrarRadio(m) {
  const n = estado.escolha[m.codigo_ibge].nova;
  const alcance = n.alcance === 'municipio' ? { municipios: [m.codigo_ibge] }
    : { comunidades: m.comunidades.map(c => ({ municipio: m.codigo_ibge, nome: semSufixo(c.nome), distrito: c.distrito })) };
  const j = await api('/api/radios', { method: 'POST', json: { nome: n.nome, email: n.email || null, whatsapp: n.whatsapp || null,
    valor_padrao: n.valor || null, cobranca: n.cobranca, alcance } });
  avisar(`${j.radio.nome} cadastrada (registrado na auditoria).`);
  estado.escolha[m.codigo_ibge] = escolhaPadrao(j.radio);
  await carregarEnvios();
}

async function enviarParaRadio(m, canal) {
  const cod = m.codigo_ibge, e = estado.escolha[cod], radio = estado.radios.find(x => String(x.id) === String(e.radioId));
  if (!radio) return avisar('Escolha a rádio.', true);
  const valor = reaisNumero(e.valor), texto = estado.avisos[cod];
  if (valor === null || Number.isNaN(valor)) return avisar('Informe o valor do envio em R$.', true);
  if (canal === 'email') {
    if (!radio.email) return avisar(`${radio.nome} não tem e-mail cadastrado.`, true);
    if (!confirm(`Enviar para ${radio.nome} (${radio.email})?`)) return;
    avisar(`Gerando o PDF${temAudio() ? ' e o MP3' : ''} e enviando para ${radio.nome}…`);
  } else if (canal === 'whatsapp') {
    if (!radio.whatsapp) return avisar(`${radio.nome} não tem WhatsApp cadastrado.`, true);
    if (!confirm(`Abrir o WhatsApp para ${radio.nome} (${radio.whatsapp}) com a mensagem?`)) return;
    const numero = radio.whatsapp.length > 11 ? radio.whatsapp : `55${radio.whatsapp}`;
    window.open(`https://wa.me/${numero}?text=${encodeURIComponent(texto)}`, '_blank', 'noopener');
  } else {
    if (!confirm(`Copiar a mensagem para mandar para ${radio.nome}?`)) return;
    try { await navigator.clipboard.writeText(texto); } catch (x) { return avisar('Não foi possível copiar; selecione o texto e use Ctrl+C.', true); }
  }
  const j = await api(`/api/historico/${estado.resultado.id}/envios`, { method: 'POST', json: { municipio: cod, radio_id: radio.id, canal, texto,
    valor: e.valor, cobranca: e.cobranca, custo_antigo: e.antigo || null } });
  avisar(j.erro || { email: `E-mail entregue ao servidor para ${radio.nome} (${radio.email}). A rádio confirma pelo link do e-mail.`,
    whatsapp: `WhatsApp aberto para ${radio.nome}; o envio ficou registrado.`, copia: `Mensagem copiada para ${radio.nome}; o envio ficou registrado.` }[canal], !!j.erro);
  estado.finais[cod] = texto;
  desenharFinal(cod);
  await carregarEnvios();
}

async function baixarDaApi(url, opcoes, nomePadrao) {
  const r = await fetch(url, { method: 'POST', credentials: 'same-origin', ...opcoes });
  if (r.status === 401) { sessaoAcabou(); throw new ErroApi(401, 'A sessão acabou.'); }
  if (!r.ok) throw new ErroApi(r.status, (await r.json().catch(() => ({}))).detail || 'Não foi possível baixar.');
  const nome = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '')?.[1] || nomePadrao;
  const href = URL.createObjectURL(await r.blob()), link = no('a', { href, download: nome });
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10000);
}

function sessaoAcabou() {
  limparTela();
  estado.tela = 'entrar';
  desenharTela(); desenharEstado();
  mensagemEm('estadoEntrar', 'A sessão acabou. Entre de novo.', true);
}

function avisar(mensagem, erro = false) {
  estado.mensagem = mensagem; estado.erro = erro;
  desenharEstado();
}

async function abrirApp() {
  estado.tela = 'app';
  estado.vista = vistasDoPerfil()[0]?.[0] || 'historico';
  if (estado.vista === 'painel' && !pode('ver_historico')) estado.vista = 'historico';
  desenharTela(); desenharAbas();
  iniciarMapa();
  mapa.invalidateSize();
  [estado.config, estado.concessao] = await Promise.all([api('/api/config'), api('/api/concessao')]);
  $('faixa').textContent = estado.config.aviso_ficticio;
  $('idioma').replaceChildren(...Object.entries(estado.config.idiomas).map(([k, nome]) => no('option', { value: k, texto: nome })));
  $('idioma').value = estado.config.idioma_padrao;
  $('tipo').replaceChildren(...Object.entries(estado.config.tipos).map(([k, nome]) => no('option', { value: k, texto: nome })));
  $('tipo').value = estado.config.tipo_padrao;
  $('tipoOutro').maxLength = estado.config.max_outro;
  desenharConcessao();
  mapa.fitBounds(camadaConcessao.getBounds(), { padding: [20, 20] });
  await irPara(estado.vista);
}

async function aposEntrar(usuario) {
  estado.usuario = usuario;
  if (usuario.trocar_senha) {
    estado.tela = 'senha';
    desenharTela();
    $('senhaAtual').focus();
  } else {
    await abrirApp();
  }
}

async function entrar(evento) {
  evento.preventDefault();
  const email = $('email').value.trim(), senha = $('senha').value;
  if (!email || !senha) return mensagemEm('estadoEntrar', 'Informe o e-mail e a senha.', true);
  $('botaoEntrar').disabled = true;
  try {
    const j = await api('/api/entrar', { method: 'POST', json: { email, senha } });
    $('senha').value = '';
    mensagemEm('estadoEntrar', '');
    await aposEntrar(j.usuario);
  } catch (e) {
    mensagemEm('estadoEntrar', e.message, true);
  } finally {
    $('botaoEntrar').disabled = false;
  }
}

async function trocarSenha(evento) {
  evento.preventDefault();
  const atual = $('senhaAtual').value, nova = $('senhaNova').value, problema = validarSenhaNova(nova, $('senhaNova2').value);
  if (problema) return mensagemEm('estadoSenha', problema, true);
  $('botaoSenha').disabled = true;
  try {
    const j = await api('/api/senha', { method: 'POST', json: { atual, nova } });
    for (const id of ['senhaAtual', 'senhaNova', 'senhaNova2']) $(id).value = '';
    mensagemEm('estadoSenha', '');
    await aposEntrar(j.usuario);
  } catch (e) {
    mensagemEm('estadoSenha', e.message, true);
  } finally {
    $('botaoSenha').disabled = false;
  }
}

// ao sair (ou quando a sessão acaba), nada do usuário anterior fica na página: num computador
// compartilhado, quem entra depois não vê resultados, listas nem o roteiro escondidos
function limparTela() {
  Object.assign(estado, { usuario: null, resultado: null, origem: null, avisos: {}, finais: {}, formulario: null, arquivo: null,
    conferi: false, justificativa: '', abas: [], aba: '',
    historico: [], usuarios: [], perfis: {}, empresas: [], registro: [], mensagem: '', erro: false,
    passo: 1, painel: null, filtroHistorico: { busca: '', periodo: '' } });
  Object.assign(estado, { radios: [], sugestao: {}, envios: [], escolha: {}, relatorio: null });
  for (const id of ['abas', 'resumo', 'municipios', 'problemasCorpo', 'listaHistorico', 'listaUsuarios', 'listaEmpresas', 'listaRegistro',
    'painelDash', 'contagemHistorico', 'conferencia', 'aba', 'solicitado', 'acoesAviso', 'estadoAuditoria', 'relatorio', 'relMes', 'audMes',
    'listaRadios', 'radComunidades', 'ajudaCorpo', 'subabas'])
    $(id).replaceChildren();
  Object.assign(estado, { radiosAdmin: [], radioEditando: null, alcanceComunidades: [], configuracao: null });
  $('caixaAjuda').hidden = true;
  $('dica').hidden = true;
  $('arquivo').value = '';
  $('buscaHistorico').value = ''; $('periodoHistorico').value = '';
  $('resultado').hidden = true;
  camadaComunidades?.remove();
  camadaComunidades = null;
  camadaUcs?.remove();
  camadaUcs = null;
  $('botaoUcs').closest('li').hidden = true;
  for (const a of [...Object.values(estado.audios), ...Object.values(estado.audiosHoje)]) URL.revokeObjectURL(a.url);
  estado.audios = {}; estado.audiosHoje = {};
  $('comparativo').replaceChildren(); $('comparativoTotal').replaceChildren();
  document.documentElement.dataset.farol = 'saiu';
}

async function sair() {
  try { await api('/api/sair', { method: 'POST' }); } catch (e) { /* a sessão já pode ter acabado */ }
  limparTela();
  estado.tela = 'entrar';
  desenharTela(); desenharEstado();
  $('email').focus();
}

async function irPara(vista) {
  estado.vista = vista;
  desenharAbas();
  try {
    if (vista === 'historico') { estado.historico = (await api('/api/historico')).avisos; desenharHistorico(); }
    if (vista === 'painel') { estado.painel = await api('/api/painel'); desenharPainel(); }
    if (vista === 'relatorios') { desenharFiltrosRelatorio(); await carregarRelatorio(); }
    if (vista === 'registro') prepararAuditoria();
    if (vista === 'radios') { estado.radiosAdmin = (await api('/api/radios')).radios; desenharRadios(); }
    if (vista === 'configuracoes') { estado.configuracao = await api('/api/empresa/configuracao'); desenharConfig(); }
    if (vista === 'comparativo') { desenharComparativo(); estado.painel = await api('/api/painel'); desenharComparativo(); }
    if (vista === 'usuarios') { const j = await api('/api/usuarios'); estado.usuarios = j.usuarios; estado.perfis = j.perfis; desenharUsuarios(); }
    if (vista === 'empresas') { estado.empresas = (await api('/api/empresas')).empresas; desenharEmpresas(); }
    if (vista === 'registro') { estado.registro = (await api('/api/registro')).registro; desenharRegistro(); }
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
  if (estado.tela === 'app') desenharConcessao();   // no dashboard, o mapa pinta os municípios pelos avisos
  document.documentElement.dataset.farol = 'pronto';
}

// ---- Funil do novo aviso ----
function irParaPasso(n) {
  if (n === 2 && passoMaximo() < 2) return avisar(validarArquivo(estado.arquivo), true);
  if (n > passoMaximo()) return;
  estado.passo = n;
  if (n < 3) avisar('');
  desenharAbas();
  $('vista-aviso').scrollIntoView({ block: 'start' });
}

// começa outro desligamento: tira o resultado do envio anterior da tela e do mapa (o histórico já o guardou)
function novoAviso() {
  descartarNovo();
  estado.arquivo = null;
  $('arquivo').value = '';
  estado.passo = 1;
  avisar('');
  desenharAbas();
}

// tira da tela e do mapa a conferência ou o aviso novo (a planilha escolhida fica)
function descartarNovo() {
  Object.assign(estado, { conferi: false, justificativa: '', abas: [], aba: '' });
  $('aba').replaceChildren();
  if (estado.origem === 'novo') {
    Object.assign(estado, { resultado: null, origem: null, avisos: {}, finais: {}, formulario: null });
    for (const a of [...Object.values(estado.audios), ...Object.values(estado.audiosHoje)]) URL.revokeObjectURL(a.url);
    estado.audios = {}; estado.audiosHoje = {};
    for (const id of ['resumo', 'municipios', 'problemasCorpo']) $(id).replaceChildren();
    desenharComparativo();
    camadaComunidades?.remove(); camadaComunidades = null;
    desenharConferencia(); desenharUcs(); desenharConcessao(); desenharBase(); desenharNomes();
  }
}

// outra planilha escolhida: a conferência da anterior não vale mais
function escolherPlanilha(arquivo) {
  if (temResultadoNovo() && !gerado()) descartarNovo();
  else Object.assign(estado, { abas: [], aba: '' });
  estado.arquivo = arquivo || null;
  avisar('');
}

async function mostrarResultado(resultado, origem, formulario) {
  estado.resultado = resultado; estado.origem = origem; estado.formulario = formulario;
  Object.assign(estado, { envios: [], sugestao: {}, escolha: {} });
  estado.avisos = Object.fromEntries(resultado.municipios.map(m => [m.codigo_ibge, textoAviso(m)]));
  estado.finais = Object.fromEntries(resultado.municipios.filter(m => m.texto_final).map(m => [m.codigo_ibge, m.texto_final]));
  desenharResultado(); desenharConcessao();
  await Promise.all(resultado.municipios.filter(m => !estado.territorios[m.codigo_ibge]).map(async m => {
    estado.territorios[m.codigo_ibge] = await api(`/api/municipios/${m.codigo_ibge}/comunidades`);
  }));
  desenharComunidades(); desenharUcs(); desenharBase(); desenharNomes();
  await carregarEnvios();
}

// 1º passo (Conferir): a planilha vai ao servidor, que devolve a conferência e o pacote assinado (15 min).
// Nada vai para o histórico ainda.
async function enviar(evento) {
  evento.preventDefault();
  const form = { arquivo: estado.arquivo, data: $('data').value, inicio: $('inicio').value, fim: $('fim').value, idioma: $('idioma').value,
    tipo: $('tipo').value, tipoOutro: $('tipoOutro').value };
  const problema = validarFormulario(form);
  if (problema) {
    if (validarArquivo(form.arquivo)) { estado.passo = 1; desenharAbas(); }
    return avisar(problema, true);
  }
  if (temResultadoNovo() && !gerado()) descartarNovo();
  estado.enviando = true;
  avisar('Lendo a planilha, conferindo as linhas e localizando as comunidades…');
  const horario = `${horaTexto(form.inicio)} às ${horaTexto(form.fim)}`;
  const dados = new FormData();
  dados.append('arquivo', form.arquivo);
  dados.append('data', dataTexto(form.data));
  dados.append('horario', horario);
  dados.append('idioma', form.idioma);
  dados.append('tipo', form.tipo);
  if (form.tipo === 'outro') dados.append('tipo_outro', form.tipoOutro);
  if (estado.aba) dados.append('aba', estado.aba);
  try {
    const j = await api('/api/planilha', { method: 'POST', body: dados });
    const c = j.conferencia;
    avisar(c.vital_bloqueio.length ? 'Conferência pronta, com bloqueio: há equipamento vital com problema (veja em vermelho).'
      : `Conferência pronta: ${fmt(c.numeros.clientes)} cliente(s), ${fmt(c.numeros.comunidades)} comunidade(s). Confira os números e o mapa para gerar o aviso.`,
      !!c.vital_bloqueio.length || !j.municipios.length);
    estado.passo = 3;
    await mostrarResultado(j, 'novo', { data: dataTexto(form.data), dataLonga: dataLonga(form.data), horario, idioma: form.idioma,
      tipo: form.tipo, tipoOutro: form.tipo === 'outro' ? form.tipoOutro : null });
    document.documentElement.dataset.farol = 'conferencia';
  } catch (e) {
    if (e.status === 409 && e.dados.abas) {   // mais de uma aba serve: a pessoa escolhe e confere de novo
      estado.abas = e.dados.abas;
      estado.aba = estado.abas[0];
      $('aba').replaceChildren(...estado.abas.map(a => no('option', { value: a, texto: a })));
      avisar(`${e.message} Escolha a aba e clique em "Conferir a planilha" de novo.`, true);
    } else if (e.status !== 401) avisar(e.message, true);
  } finally {
    estado.enviando = false;
    desenharEstado();
  }
}

// 2º passo (Gerar aviso): o pacote da conferência, a caixa "Conferi" e a justificativa; o servidor confere tudo de novo
async function gerarAviso() {
  const problema = problemaParaGerar();
  if (problema) return avisar(problema, true);
  const f = estado.formulario;
  estado.enviando = true;
  desenharFunil();
  avisar('Gerando o aviso…');
  try {
    const j = await api('/api/avisos', { method: 'POST', json: { pacote: estado.resultado.pacote, data: f.data, horario: f.horario, idioma: f.idioma,
      conferi: estado.conferi, justificativa: estado.justificativa.trim() || null, tipo: f.tipo, tipo_outro: f.tipoOutro } });
    const n = j.municipios.length;
    avisar(n ? `Pronto: ${n} município(s), ${fmt(j.municipios.reduce((s, m) => s + m.comunidades.length, 0))} comunidade(s). Guardado no histórico (aviso nº ${j.id}).`
      : `Nenhuma UC na área de concessão. Guardado no histórico (aviso nº ${j.id}).`, !n);
    estado.passo = 4;
    await mostrarResultado(j, 'novo', f);
    document.documentElement.dataset.farol = 'resultado';
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    estado.enviando = false;
    desenharFunil();
  }
}

// conferência: caixa "Conferi", justificativa e os downloads (relatório sem UC; JSON com as UCs, registrado na auditoria)
function editarConferencia(evento) {
  const alvo = evento.target;
  if (alvo.id === 'conferi') estado.conferi = alvo.checked;
  else if (alvo.id === 'justificativa') {
    estado.justificativa = alvo.value;
    $('contaJustificativa').textContent = `${alvo.value.length} de ${MAX_JUSTIFICATIVA} caracteres`;
  } else return;
  desenharFunil();
}

async function acaoConferencia(evento) {
  const b = evento.target.closest('button[data-conf]');
  if (!b) return;
  b.disabled = true;
  try {
    if (b.dataset.conf === 'relatorio') {
      await baixarDaApi('/api/planilha/relatorio', { headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pacote: estado.resultado.pacote }) }, 'farol-relatorio-planilha.csv');
      avisar('Relatório da planilha baixado (só linha, situação e motivo; sem UC).');
    } else {
      if (!estado.arquivo) return avisar('Escolha a planilha de novo para baixar o JSON.', true);
      if (!confirm('O JSON tem os números de UC (dado pessoal). O download fica registrado na auditoria com o seu nome. Baixar?')) return;
      const dados = new FormData();
      dados.append('arquivo', estado.arquivo);
      if (estado.aba) dados.append('aba', estado.aba);
      await baixarDaApi('/api/planilha/json', { body: dados }, 'farol-planilha.json');
      avisar('JSON da planilha baixado (registrado na auditoria).');
    }
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    b.disabled = false;
  }
}

// guarda no histórico o texto que vai para a rádio (ao baixar o PDF ou copiar)
async function guardarFinal(codigo) {
  if (!pode('gerar_aviso') || !estado.resultado.id || estado.finais[codigo] === estado.avisos[codigo]) return;
  try {
    await api(`/api/historico/${estado.resultado.id}/municipios/${codigo}/texto`, { method: 'PUT', json: { texto: estado.avisos[codigo] } });
    estado.finais[codigo] = estado.avisos[codigo];
    desenharFinal(codigo);
  } catch (e) {
    avisar(`Não foi possível guardar o texto final: ${e.message}`, true);
  }
}

async function gerarAudio(codigo, m) {
  if (audioAtual(codigo)) return audioAtual(codigo);
  avisar(`Gerando o áudio de ${m.nome}…`);
  const texto = estado.avisos[codigo];
  const r = await fetch('/api/audio', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto, idioma: estado.formulario.idioma, municipio: m.nome }) });
  if (r.status === 401) { sessaoAcabou(); throw new ErroApi(401, 'A sessão acabou.'); }
  if (!r.ok) throw new ErroApi(r.status, (await r.json().catch(() => ({}))).detail || 'Não foi possível gerar o áudio.');
  if (estado.audios[codigo]) URL.revokeObjectURL(estado.audios[codigo].url);
  estado.audios[codigo] = { texto, url: URL.createObjectURL(await r.blob()), segundos: Number(r.headers.get('X-Duracao-Segundos')) || 0 };
  avisar(`Áudio de ${m.nome} pronto.`);
  desenharTocador(codigo);
  return estado.audios[codigo];
}

// áudio do comparativo: o do Farol é o mesmo de "Avisos"; o de hoje pede o limite maior (é bem mais longo)
async function audioHoje(codigo, m) {
  if (estado.audiosHoje[codigo]) return estado.audiosHoje[codigo];
  avisar(`Gerando o áudio do aviso de hoje de ${m.nome} (é longo: pode levar um tempo)…`);
  const r = await fetch('/api/audio', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto: m.hoje.texto, idioma: 'pt-BR', municipio: m.nome, comparativo: true }) });
  if (r.status === 401) { sessaoAcabou(); throw new ErroApi(401, 'A sessão acabou.'); }
  if (!r.ok) throw new ErroApi(r.status, (await r.json().catch(() => ({}))).detail || 'Não foi possível gerar o áudio.');
  estado.audiosHoje[codigo] = { url: URL.createObjectURL(await r.blob()), segundos: Number(r.headers.get('X-Duracao-Segundos')) || 0 };
  avisar(`Áudio do aviso de hoje de ${m.nome} pronto.`);
  return estado.audiosHoje[codigo];
}

async function acaoComparativo(evento) {
  const b = evento.target.closest('button[data-comp]');
  if (!b) return;
  const codigo = b.dataset.codigo, m = estado.resultado.municipios.find(x => x.codigo_ibge === codigo);
  b.disabled = true;
  try {
    const a = b.dataset.comp === 'hoje' ? await audioHoje(codigo, m) : await gerarAudio(codigo, m);
    const lugar = $(`tocador-${b.dataset.comp}-${codigo}`);
    lugar.replaceChildren(no('audio', { controls: true, src: a.url, preload: 'auto', 'aria-label': `Áudio do aviso ${b.dataset.comp === 'hoje' ? 'de hoje' : 'do Farol'}` }),
      no('span', { classe: 'ajuda', texto: `${tempoNoAr(Math.round(a.segundos))} de áudio (voz sintetizada)` }));
    lugar.querySelector('audio').play().catch(() => {});
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    b.disabled = false;
  }
}

async function acao(evento) {
  const b = evento.target.closest('button[data-acao]');
  if (!b) return;
  const codigo = b.dataset.codigo, m = estado.resultado.municipios.find(x => x.codigo_ibge === codigo);
  if (b.dataset.acao === 'copiar') {
    try { await navigator.clipboard.writeText(estado.avisos[codigo]); avisar(`Aviso de ${m.nome} copiado.`); }
    catch (e) { avisar('Não foi possível copiar; selecione o texto e use Ctrl+C.', true); }
    await guardarFinal(codigo);
  } else if (b.dataset.acao === 'restaurar') {
    estado.avisos[codigo] = textoGerado(m);
    $(`aviso-${codigo}`).value = textoGerado(m);
    desenharTempo(codigo);
  } else if (b.dataset.acao === 'ouvir' || b.dataset.acao === 'audio') {
    b.disabled = true;
    try {
      const a = await gerarAudio(codigo, m);
      if (b.dataset.acao === 'ouvir') {
        $(`tocador-${codigo}`).querySelector('audio')?.play().catch(() => {});
      } else {
        const link = no('a', { href: a.url, download: `farol-aviso-${m.nome}-${estado.formulario.data.replace('/', '-')}.mp3` });
        document.body.append(link); link.click(); link.remove();
        await guardarFinal(codigo);
      }
    } catch (e) {
      if (e.status !== 401) avisar(e.message, true);
    } finally {
      b.disabled = false;
    }
  } else if (b.dataset.acao === 'pdf') {   // o PDF é gerado no servidor, com o texto editado, e fica na auditoria
    b.disabled = true;
    try {
      await baixarDaApi(`/api/historico/${estado.resultado.id}/municipios/${codigo}/pdf`, { headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texto: estado.avisos[codigo] }) }, `farol-aviso-${codigo}.pdf`);
      await guardarFinal(codigo);
      avisar(`PDF de ${m.nome} baixado (registrado na auditoria).`);
    } catch (e) {
      if (e.status !== 401) avisar(e.message, true);
    } finally {
      b.disabled = false;
    }
  }
}

function editar(evento) {
  const a = evento.target;
  if (a.tagName !== 'TEXTAREA' || !a.dataset.codigo || a.readOnly) return;
  estado.avisos[a.dataset.codigo] = a.value;
  desenharTempo(a.dataset.codigo);
}

async function abrirHistorico(evento) {
  const b = evento.target.closest('button[data-historico]');
  if (!b) return;
  try {
    const a = await api(`/api/historico/${b.dataset.historico}`);
    await mostrarResultado(doHistorico(a), 'historico', { data: a.data, dataLonga: a.data, horario: a.horario, idioma: a.idioma });
    desenharHistorico();
    $('resultado').scrollIntoView({ block: 'start' });
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
}

// aviso do histórico: mudar a data ou cancelar; o servidor confere a permissão e registra o antes e o depois
async function acaoAviso(evento) {
  const b = evento.target.closest('button[data-aviso]');
  if (!b) return;
  const r = estado.resultado;
  try {
    let a, feito;
    if (b.dataset.aviso === 'data') {
      const d = $('novaData').value, i = $('novoInicio').value, f = $('novoFim').value;
      if (!d || !i || !f || f <= i) return avisar('Informe a nova data e um horário de fim depois do início.', true);
      a = await api(`/api/historico/${r.id}/data`, { method: 'POST', json: { data: dataTexto(d), horario: `${horaTexto(i)} às ${horaTexto(f)}` } });
      feito = `Data do aviso nº ${r.id} mudada para ${a.data}, ${a.horario} (registrado na auditoria).`;
    } else {
      const motivo = $('motivoCancelar').value.trim();
      if (motivo.length < 3) return avisar('Escreva o motivo do cancelamento.', true);
      if (!confirm(`Cancelar o desligamento do aviso nº ${r.id}? O aviso fica no histórico, marcado como cancelado.`)) return;
      a = await api(`/api/historico/${r.id}/cancelar`, { method: 'POST', json: { motivo } });
      feito = `Desligamento do aviso nº ${r.id} cancelado (registrado na auditoria).`;
    }
    // a lista e o aviso aberto primeiro; a mensagem de pronto só depois de tudo redesenhado
    estado.historico = estado.historico.map(x => x.id === a.id ? a : x);
    desenharHistorico();
    await mostrarResultado(doHistorico(a), 'historico', { data: a.data, dataLonga: a.data, horario: a.horario, idioma: a.idioma });
    avisar(feito);
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
}

async function carregarRelatorio(evento) {
  evento?.preventDefault();
  try {
    estado.relatorio = await api(`/api/relatorios/mensal?${consulta(filtrosRelatorio())}`);
    desenharRelatorio();
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
}

async function exportarRelatorio(evento) {
  const b = evento.target.closest('button[data-rel]');
  if (!b) return;
  b.disabled = true;
  try {
    await baixarDaApi(`/api/relatorios/mensal.${b.dataset.rel}?${consulta(filtrosRelatorio())}`, { method: 'GET' }, `farol-relatorio.${b.dataset.rel}`);
    avisar(`Relatório baixado em ${b.dataset.rel.toUpperCase()}, com o seu nome e o código de verificação (registrado na auditoria).`);
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  } finally {
    b.disabled = false;
  }
}

// auditoria: o relatório da empresa (Admin da empresa) ou o geral de acessos (Admin do Farol)
function prepararAuditoria() {
  const geral = pode('auditoria_geral');
  $('formAuditoria').hidden = !geral && !pode('relatorio_auditoria');
  $('tituloRelAuditoria').textContent = geral ? 'Auditoria geral de acessos (todas as empresas)' : 'Relatório de auditoria da empresa';
  $('audEmpresaRotulo').hidden = !geral;
  $('audAcessos').checked = geral;
  if (!$('audMes').options.length) $('audMes').replaceChildren(...ultimosMeses().map(([v, t]) => no('option', { value: v, texto: t })));
}

async function exportarAuditoria(evento) {
  const b = evento.target.closest('button[data-aud]');
  if (!b) return;
  const f = { mes: $('audMes').value, so_acessos: String($('audAcessos').checked) };
  if ($('audPessoa').value.trim()) f.pessoa = $('audPessoa').value.trim();
  if (pode('auditoria_geral') && $('audEmpresa').value.trim()) f.empresa = $('audEmpresa').value.trim().toUpperCase();
  b.disabled = true;
  try {
    await baixarDaApi(`/api/relatorios/${pode('auditoria_geral') ? 'acessos' : 'auditoria'}.${b.dataset.aud}?${consulta(f)}`, { method: 'GET' },
      `farol-auditoria.${b.dataset.aud}`);
    mensagemEm('estadoAuditoria', `Relatório baixado em ${b.dataset.aud.toUpperCase()}, com o seu nome e o código de verificação.`);
  } catch (e) {
    if (e.status !== 401) mensagemEm('estadoAuditoria', e.message, true);
  } finally {
    b.disabled = false;
  }
}

async function baixarComprovante(evento) {
  if (evento.target.id !== 'baixarComprovante') return;
  try {
    await baixarDaApi(`/api/historico/${estado.resultado.id}/comprovante.pdf`, { method: 'GET' }, 'farol-comprovante.pdf');
    avisar(`Comprovante do aviso nº ${estado.resultado.id} baixado (registrado na auditoria).`);
  } catch (e) {
    if (e.status !== 401) avisar(e.message, true);
  }
}

async function verificarAuditoria() {
  try {
    const v = await api('/api/auditoria/verificar');
    mensagemEm('estadoAuditoria', v.ok ? `Auditoria íntegra${v.linhas ? `: ${fmt(v.linhas)} linhas conferidas` : ''}. Nenhuma linha foi alterada nem apagada.`
      : `A auditoria NÃO confere${v.quebra_id ? ` a partir da linha ${v.quebra_id} (${v.motivo})` : `: ${v.motivo}`}.`, !v.ok);
    estado.registro = (await api('/api/registro')).registro;
    desenharRegistro();
  } catch (e) {
    if (e.status !== 401) mensagemEm('estadoAuditoria', e.message, true);
  }
}

const selecionados = sel => [...sel.selectedOptions].map(o => o.value);

async function cadastrarUsuario(evento) {
  evento.preventDefault();
  try {
    const j = await api('/api/usuarios', { method: 'POST', json: { nome: $('novoNome').value, email: $('novoEmail').value, perfil: $('novoPerfil').value,
      municipios: selecionados($('novoMunicipios')) } });
    for (const o of $('novoMunicipios').options) o.selected = false;
    $('novoNome').value = ''; $('novoEmail').value = '';
    mensagemEm('estadoUsuario', `${j.usuario.nome} cadastrado.`);
    mostrarSenhaTemporaria(`Senha temporária de ${j.usuario.nome} (${j.usuario.email}):`, j.senha_temporaria);
    await irPara('usuarios');
  } catch (e) {
    if (e.status !== 401) mensagemEm('estadoUsuario', e.message, true);
  }
}

async function acaoUsuario(evento) {
  const b = evento.target.closest('button[data-acao-usuario]');
  if (!b) return;
  const linha = b.closest('[data-usuario]'), id = linha.dataset.usuario, x = estado.usuarios.find(u => String(u.id) === id);
  try {
    if (b.dataset.acaoUsuario === 'salvar') {
      const campo = n => linha.querySelector(`[data-campo="${n}"]`).value;
      await api(`/api/usuarios/${id}`, { method: 'PATCH', json: { perfil: campo('perfil'), status: campo('status'),
        municipios: selecionados(linha.querySelector('[data-campo="municipios"]')) } });
      mensagemEm('estadoUsuario', `${x.nome}: alterações salvas.`);
    } else {
      const j = await api(`/api/usuarios/${id}/senha-temporaria`, { method: 'POST' });
      mostrarSenhaTemporaria(`Nova senha temporária de ${x.nome} (${x.email}). As sessões abertas dele foram encerradas.`, j.senha_temporaria);
    }
    await irPara('usuarios');
  } catch (e) {
    if (e.status !== 401) mensagemEm('estadoUsuario', e.message, true);
  }
}

async function cadastrarEmpresa(evento) {
  evento.preventDefault();
  const v = id => $(id).value;
  try {
    const j = await api('/api/empresas', { method: 'POST', json: { nome: v('empNome'), sigla: v('empSigla'), dominio: v('empDominio'),
      admin_nome: v('empAdminNome'), admin_email: v('empAdminEmail'), cnpj: v('empCnpj') || null } });
    for (const id of ['empNome', 'empCnpj', 'empSigla', 'empDominio', 'empAdminNome', 'empAdminEmail']) $(id).value = '';
    mensagemEm('estadoEmpresa', `${j.empresa.nome} cadastrada.`);
    mostrarSenhaTemporaria(`Senha temporária do primeiro admin de ${j.empresa.nome}:`, j.senha_temporaria);
    await irPara('empresas');
  } catch (e) {
    if (e.status !== 401) mensagemEm('estadoEmpresa', e.message, true);
  }
}

async function acaoEmpresa(evento) {
  const b = evento.target.closest('button[data-empresa-acao]');
  if (!b) return;
  const id = b.closest('[data-empresa]').dataset.empresa, e = estado.empresas.find(x => String(x.id) === id), status = b.dataset.empresaAcao;
  if (status === 'suspensa' && !confirm(`Suspender ${e.nome}? Ninguém da empresa entra até ela ser reativada.`)) return;
  try {
    await api(`/api/empresas/${id}`, { method: 'PATCH', json: { status } });
    await irPara('empresas');
    mensagemEm('estadoEmpresa', `${e.nome} ${status === 'suspensa' ? 'suspensa' : 'reativada'} (registrado na auditoria).`);
  } catch (x) {
    if (x.status !== 401) mensagemEm('estadoEmpresa', x.message, true);
  }
}

// ---- Rádios (Admin da empresa) ----
function limparFormRadio() {
  estado.radioEditando = null;
  estado.alcanceComunidades = [];
  for (const id of ['radNome', 'radEmail', 'radWhats', 'radValor']) $(id).value = '';
  $('radCobranca').value = 'fechado';
  $('radAtiva').checked = true;
  for (const o of $('radMunicipios').options) o.selected = false;
  $('radMunCom').value = '';
}

async function salvarRadio(evento) {
  evento.preventDefault();
  const r = estado.radioEditando;
  const dados = { nome: $('radNome').value, email: $('radEmail').value || null, whatsapp: $('radWhats').value || null,
    valor_padrao: $('radValor').value || null, cobranca: $('radCobranca').value, ativa: $('radAtiva').checked,
    alcance: { municipios: selecionados($('radMunicipios')), comunidades: estado.alcanceComunidades } };
  try {
    const j = await api(r ? `/api/radios/${r.id}` : '/api/radios', { method: r ? 'PATCH' : 'POST', json: dados });
    limparFormRadio();
    await irPara('radios');
    mensagemEm('estadoRadio', `${j.radio.nome} ${r ? 'alterada' : 'cadastrada'} (registrado na auditoria).`);
  } catch (e) {
    if (e.status !== 401) mensagemEm('estadoRadio', e.message, true);
  }
}

async function editarRadio(evento) {
  const b = evento.target.closest('button[data-radio-acao]');
  if (!b) return;
  const r = estado.radiosAdmin.find(x => String(x.id) === b.closest('[data-radio]').dataset.radio);
  estado.radioEditando = r;
  estado.alcanceComunidades = r.alcance.comunidades.map(c => ({ ...c }));
  $('radNome').value = r.nome; $('radEmail').value = r.email || ''; $('radWhats').value = r.whatsapp || '';
  $('radValor').value = r.valor_padrao ? Number(r.valor_padrao).toFixed(2).replace('.', ',') : '';
  $('radCobranca').value = r.cobranca; $('radAtiva').checked = r.ativa;
  for (const o of $('radMunicipios').options) o.selected = r.alcance.municipios.includes(o.value);
  desenharRadios();
  $('formRadio').scrollIntoView({ block: 'start' });
}

async function escolherMunicipioRadio() {
  const cod = $('radMunCom').value;
  if (cod && !estado.territorios[cod]) {
    try { estado.territorios[cod] = await api(`/api/municipios/${cod}/comunidades`); } catch (e) { if (e.status !== 401) mensagemEm('estadoRadio', e.message, true); }
  }
  desenharComunidadesRadio();
}

function marcarComunidade(evento) {
  const c = evento.target.dataset?.comunidade;
  if (!c) return;
  const [municipio, nome, distrito] = c.split('|');
  estado.alcanceComunidades = estado.alcanceComunidades.filter(x => `${x.municipio}|${x.nome}|${x.distrito}` !== c);
  if (evento.target.checked) estado.alcanceComunidades.push({ municipio, nome, distrito });
  $('radResumo').textContent = resumoComunidades();   // só o resumo: a lista fica (e o foco também)
}

// ---- Configurações da empresa ----
async function salvarConfig(evento) {
  evento.preventDefault();
  try {
    estado.configuracao = await api('/api/empresa/configuracao', { method: 'PUT', json: { modelo_mensagem: $('cfgModelo').value, nome_mensagem: $('cfgNome').value,
      telefone: $('cfgTelefone').value, limite_rejeicao: Number($('cfgLimite').value) / 100, epsg_utm: Number($('cfgFuso').value),
      antecedencia_dias: Number($('cfgAntecedencia').value) } });
    desenharConfig();
    mensagemEm('estadoConfig', 'Configurações salvas (registrado na auditoria). Valem para os próximos avisos.');
  } catch (e) {
    if (e.status !== 401) mensagemEm('estadoConfig', e.message, true);
  }
}

// ---- Tema, ajuda e dicas ----
function alternarTema() {
  const novo = temaAtual() === 'escuro' ? 'claro' : 'escuro';
  document.documentElement.dataset.tema = novo;
  try { localStorage.setItem('farol.tema', novo); } catch (e) { /* sem armazenamento: só nesta visita */ }
  desenharTema();
  trocarFundoDoMapa();
}

function abrirAjuda() {
  desenharAjuda();
  $('caixaAjuda').hidden = false;
  $('ajudaFechar').focus();
}

function mostrarDica(evento) {
  const b = evento.target.closest('button[data-dica]'), caixa = $('dica');
  if (!b) return;
  if (!caixa.hidden && caixa.dataset.de === b.dataset.dica) { caixa.hidden = true; return; }
  caixa.textContent = DICAS[b.dataset.dica];
  caixa.dataset.de = b.dataset.dica;
  caixa.hidden = false;
  const r = b.getBoundingClientRect(), largura = Math.min(320, innerWidth - 24);
  Object.assign(caixa.style, { width: `${largura}px`, left: `${Math.max(12, Math.min(r.left + scrollX - largura / 2, innerWidth - largura - 12))}px`,
    top: `${r.bottom + scrollY + 6}px` });
}

function arrastar() {
  const z = $('zona');
  for (const ev of ['dragenter', 'dragover']) z.addEventListener(ev, e => { e.preventDefault(); z.classList.add('arrastando'); });
  for (const ev of ['dragleave', 'drop']) z.addEventListener(ev, () => z.classList.remove('arrastando'));
  z.addEventListener('drop', e => { e.preventDefault(); escolherPlanilha(e.dataTransfer.files[0]); });
}

async function abrir() {
  try { const t = localStorage.getItem('farol.tema'); if (t === 'claro' || t === 'escuro') document.documentElement.dataset.tema = t; } catch (e) { /* sem armazenamento */ }
  desenharTema();
  // data padrão: daqui a 4 dias (acima das 72 h legais)
  const d = new Date(Date.now() + 4 * 864e5);
  $('data').value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  $('formEntrar').addEventListener('submit', entrar);
  $('formSenha').addEventListener('submit', trocarSenha);
  $('sair').addEventListener('click', sair);
  $('abas').addEventListener('click', e => { const b = e.target.closest('button[data-vista]'); if (b) irPara(b.dataset.vista); });
  $('arquivo').addEventListener('change', e => escolherPlanilha(e.target.files[0]));
  $('aba').addEventListener('change', e => { estado.aba = e.target.value; });
  $('tipo').addEventListener('change', e => { for (const id of ['tipoOutroRotulo', 'tipoOutroAjuda']) $(id).hidden = e.target.value !== 'outro'; });
  $('acoesAviso').addEventListener('click', acaoAviso);
  $('verificarAuditoria').addEventListener('click', verificarAuditoria);
  $('formRelatorio').addEventListener('submit', carregarRelatorio);
  $('formRelatorio').addEventListener('click', exportarRelatorio);
  $('formAuditoria').addEventListener('click', exportarAuditoria);
  $('solicitado').addEventListener('click', baixarComprovante);
  $('conferencia').addEventListener('change', editarConferencia);
  $('conferencia').addEventListener('input', editarConferencia);
  $('conferencia').addEventListener('click', acaoConferencia);
  $('form').addEventListener('submit', enviar);
  $('botaoUcs').addEventListener('click', () => { estado.verUcs = !estado.verUcs; desenharUcs(); });
  $('botaoRede').addEventListener('click', alternarRede);
  $('botaoLegenda').addEventListener('click', alternarLegenda);
  try { estado.legendaMinimizada = localStorage.getItem('farol.legenda') === 'minimizada'; } catch (e) { /* sem armazenamento */ }
  desenharLegenda();
  $('funil').addEventListener('click', e => { const b = e.target.closest('button[data-passo]'); if (b && !b.disabled) irParaPasso(Number(b.dataset.passo)); });
  $('avancar').addEventListener('click', () => irParaPasso(2));
  $('voltar').addEventListener('click', () => irParaPasso(1));
  $('voltarResultado').addEventListener('click', () => irParaPasso(estado.passo - 1));
  $('avancarResultado').addEventListener('click', () => gerado() ? irParaPasso(4) : gerarAviso());
  $('novoAviso').addEventListener('click', novoAviso);
  $('verComparativo').addEventListener('click', () => irPara('comparativo'));
  $('comparativo').addEventListener('click', acaoComparativo);
  $('buscaHistorico').addEventListener('input', e => { estado.filtroHistorico.busca = e.target.value; desenharHistorico(); });
  $('periodoHistorico').addEventListener('change', e => { estado.filtroHistorico.periodo = e.target.value; desenharHistorico(); });
  $('municipios').addEventListener('click', acao);
  $('municipios').addEventListener('click', acaoEnvio);
  $('municipios').addEventListener('input', editarEnvio);
  $('municipios').addEventListener('change', editarEnvio);
  $('municipios').addEventListener('input', editar);
  $('listaHistorico').addEventListener('click', abrirHistorico);
  $('formUsuario').addEventListener('submit', cadastrarUsuario);
  $('listaEmpresas').addEventListener('click', acaoEmpresa);
  $('formRadio').addEventListener('submit', salvarRadio);
  $('radCancelar').addEventListener('click', () => { limparFormRadio(); desenharRadios(); });
  $('listaRadios').addEventListener('click', editarRadio);
  $('radMunCom').addEventListener('change', escolherMunicipioRadio);
  $('radComunidades').addEventListener('change', marcarComunidade);
  $('formConfig').addEventListener('submit', salvarConfig);
  $('formConfig').addEventListener('input', desenharPreviaConfig);
  $('cfgPadrao').addEventListener('click', () => { $('cfgModelo').value = estado.configuracao.modelo_padrao; desenharPreviaConfig(); });
  $('subabas').addEventListener('click', e => { const b = e.target.closest('button[data-vista]'); if (b) irPara(b.dataset.vista); });
  $('botaoTema').addEventListener('click', alternarTema);
  $('botaoAjuda').addEventListener('click', abrirAjuda);
  $('ajudaFechar').addEventListener('click', () => { $('caixaAjuda').hidden = true; $('botaoAjuda').focus(); });
  document.addEventListener('click', mostrarDica);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { $('dica').hidden = true; if (!$('caixaAjuda').hidden) { $('caixaAjuda').hidden = true; $('botaoAjuda').focus(); } } });
  $('listaUsuarios').addEventListener('click', acaoUsuario);
  $('formEmpresa').addEventListener('submit', cadastrarEmpresa);
  $('caixaFechar').addEventListener('click', () => { $('caixaSenha').hidden = true; $('caixaSenhaValor').textContent = ''; });
  $('caixaCopiar').addEventListener('click', () => navigator.clipboard.writeText($('caixaSenhaValor').textContent).catch(() => {}));
  arrastar();
  try {
    const j = await api('/api/eu');
    await aposEntrar(j.usuario);
  } catch (e) {
    estado.tela = 'entrar';
    desenharTela();
  }
  desenharEstado();
  if (estado.tela !== 'app') document.documentElement.dataset.farol = 'pronto';
}

document.addEventListener('DOMContentLoaded', abrir);
