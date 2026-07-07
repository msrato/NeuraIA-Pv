/**
 * cerebro.js — N.E.U.R.A. v2.8.0
 * Lógica do Cérebro Neural Dinâmico com correção do botão sincronizar.
 */

'use strict';

// API já foi declarada em interface.js (carregado antes deste arquivo no
// interface.html) — reutiliza a mesma constante global em vez de redeclarar.
// Redeclarar 'const' em outro <script> clássico do mesmo documento quebrava
// o parse do arquivo INTEIRO com "Identifier 'API' has already been declared",
// e por isso syncWithDatabase() nunca era definida.

/* ══════════════════════════════════════════════════════
   ESTADO DO GRAFO
   ══════════════════════════════════════════════════════ */
let network       = null;
let nodesDataset  = null;
let edgesDataset  = null;

/* ══════════════════════════════════════════════════════
   MAPA ANATÔMICO DOS LOBOS (Desenho Real do Cérebro)
   ══════════════════════════════════════════════════════ */
const LOBOS = {
  identidade:     { x: -100, y: -100 },   // Lobo Frontal
  projeto:        { x:  100, y: -120 },   // Lobo Parietal
  aprendizado:    { x:  180, y:  -30 },   // Lobo Occipital
  objetivo:       { x: -120, y:   20 },   // Lobo Temporal
  sentimento:     { x:    0, y:  -30 },   // Sistema Límbico (Centro)
  geral:          { x:   50, y:  120 },   // Tronco / Cerebelo
  conquista:      { x:   90, y:   60 },   // Tronco superior
  relacionamento: { x: -180, y:  -50 },   // Polo frontal estendido
};

const MOCK_NODES = [
  { id:"1", texto:"Mestre: Mateus Sandes Rato é o criador do ecossistema Neura.", categoria:"identidade",  cor:"#34D399" },
  { id:"2", texto:"Alter ego: Tony Stark (brilhantismo) e DIO (domínio absoluto).", categoria:"identidade",  cor:"#34D399" },
  { id:"3", texto:"Projeto NeuraField S/A — empresa de IA de nível mundial.",         categoria:"projeto",     cor:"#00BFFF" },
  { id:"4", texto:"Nexo Infinito (NI) integra todas as redes e bancos de dados.",    categoria:"projeto",     cor:"#00BFFF" },
  { id:"5", texto:"Estudando Python, Flask e MongoDB Atlas para o backend.",          categoria:"aprendizado", cor:"#A78BFA" },
  { id:"6", texto:"Construindo interface holográfica ciano com Canvas/Vis.js.",       categoria:"aprendizado", cor:"#A78BFA" },
  { id:"7", texto:"Meta: voz offline com Kokoro-ONNX sem depender de nuvem.",        categoria:"objetivo",    cor:"#F59E0B" },
  { id:"8", texto:"Sentimento: orgulho ao ver a síntese de voz rodar local.",        categoria:"sentimento",  cor:"#F472B6" },
];

const MOCK_EDGES = [
  { from:"1", to:"2" },
  { from:"1", to:"3" },
  { from:"3", to:"4" },
  { from:"5", to:"6" },
  { from:"1", to:"5" },
  { from:"3", to:"7" },
  { from:"1", to:"8" },
];

function _posComJitter(categoria) {
  const base   = LOBOS[categoria] ?? LOBOS.geral;
  const jitter = 60;
  return {
    x: base.x + (Math.random() - 0.5) * jitter,
    y: base.y + (Math.random() - 0.5) * jitter,
  };
}

function _formatarNos(nos) {
  return nos.map(n => {
    const pos   = _posComJitter(n.categoria);
    const label = n.texto.length > 25
      ? n.texto.slice(0, 22) + '...'
      : n.texto;

    return {
      id:    n.id,
      label,
      title: n.texto,
      x:     pos.x,
      y:     pos.y,
      color: {
        background: '#010409',
        border:     n.cor ?? '#6B7280',
        highlight:  { background: '#081e2b', border: '#00f0ff' },
        hover:      { background: '#0c2838', border: '#00f0ff' },
      },
      font:        { color: '#a5f3fc', face: 'Share Tech Mono', size: 10 },
      shape:       'dot',
      size:        13,
      borderWidth: 2,
      shadow:      { enabled: true, color: n.cor ?? '#6B7280', size: 6, x: 0, y: 0 },
      _data: n,
    };
  });
}

function _formatarArestas(edges, nosFormatados) {
  const corPorId = {};
  nosFormatados.forEach(n => { corPorId[n.id] = n.color.border; });

  return edges.map((e, i) => ({
    id:    `e${i}`,
    from:  e.from,
    to:    e.to,
    color: { color: corPorId[e.from] ?? '#0b2545', opacity: 0.5, highlight: '#00f0ff' },
    width: 1,
    smooth: { type: 'curvedCW', roundness: 0.15 },
  }));
}

function _gerarArestasPorCategoria(nos) {
  const edges = [];
  const grupos = {};
  nos.forEach(n => {
    if (!grupos[n.categoria]) grupos[n.categoria] = [];
    grupos[n.categoria].push(n.id);
  });

  Object.values(grupos).forEach(ids => {
    for (let i = 0; i < ids.length - 1; i++) {
      edges.push({ from: ids[i], to: ids[i + 1] });
    }
    if (ids.length > 2) {
      edges.push({ from: ids[ids.length - 1], to: ids[0] });
    }
  });

  return edges;
}

function initNetwork(nos, edges) {
  const container = document.getElementById('network-container');
  if (!container) return;

  if (network) {
    network.destroy();
    network = null;
  }

  nodesDataset = new vis.DataSet();
  edgesDataset = new vis.DataSet();

  const nosFormatados    = _formatarNos(nos);
  const arestasFormatadas = _formatarArestas(edges, nosFormatados);

  nodesDataset.add(nosFormatados);
  edgesDataset.add(arestasFormatadas);

  const options = {
    physics: {
      enabled: true,
      solver:  'repulsion',
      repulsion: {
        nodeDistance:    90,
        centralGravity:  0.08,
        springLength:    100,
        springConstant:  0.04,
        damping:         0.08,
      },
      stabilization: { iterations: 80, fit: true },
    },
    interaction: {
      hover:       true,
      zoomView:    true,
      dragView:    true,
    }
  };

  network = new vis.Network(
    container,
    { nodes: nodesDataset, edges: edgesDataset },
    options,
  );

  network.on('click', params => {
    if (params.nodes.length > 0) {
      const visNode = nodesDataset.get(params.nodes[0]);
      if (visNode?._data) _abrirInspetor(visNode._data);
    }
  });

  network.once('stabilizationIterationsDone', () => {
    network.setOptions({ physics: { enabled: false } });
  });
}

function _abrirInspetor(data) {
  const idDisplay = document.getElementById('node-id-display');
  const content   = document.getElementById('inspector-content');
  if (!idDisplay || !content) return;

  idDisplay.textContent = `NEURON_ID: ${String(data.id).slice(0, 14)}`;

  content.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:12px;">
      <div>
        <span style="font-size:8px;color:var(--muted);display:block;letter-spacing:2px;margin-bottom:4px;">LOBO / REDE ATIVA</span>
        <span style="font-size:10px;font-weight:700;padding:2px 8px;border:1px solid ${data.cor};color:${data.cor};letter-spacing:2px;">
          ${(data.categoria ?? 'GERAL').toUpperCase()}
        </span>
      </div>
      <div>
        <span style="font-size:8px;color:var(--muted);display:block;letter-spacing:2px;margin-bottom:4px;">MEMÓRIA ARMAZENADA</span>
        <p style="background:rgba(1,4,9,0.8);border:1px solid rgba(0,240,255,0.08);padding:8px 10px;color:var(--text);font-family:var(--mono);font-size:10.5px;line-height:1.65;">
          "${data.texto}"
        </p>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:8px;color:var(--muted);padding-top:4px;border-top:1px solid rgba(0,240,255,0.06);">
        <span>ESTADO: ATIVO</span>
        <span style="color:var(--accent);">DESCRIPTOGRAFADO ✓</span>
      </div>
    </div>
  `;
}

async function syncWithDatabase() {
  const btn      = document.getElementById('sync-btn');
  const icon     = document.getElementById('sync-icon');
  const btnLabel = btn?.querySelector('span');

  if (icon)     icon.classList.remove('hidden');
  if (btnLabel) btnLabel.textContent = 'SINCRONIZANDO...';
  if (btn)      btn.disabled = true;

  try {
    const res = await fetch(`${API}/api/memorias_hud`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const result = await res.json();

    if (result.status === 'ok' && Array.isArray(result.nos) && result.nos.length > 0) {
      const edges = _gerarArestasPorCategoria(result.nos);
      initNetwork(result.nos, edges);
      console.log(`[CEREBRO] ${result.total} memórias reais carregadas com sucesso.`);
    } else {
      throw new Error('Sem memórias gravadas ou formato inválido');
    }

  } catch (err) {
    console.warn('[CEREBRO] Servidor ou Banco offline. Carregando dados MOCK anatômicos.', err.message);
    initNetwork(MOCK_NODES, MOCK_EDGES);
  } finally {
    if (icon)     icon.classList.add('hidden');
    if (btnLabel) btnLabel.textContent = 'SINCRONIZAR MEMÓRIA';
    if (btn)      btn.disabled = false;
  }
}

function _iniciarRelogio() {
  const h = document.getElementById('clock-h');
  const m = document.getElementById('clock-m');
  const s = document.getElementById('clock-s');

  function _tick() {
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    if (h) h.textContent = pad(now.getHours());
    if (m) m.textContent = pad(now.getMinutes());
    if (s) s.textContent = pad(now.getSeconds());
  }

  _tick();
  setInterval(_tick, 1000);
}

async function _atualizarRecursos() {
  const cpuEl  = document.getElementById('cpu-load');
  const ramEl  = document.getElementById('ram-load');

  try {
    const res = await fetch(`${API}/api/status`, {
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) throw new Error();
    const data = await res.json();
    if (cpuEl) cpuEl.textContent = `${data.cpu_percent ?? '--'}%`;
    if (ramEl) ramEl.textContent = `${data.ram_usado_gb ?? '--'} / ${data.ram_total_gb ?? '--'} GB`;
  } catch {
    const cpu = Math.floor(Math.random() * 12) + 6;
    const ram = (5.8 + Math.random() * 0.4).toFixed(1);
    if (cpuEl) cpuEl.textContent = `${cpu}%`;
    if (ramEl) ramEl.textContent = `${ram} / 16 GB`;
  }
}

function _iniciarMonitorRecursos() {
  _atualizarRecursos();
  setInterval(_atualizarRecursos, 5000);
}

async function atualizarStatusHeader() {
  try {
    const res  = await fetch(`${API}/api/status`, { signal: AbortSignal.timeout(2000) });
    if (!res.ok) throw new Error();
    const data = await res.json();

    const vozEl    = document.getElementById('hdr-voz');
    const modeloEl = document.getElementById('hdr-modelo');
    const mongoEl  = document.getElementById('mongo-status');

    if (vozEl    && data.voz_modo)    vozEl.textContent    = data.voz_modo;
    if (modeloEl && data.modelo)      modeloEl.textContent = data.modelo;
    if (mongoEl  && data.mongo_status) mongoEl.textContent = data.mongo_status;
  } catch {
    // Flask offline — mantém valores padrão
  }
}

window.addEventListener('DOMContentLoaded', () => {
  _iniciarRelogio();
  _iniciarMonitorRecursos();

  initNetwork(MOCK_NODES, MOCK_EDGES);
  syncWithDatabase();

  atualizarStatusHeader();
  setInterval(atualizarStatusHeader, 10_000);
});