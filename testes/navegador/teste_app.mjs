// Teste da tela do app (servida pela API em http://127.0.0.1:8000), com capturas e o PDF gerado.
// - Abre a tela, envia a planilha de teste pelo campo de arquivo e gera o aviso.
// - O aviso de cada município na tela é idêntico ao que a API devolve para a mesma planilha.
// - O mapa desenha a concessão e as comunidades afetadas; a edição do aviso atualiza o tempo no ar.
// - O PDF (roteiro para a rádio) sai com o texto editado; a página não mostra nenhuma UC nem coordenada.
// - Só requisições ao próprio servidor e aos fundos da Esri; nenhuma exceção nem violação da CSP.
// - Alvos de 44 px e nenhuma rolagem horizontal no celular; planilha inválida mostra o erro.
// Uso (com a API rodando): node testes/navegador/teste_app.mjs
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const BASE = process.env.FAROL_URL || 'http://127.0.0.1:8000';
const PLANILHA = join(RAIZ, 'saida', 'planilhas_teste', 'planilha_CF-0066.csv');
const CAP = join(RAIZ, 'saida', 'capturas_app');
mkdirSync(CAP, { recursive: true });
const resultados = [];
const conferir = (nome, ok, extra = '') => resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]);
const espera = ms => new Promise(r => setTimeout(r, ms));
async function captura(p, nome) {
  const r = await p.send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(CAP, nome), Buffer.from(r.data, 'base64'));
}
const registrarRede = lista => async pg => { await pg.send('Network.enable'); pg.on('Network.requestWillBeSent', e => lista.push(e.request.url)); };
const externa = u => !u.startsWith(BASE + '/') && !u.startsWith('https://server.arcgisonline.com/') && !u.startsWith('data:');

async function escolherArquivo(p, caminho) {
  const { root } = await p.send('DOM.getDocument', { depth: 1 });
  const { nodeId } = await p.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#arquivo' });
  await p.send('DOM.setFileInputFiles', { nodeId, files: [caminho] });
}
async function gerar(p) {
  await p.avaliar(`(document.documentElement.dataset.farol = 'enviando', $('form').requestSubmit(), 0)`);
  return p.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => {
    if (document.documentElement.dataset.farol === 'resultado' || $('estado').classList.contains('erro') || Date.now() - t0 > 60000) ok($('estado').textContent);
    else setTimeout(ver, 100); }; ver(); })`);
}
// alvos de toque: botões, campos e links fora de texto corrido, visíveis, com menos de 44 x 44 px
const PEQUENOS = `[...document.querySelectorAll('button, input:not([type=file]), select, textarea, summary, a, .arquivo')]
  .filter(e => e.offsetParent && !e.closest('p, .leaflet-control-attribution'))
  .map(e => [e.id || e.className || e.tagName, Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)])
  .filter(([, w, h]) => w < 44 || h < 44)`;

// ---------- Resposta esperada: a API, direto, com a mesma planilha ----------
const fd = new FormData();
fd.append('arquivo', new Blob([readFileSync(PLANILHA)]), 'planilha_CF-0066.csv');
// a tela manda a data como dd/mm e o horário como "8h às 14h"; o teste fixa os mesmos valores
fd.append('data', '20/11'); fd.append('horario', '8h às 14h'); fd.append('idioma', 'pt-BR');
const esperado = await (await fetch(`${BASE}/api/avisos`, { method: 'POST', body: fd })).json();
const ucs = readFileSync(PLANILHA, 'utf-8').split(/\r?\n/).slice(1).filter(Boolean).map(l => l.split(';'));

// ---------- 1. Computador ----------
{
  const rede = [];
  const p = await abrir(`${BASE}/`, { largura: 1440, altura: 900, antesDeNavegar: registrarRede(rede) });
  const ini = await p.avaliar(`({ idiomas: [...$('idioma').options].map(o => o.value).join(','), municipios: estado.concessao?.features.length,
    faixa: $('faixa').textContent, caminhos: document.querySelectorAll('#mapa path').length })`);
  conferir('abertura: 3 idiomas, 66 municípios da concessão no mapa e a faixa de dados fictícios',
    ini.idiomas === 'pt-BR,en,es' && ini.municipios === 66 && ini.caminhos >= 66 && /fictícios/.test(ini.faixa), JSON.stringify(ini));
  await captura(p, '1_abertura.png');
  await p.avaliar(`($('data').value = '2026-11-20', $('inicio').value = '08:00', $('fim').value = '14:00', 0)`);
  await escolherArquivo(p, PLANILHA);
  const nome = await p.avaliar(`$('arquivoNome').textContent`);
  conferir('arquivo escolhido aparece pelo nome', nome.startsWith('planilha_CF-0066.csv'), nome);
  const msg = await gerar(p);
  conferir('gerar aviso: pronto, sem erro', /^Pronto/.test(msg), msg);
  await espera(800);
  const tela = await p.avaliar(`({ avisos: [...document.querySelectorAll('#municipios textarea')].map(t => t.value),
    titulos: [...document.querySelectorAll('.mun-cab h3')].map(h => h.textContent),
    comunidades: camadaComunidades ? camadaComunidades.getLayers().length : 0,
    resumo: $('resumo').textContent.replace(/\\s+/g, ' ') })`);
  conferir('o aviso de cada município é idêntico ao da API', JSON.stringify(tela.avisos) === JSON.stringify(esperado.municipios.map(m => m.aviso)),
    `\n  tela: ${JSON.stringify(tela.avisos)}\n  API:  ${JSON.stringify(esperado.municipios.map(m => m.aviso))}`);
  conferir('municípios na ordem da API (Leopoldina primeiro)', JSON.stringify(tela.titulos) === JSON.stringify(esperado.municipios.map(m => `${m.nome}/${m.uf}`)), JSON.stringify(tela.titulos));
  conferir('mapa: comunidades afetadas desenhadas', tela.comunidades >= 8, String(tela.comunidades));
  conferir('resumo: 758 linhas lidas e o prazo de 5 dias úteis', /758/.test(tela.resumo) && /5 dias úteis/.test(tela.resumo), tela.resumo);
  await captura(p, '2_resultado.png');

  // edição: o tempo no ar acompanha o texto
  const cod = esperado.municipios[0].codigo_ibge;
  const antes = await p.avaliar(`$('tempo-${cod}').textContent`);
  await p.avaliar(`(() => { const a = $('aviso-${cod}'); a.value = a.value + ' Mais informações pelo telefone da distribuidora.'; a.dispatchEvent(new Event('input', { bubbles: true })); return 0; })()`);
  const depois = await p.avaliar(`$('tempo-${cod}').textContent`);
  conferir('editar o aviso atualiza as palavras e o tempo no ar', antes !== depois && /palavras/.test(depois), `${antes} -> ${depois}`);

  // PDF do roteiro com o texto editado
  await p.avaliar(`desenharRoteiro('${cod}')`);
  const roteiro = await p.avaliar(`$('roteiro').textContent`);
  conferir('roteiro: texto editado, município, data e código de verificação', roteiro.includes('Mais informações pelo telefone') && roteiro.includes('Leopoldina/MG')
    && roteiro.includes('20/11/2026') && /SHA-256\): [0-9a-f]{16}/.test(roteiro), roteiro.slice(0, 160));
  const repetido = roteiro.match(/\(([^()]+)\) \(\1\)/);
  conferir('roteiro: homônimos com o distrito uma vez só (nada de "(Tebas) (Tebas)")', !repetido, repetido?.[0]);
  await p.send('Emulation.setEmulatedMedia', { media: 'print' });
  const pdf = await p.send('Page.printToPDF', { printBackground: true, preferCSSPageSize: true });
  await p.send('Emulation.setEmulatedMedia', { media: '' });
  writeFileSync(join(CAP, 'roteiro_leopoldina.pdf'), Buffer.from(pdf.data, 'base64'));
  conferir('PDF do roteiro gerado', pdf.data.length > 10_000, `${Math.round(pdf.data.length * .75 / 1024)} KB`);

  // nenhuma UC nem coordenada da planilha na página (tela e roteiro)
  const texto = await p.avaliar(`document.documentElement.outerHTML + document.body.innerText`);
  const vazou = ucs.filter(([uc, lat, lon]) => texto.includes(uc) || texto.includes(lat) || texto.includes(lon)).slice(0, 3);
  conferir('nenhuma UC nem coordenada da planilha na página', !vazou.length, JSON.stringify(vazou));
  const csp = await p.avaliar('window.__csp');
  conferir('nenhuma exceção nem violação da CSP', !p.excecoes.length && !csp.length, JSON.stringify([p.excecoes, csp]));
  conferir('só requisições ao próprio servidor e aos fundos da Esri', rede.length && !rede.some(externa), JSON.stringify(rede.filter(externa)));
  const peq = await p.avaliar(PEQUENOS);
  conferir('alvos de toque de pelo menos 44 x 44 px (computador)', !peq.length, JSON.stringify(peq));
  await p.fechar();
}

// ---------- 2. Celular e planilha inválida ----------
{
  const p = await abrir(`${BASE}/`, { largura: 390, altura: 844 });
  await escolherArquivo(p, join(RAIZ, 'testes', 'navegador', 'exemplos', 'area_teste_sem_poligono.geojson'));
  const erroExt = await gerar(p);
  conferir('arquivo que não é .csv nem .xlsx: erro na tela, sem enviar', /\.csv ou \.xlsx/.test(erroExt), erroExt);
  await escolherArquivo(p, PLANILHA);
  const msg = await gerar(p);
  conferir('celular: gera o aviso', /^Pronto/.test(msg), msg);
  await espera(800);
  conferir('celular: sem rolagem horizontal', await p.avaliar('document.documentElement.scrollWidth <= innerWidth'));
  const peq = await p.avaliar(PEQUENOS);
  conferir('alvos de toque de pelo menos 44 x 44 px (celular)', !peq.length, JSON.stringify(peq));
  await captura(p, '3_celular.png');
  await p.fechar();
}

for (const r of resultados) console.log(r[0], r[1], r[0] !== 'OK  ' && r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK (capturas e PDF em ${CAP})`);
process.exit(falhas ? 1 : 0);
