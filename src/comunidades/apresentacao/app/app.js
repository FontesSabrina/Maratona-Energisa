'use strict';
// Farol: tela do aviso de desligamento. Envia a planilha para a API, mostra os municípios e as
// comunidades no mapa e gera o roteiro (PDF) para a rádio. Só fala com a própria API.
// Organização: Model (estado e regras puras), View (desenha a partir do estado) e Controller (eventos).

// ======================= Model: estado da tela e regras puras (não toca no HTML) =======================
const estado = {
  config: null,            // /api/config
  concessao: null,         // contornos dos municípios (GeoJSON)
  arquivo: null,           // o File escolhido (fica só no navegador até o envio)
  enviando: false,
  mensagem: '', erro: false,
  resultado: null,         // resposta de /api/avisos
  avisos: {},              // codigo_ibge -> texto do aviso (editável)
  territorios: {},         // codigo_ibge -> GeoJSON das comunidades
  formulario: null,        // data, horário e idioma do último envio (para o roteiro)
};

const fmt = n => Number(n).toLocaleString('pt-BR');

// "08:00" -> "8h", "08:30" -> "8h30" (como o aviso fala)
function horaTexto(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  return `${h}h${m ? String(m).padStart(2, '0') : ''}`;
}
// "2026-11-12" -> "12/11"
function dataTexto(iso) {
  const [, m, d] = iso.split('-');
  return `${d}/${m}`;
}
function dataLonga(iso) {
  const [a, m, d] = iso.split('-');
  return `${d}/${m}/${a}`;
}

function validarFormulario({ arquivo, data, inicio, fim }) {
  if (!arquivo) return 'Escolha a planilha das UCs afetadas.';
  if (!/\.(csv|xlsx)$/i.test(arquivo.name)) return 'A planilha tem de ser .csv ou .xlsx.';
  if (estado.config && arquivo.size > estado.config.limites.bytes) return 'A planilha passa de 10 MB.';
  if (!data) return 'Informe a data do desligamento.';
  if (!inicio || !fim) return 'Informe o horário de início e de fim.';
  if (fim <= inicio) return 'O fim tem de ser depois do início.';
  return null;
}

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

function grupos(m) {
  const g = { inteira: [], parte: [], vizinha: [] };
  for (const c of m.comunidades) g[situacao(c)].push(c);
  return g;
}

async function codigoVerificacao(texto) {
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(texto));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
}

// ======================= View: desenha a partir do estado (não muda o estado) =======================
const $ = id => document.getElementById(id);

// todo texto vindo da API ou da planilha entra como texto, nunca como HTML
function no(tag, props = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'classe') e.className = v;
    else if (k === 'texto') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  e.append(...filhos.filter(f => f !== null && f !== undefined));
  return e;
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
}

function desenharResumo() {
  const r = estado.resultado, p = r.planilha;
  const ucs = r.municipios.reduce((s, m) => s + m.ucs, 0);
  const dl = no('dl', { classe: 'numeros' },
    ...[['linhas lidas', p.linhas], ['UCs localizadas', ucs], ['com problema', p.total_problemas], ['fora da concessão', r.fora_da_concessao.ucs]]
      .map(([t, v]) => no('div', {}, no('dt', { texto: t }), no('dd', { texto: fmt(v) }))));
  const filhos = [dl, no('p', { classe: 'prazo', texto: `Antecedência mínima do aviso: ${r.prazo.antecedencia_minima} (${r.prazo.norma}).` })];
  if (!r.municipios.length) filhos.push(no('p', { classe: 'alerta', texto: 'Nenhuma UC da planilha caiu na área de concessão. Confira as coordenadas.' }));
  if (r.fora_da_concessao.ucs) {
    const linhas = r.fora_da_concessao.linhas.join(', ');
    filhos.push(no('p', { classe: 'alerta', texto: `${fmt(r.fora_da_concessao.ucs)} UC(s) fora da área de concessão, sem aviso: linha(s) ${linhas}${r.fora_da_concessao.ucs > r.fora_da_concessao.linhas.length ? '…' : ''}.` }));
  }
  filhos.push(no('p', { classe: 'ajuda', texto: r.aviso_ficticio }));
  $('resumo').replaceChildren(...filhos);
}

function tempoTexto(texto) {
  return `${fmt(palavras(texto))} palavras · cerca de ${fmt(segundos(texto))} s no ar`;
}

function desenharMunicipios() {
  const cartoes = estado.resultado.municipios.map(m => {
    const g = grupos(m), texto = estado.avisos[m.codigo_ibge];
    const area = no('textarea', { id: `aviso-${m.codigo_ibge}`, 'aria-label': `Aviso de ${m.nome}`, 'data-codigo': m.codigo_ibge });
    area.value = texto;
    const vital = m.equipamento_vital;
    const listas = no('div', { classe: 'listas' },
      ...['inteira', 'parte', 'vizinha'].filter(s => g[s].length).map(s => no('p', {},
        no('span', { classe: `etiqueta ${s}`, texto: { inteira: 'Inteiras', parte: 'Em parte', vizinha: 'Vizinhas' }[s] }),
        g[s].map(c => `${homonimo(c) ? nomeComDistrito(c, m) : c.nome}: ${fmt(c.afetadas)}`).join(', '))),
      no('p', { classe: 'ajuda', texto: `Equipamento vital: ${fmt(vital.sim)} sim, ${fmt(vital.nao)} não` + (vital.a_confirmar ? `, ${fmt(vital.a_confirmar)} a confirmar` : '') + '. Depois do nome, UCs afetadas da comunidade.' }));
    return no('article', { classe: 'cartao municipio', 'data-codigo': m.codigo_ibge },
      no('div', { classe: 'mun-cab' }, no('h3', { texto: `${m.nome}/${m.uf}` }), no('span', { classe: 'meta', texto: `${fmt(m.ucs)} UCs · ${fmt(m.comunidades.length)} comunidades` })),
      no('label', { for: area.id, texto: 'Aviso para a rádio (pode editar)' }), area,
      no('p', { classe: 'tempo', id: `tempo-${m.codigo_ibge}`, texto: tempoTexto(texto) }),
      no('div', { classe: 'acoes' },
        no('button', { type: 'button', classe: 'prim', 'data-acao': 'pdf', 'data-codigo': m.codigo_ibge, texto: 'Baixar PDF para a rádio' }),
        no('button', { type: 'button', 'data-acao': 'copiar', 'data-codigo': m.codigo_ibge, texto: 'Copiar texto' }),
        no('button', { type: 'button', 'data-acao': 'restaurar', 'data-codigo': m.codigo_ibge, texto: 'Desfazer edição' })),
      listas);
  });
  $('municipios').replaceChildren(...cartoes);
}

function desenharTempo(codigo) {
  $(`tempo-${codigo}`).textContent = tempoTexto(estado.avisos[codigo]);
}

function desenharProblemas() {
  const p = estado.resultado.planilha;
  $('problemas').hidden = !p.total_problemas;
  if (!p.total_problemas) return;
  $('problemasTitulo').textContent = `${fmt(p.total_problemas)} linha(s) com problema`;
  const motivos = no('ul', {}, ...Object.entries(p.problemas_por_motivo).map(([m, n]) => no('li', { texto: `${m}: ${fmt(n)}` })));
  const tabela = no('table', {}, no('thead', {}, no('tr', {}, no('th', { texto: 'Linha' }), no('th', { texto: 'Problema' }))),
    no('tbody', {}, ...p.problemas.map(x => no('tr', {}, no('td', { texto: String(x.linha) }), no('td', { texto: x.motivo })))));
  const corpo = [motivos, tabela];
  if (p.total_problemas > p.problemas.length) corpo.push(no('p', { classe: 'ajuda', texto: `Mostrando as primeiras ${fmt(p.problemas.length)}.` }));
  $('problemasCorpo').replaceChildren(...corpo);
}

function desenharResultado() {
  $('resultado').hidden = !estado.resultado;
  if (!estado.resultado) return;
  desenharResumo(); desenharMunicipios(); desenharProblemas();
}

// ---- Mapa ----
const escuro = () => matchMedia('(prefers-color-scheme: dark)').matches;
const COR = { ambar: '#F5B83D', ambarForte: '#B07800', cinza: '#93A1AF', info: '#1663C7' };
let mapa, camadaConcessao, camadaComunidades;

function iniciarMapa() {
  mapa = L.map('mapa', { zoomControl: true, attributionControl: false, minZoom: 5, maxZoom: 16 });
  L.control.attribution({ prefix: 'Concessão e comunidades: IBGE · Leaflet' }).addTo(mapa);
  L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${escuro() ? 'Dark' : 'Light'}_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
    { attribution: 'Fundo &copy; Esri', maxZoom: 16, noWrap: true }).addTo(mapa);
  mapa.setView([-21.0, -42.6], 8);
}

function desenharConcessao() {
  if (!estado.concessao) return;
  const afetados = new Set((estado.resultado?.municipios || []).map(m => m.codigo_ibge));
  camadaConcessao?.remove();
  camadaConcessao = L.geoJSON(estado.concessao, {
    style: f => afetados.has(f.properties.codigo_ibge)
      ? { color: COR.info, weight: 2.5, fillOpacity: 0 }
      : { color: COR.cinza, weight: .8, fillColor: COR.cinza, fillOpacity: .05 },
    onEachFeature: (f, l) => l.bindTooltip(() => no('span', { texto: `${f.properties.nome}/${f.properties.uf}` }), { sticky: true }),
  }).addTo(mapa);
  camadaConcessao.bringToBack();
}

function desenharComunidades() {
  camadaComunidades?.remove();
  camadaComunidades = null;
  const r = estado.resultado;
  if (!r) return;
  const feicoes = [];
  for (const m of r.municipios) {
    const terr = estado.territorios[m.codigo_ibge];
    if (!terr) continue;
    const porNome = new Map(m.comunidades.map(c => [c.nome, c]));
    for (const f of terr.features) {
      const c = porNome.get(f.properties.nome);
      if (c) feicoes.push({ ...f, properties: { ...f.properties, m, c } });
    }
  }
  if (!feicoes.length) return;
  camadaComunidades = L.geoJSON({ type: 'FeatureCollection', features: feicoes }, {
    style: f => ({
      inteira: { color: COR.ambarForte, weight: 1.5, fillColor: COR.ambar, fillOpacity: .55 },
      parte: { color: COR.ambarForte, weight: 1.5, dashArray: '5 4', fillColor: COR.ambar, fillOpacity: .22 },
      vizinha: { color: COR.cinza, weight: 1, fillColor: COR.cinza, fillOpacity: .25 },
    })[situacao(f.properties.c)],
    onEachFeature: (f, l) => {
      const { c, m } = f.properties;
      l.bindTooltip(() => no('span', {}, no('strong', { texto: nomeComDistrito(c, m) }), ` · ${ROTULO[situacao(c)]}`, no('br'),
        `${fmt(c.afetadas)} UCs afetadas · ${fmt(c.total)} endereços na comunidade`), { sticky: true });
    },
  }).addTo(mapa);
  mapa.fitBounds(camadaComunidades.getBounds(), { padding: [30, 30], maxZoom: 13 });
}

// ---- Roteiro (PDF) de um município ----
async function desenharRoteiro(codigo) {
  const m = estado.resultado.municipios.find(x => x.codigo_ibge === codigo);
  const f = estado.formulario, texto = estado.avisos[codigo], g = grupos(m);
  const codigoV = (await codigoVerificacao(texto)).slice(0, 16);
  const lista = (titulo, cs) => cs.length ? [no('h2', { texto: titulo }), no('ul', {}, ...cs.map(c => no('li', { texto: nomeComDistrito(c, m) })))] : [];
  const agora = new Date();
  $('roteiro').replaceChildren(
    no('div', { classe: 'rt-marca' }, no('img', { src: '/assets/marca/farol.svg', alt: '' }),
      no('div', {}, no('p', { classe: 'rt-nome', texto: 'Farol' }), no('p', { classe: 'rt-slogan', texto: 'Cada comunidade avisada pelo nome' }))),
    no('h1', { texto: 'Roteiro para a rádio' }),
    no('p', { classe: 'rt-meta', texto: `${m.nome}/${m.uf} · desligamento programado em ${dataLonga(f.data)}, das ${horaTexto(f.inicio)} às ${horaTexto(f.fim)} · ${estado.config.distribuidora}` }),
    no('h2', { texto: 'Texto para leitura' }),
    no('p', { classe: 'rt-aviso', texto }),
    no('p', { classe: 'rt-tempo', texto: tempoTexto(texto) }),
    ...lista('Comunidades inteiras', g.inteira), ...lista('Parte da comunidade', g.parte),
    ...(g.vizinha.length ? [no('h2', { texto: 'Localidades vizinhas (citadas em conjunto)' }), no('p', { texto: g.vizinha.map(c => nomeComDistrito(c, m)).join(', ') })] : []),
    no('h2', { texto: 'Prazo' }),
    no('p', { texto: `Antecedência mínima: ${estado.resultado.prazo.antecedencia_minima} (${estado.resultado.prazo.norma}).` }),
    no('p', { texto: `Unidades com equipamento vital: ${fmt(m.equipamento_vital.sim)}` + (m.equipamento_vital.a_confirmar ? ` (${fmt(m.equipamento_vital.a_confirmar)} a confirmar)` : '') + '.' }),
    no('div', { classe: 'rt-rodape' },
      no('p', { texto: `Gerado em ${agora.toLocaleDateString('pt-BR')} às ${agora.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}. Código de verificação do texto (SHA-256): ` },
        no('span', { classe: 'rt-codigo', texto: codigoV })),
      no('p', { texto: estado.resultado.aviso_ficticio })));
}

// ======================= Controller: eventos e chamadas à API (atualiza o estado e redesenha) =======================
function avisar(mensagem, erro = false) {
  estado.mensagem = mensagem; estado.erro = erro;
  desenharEstado();
}

function escolherArquivo(f) {
  estado.arquivo = f || null;
  avisar('');
}

async function obter(url) {
  const r = await fetch(url, { credentials: 'same-origin' });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

async function enviar(evento) {
  evento.preventDefault();
  const form = { arquivo: estado.arquivo, data: $('data').value, inicio: $('inicio').value, fim: $('fim').value, idioma: $('idioma').value };
  const problema = validarFormulario(form);
  if (problema) return avisar(problema, true);
  estado.enviando = true;
  avisar('Lendo a planilha e localizando as comunidades…');
  const dados = new FormData();
  dados.append('arquivo', form.arquivo);
  dados.append('data', dataTexto(form.data));
  dados.append('horario', `${horaTexto(form.inicio)} às ${horaTexto(form.fim)}`);
  dados.append('idioma', form.idioma);
  try {
    const r = await fetch('/api/avisos', { method: 'POST', body: dados, credentials: 'same-origin' });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Não foi possível processar a planilha.');
    estado.resultado = j;
    estado.formulario = form;
    estado.avisos = Object.fromEntries(j.municipios.map(m => [m.codigo_ibge, m.aviso]));
    const n = j.municipios.length;
    avisar(n ? `Pronto: ${n} município(s), ${fmt(j.municipios.reduce((s, m) => s + m.comunidades.length, 0))} comunidade(s).` : 'Nenhuma UC na área de concessão.', !n);
    desenharResultado(); desenharConcessao();
    await Promise.all(j.municipios.filter(m => !estado.territorios[m.codigo_ibge]).map(async m => {
      estado.territorios[m.codigo_ibge] = await obter(`/api/municipios/${m.codigo_ibge}/comunidades`);
    }));
    desenharComunidades();
    document.documentElement.dataset.farol = 'resultado';
  } catch (e) {
    avisar(e.message || 'Erro de conexão com o servidor.', true);
  } finally {
    estado.enviando = false;
    desenharEstado();
  }
}

async function acao(evento) {
  const b = evento.target.closest('button[data-acao]');
  if (!b) return;
  const codigo = b.dataset.codigo, m = estado.resultado.municipios.find(x => x.codigo_ibge === codigo);
  if (b.dataset.acao === 'copiar') {
    try { await navigator.clipboard.writeText(estado.avisos[codigo]); avisar(`Aviso de ${m.nome} copiado.`); }
    catch (e) { avisar('Não foi possível copiar; selecione o texto e use Ctrl+C.', true); }
  } else if (b.dataset.acao === 'restaurar') {
    estado.avisos[codigo] = m.aviso;
    $(`aviso-${codigo}`).value = m.aviso;
    desenharTempo(codigo);
  } else if (b.dataset.acao === 'pdf') {
    await desenharRoteiro(codigo);
    const titulo = document.title;
    document.title = `Farol - aviso ${m.nome} ${dataTexto(estado.formulario.data).replace('/', '-')}`;  // nome sugerido do PDF
    window.print();
    document.title = titulo;
  }
}

function editar(evento) {
  const a = evento.target;
  if (a.tagName !== 'TEXTAREA' || !a.dataset.codigo) return;
  estado.avisos[a.dataset.codigo] = a.value;
  desenharTempo(a.dataset.codigo);
}

function arrastar() {
  const z = $('zona');
  for (const ev of ['dragenter', 'dragover']) z.addEventListener(ev, e => { e.preventDefault(); z.classList.add('arrastando'); });
  for (const ev of ['dragleave', 'drop']) z.addEventListener(ev, () => z.classList.remove('arrastando'));
  z.addEventListener('drop', e => { e.preventDefault(); escolherArquivo(e.dataTransfer.files[0]); });
}

async function abrir() {
  // data padrão: daqui a 4 dias (acima das 72 h legais)
  const d = new Date(Date.now() + 4 * 864e5);
  $('data').value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  $('arquivo').addEventListener('change', e => escolherArquivo(e.target.files[0]));
  $('form').addEventListener('submit', enviar);
  $('municipios').addEventListener('click', acao);
  $('municipios').addEventListener('input', editar);
  arrastar();
  iniciarMapa();
  try {
    [estado.config, estado.concessao] = await Promise.all([obter('/api/config'), obter('/api/concessao')]);
    $('faixa').textContent = estado.config.aviso_ficticio;
    $('idioma').replaceChildren(...Object.entries(estado.config.idiomas).map(([k, nome]) => no('option', { value: k, texto: nome })));
    $('idioma').value = estado.config.idioma_padrao;
    desenharConcessao();
    mapa.fitBounds(camadaConcessao.getBounds(), { padding: [20, 20] });
  } catch (e) {
    avisar('Não foi possível falar com o servidor do Farol.', true);
  }
  desenharEstado();
  document.documentElement.dataset.farol = 'pronto';
}

document.addEventListener('DOMContentLoaded', abrir);
