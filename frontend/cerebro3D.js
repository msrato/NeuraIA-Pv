/**
 * cerebro3d.js — N.E.U.R.A. v2.9.0
 * Responsabilidade única: renderizar a esfera neural 3D de partículas.
 *
 * Cada partícula = 1 memória do MongoDB (via /api/memorias_hud).
 * A cor de cada partícula vem da categoria da memória (lobo anatômico).
 * O número de partículas = número real de memórias salvas.
 * Enquanto offline usa MOCK_NODES para manter a HUD funcional.
 *
 * Depende de:
 *   - Three.js r128 via CDN
 *   - API global de interface.js
 *
 * Consome IDs HTML:
 *   - network-container   (canvas 3D)
 *   - node-id-display     (inspetor: ID)
 *   - inspector-content   (inspetor: conteúdo)
 *   - sync-btn, sync-icon (botão de sync)
 *
 * Para trocar o visual: edite CEREBRO_CONFIG abaixo.
 * Para adicionar categorias: adicione em COR_CATEGORIA.
 * Para substituir a fonte de dados: edite apenas syncWithDatabase().
 */

'use strict';

/* ══════════════════════════════════════════════════════
   CONFIGURAÇÃO
   ══════════════════════════════════════════════════════ */
const CEREBRO_CONFIG = {
  RAIO:              1.6,     // raio da esfera de memórias
  CAMERA_Z:          4.2,     // distância da câmera
  PARTICULA_RAIO:    0.028,   // tamanho de cada neurônio
  ROTACAO_AUTO:      0.0008,  // rotação automática (rad/frame)
  GLOW_OPACIDADE:    0.18,    // opacidade do halo ao redor da partícula
  HOVER_ESCALA:      1.8,     // escala ao passar o mouse
  SELECIONADO_ESCALA: 2.4,    // escala ao clicar
  PULSE_SPEED:       0.025,   // velocidade do pulso das conexões
};

/* Cores por categoria (lobo anatômico) */
const COR_CATEGORIA = {
  identidade:     '#34D399',   // Lobo Frontal — verde
  projeto:        '#00BFFF',   // Lobo Parietal — azul
  aprendizado:    '#A78BFA',   // Lobo Occipital — roxo
  objetivo:       '#F59E0B',   // Lobo Temporal — âmbar
  sentimento:     '#F472B6',   // Sist. Límbico — rosa
  conquista:      '#FB923C',   // Tronco superior — laranja
  relacionamento: '#60A5FA',   // Polo frontal — azul claro
  geral:          '#6B7280',   // Tronco — cinza
};

/* Posições anatômicas dos lobos (esféricas → cartesianas depois) */
const LOBOS_ESFERICOS = {
  // [phi (polar), theta (azimutal)] em radianos
  identidade:     [0.9,  2.5],    // Lobo Frontal — frente superior esquerda
  projeto:        [0.8,  0.8],    // Lobo Parietal — topo centro
  aprendizado:    [1.0, -0.6],    // Lobo Occipital — trás
  objetivo:       [1.3,  2.2],    // Lobo Temporal — lateral inferior
  sentimento:     [1.0,  1.5],    // Sist. Límbico — centro
  conquista:      [1.4,  1.0],    // Tronco superior
  relacionamento: [1.2,  3.0],    // Polo frontal
  geral:          [1.6,  1.5],    // Tronco inferior
};

/* ══════════════════════════════════════════════════════
   DADOS MOCK
   ══════════════════════════════════════════════════════ */
const MOCK_NODES = [
  { id:"1",  texto:"Mestre: Mateus Sandes Rato é o criador do ecossistema Neura.", categoria:"identidade"  },
  { id:"2",  texto:"Alter ego: Tony Stark (brilhantismo) e DIO (domínio absoluto).", categoria:"identidade"  },
  { id:"3",  texto:"Projeto NeuraField S/A — empresa de IA de nível mundial.",       categoria:"projeto"     },
  { id:"4",  texto:"Nexo Infinito (NI) integra todas as redes e bancos de dados.",  categoria:"projeto"     },
  { id:"5",  texto:"Estudando Python, Flask e MongoDB Atlas para o backend.",        categoria:"aprendizado" },
  { id:"6",  texto:"Construindo interface holográfica ciano com Canvas/Three.js.",   categoria:"aprendizado" },
  { id:"7",  texto:"Meta: voz offline com Kokoro-ONNX sem depender de nuvem.",      categoria:"objetivo"    },
  { id:"8",  texto:"Sentimento: orgulho ao ver a síntese de voz rodar local.",      categoria:"sentimento"  },
  { id:"9",  texto:"Sistema de 3 modos de voz: MUDO, AUTO, COMMAND.",               categoria:"projeto"     },
  { id:"10", texto:"Aprendendo tool calling e loops de agentes com Groq.",           categoria:"aprendizado" },
  { id:"11", texto:"HUD holográfica cyberpunk estilo J.A.R.V.I.S.",                  categoria:"projeto"     },
  { id:"12", texto:"Plano de domínio mundial via NeuraField S/A.",                   categoria:"objetivo"    },
];

/* ══════════════════════════════════════════════════════
   ESTADO
   ══════════════════════════════════════════════════════ */
let _scene       = null;
let _camera      = null;
let _renderer    = null;
let _group       = null;  // grupo rotacionável com todas as partículas
let _raf         = null;
let _memorias    = [];    // dados originais de cada nó (texto, categoria, id)
let _meshes      = [];    // THREE.Mesh de cada partícula (índice = memória)
let _conexoes    = [];    // THREE.Line de sinapses
let _selecionado = -1;    // índice da memória selecionada (-1 = nenhuma)
let _hovered     = -1;    // índice sob o cursor
let _pulseT      = 0;
let _rotY        = 0;
let _isDragging  = false;
let _lastX       = 0;
let _lastY       = 0;
let _rotX        = 0;
let _camYaw      = 0.85;
let _camPitch    = 0.35;
let _camRadius   = CEREBRO_CONFIG.CAMERA_Z;

const _raycaster = new THREE.Raycaster();
const _mouse     = new THREE.Vector2();

function _criarFundoCerebral() {
  const fundo = new THREE.Group();

  const geometry = new THREE.BufferGeometry();
  const count = 1200;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const i3 = i * 3;
    const radius = 8 + Math.random() * 18;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    positions[i3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[i3 + 1] = radius * Math.cos(phi);
    positions[i3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  const estrellas = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({
      color: '#7dd3fc',
      size: 0.04,
      transparent: true,
      opacity: 0.8,
      depthWrite: false,
    })
  );
  fundo.add(estrellas);

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(2.8, 5.8, 128),
    new THREE.MeshBasicMaterial({
      color: '#0ea5e9',
      transparent: true,
      opacity: 0.12,
      side: THREE.DoubleSide,
    })
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = -2.1;
  fundo.add(ring);

  const glow = new THREE.Mesh(
    new THREE.CircleGeometry(1.7, 64),
    new THREE.MeshBasicMaterial({
      color: '#22d3ee',
      transparent: true,
      opacity: 0.06,
      side: THREE.DoubleSide,
    })
  );
  glow.rotation.x = -Math.PI / 2;
  glow.position.y = -1.8;
  fundo.add(glow);

  return fundo;
}

/* ══════════════════════════════════════════════════════
   DISTRIBUIÇÃO FIBONACCI NA ESFERA
   Distribui N pontos uniformemente na superfície — garante
   que não ficam todos amontoados no mesmo lugar.
   ══════════════════════════════════════════════════════ */
function _fibonacciEsfera(n, raio) {
  const pts      = [];
  const golden   = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y      = 1 - (i / (n - 1)) * 2;
    const r      = Math.sqrt(1 - y * y);
    const theta  = golden * i;
    pts.push(new THREE.Vector3(
      Math.cos(theta) * r * raio,
      y               * raio,
      Math.sin(theta) * r * raio
    ));
  }
  return pts;
}

/* ══════════════════════════════════════════════════════
   POSIÇÃO DO LOBO COM JITTER
   Cada partícula fica próxima do centro anatômico do seu lobo,
   mas com um desvio aleatório pequeno para parecer orgânico.
   ══════════════════════════════════════════════════════ */
function _posLobo(categoria, seed) {
  const esf   = LOBOS_ESFERICOS[categoria] ?? LOBOS_ESFERICOS.geral;
  const [phi, theta] = esf;
  const R     = CEREBRO_CONFIG.RAIO;
  const j     = 0.28;  // raio do jitter em unidades de mundo

  // jitter determinístico (não muda a cada frame)
  const jx    = (((seed * 7919) % 100) / 100 - 0.5) * j;
  const jy    = (((seed * 6271) % 100) / 100 - 0.5) * j;
  const jz    = (((seed * 5003) % 100) / 100 - 0.5) * j;

  return new THREE.Vector3(
    Math.sin(phi) * Math.cos(theta) * R + jx,
    Math.cos(phi)                   * R + jy,
    Math.sin(phi) * Math.sin(theta) * R + jz
  );
}

/* ══════════════════════════════════════════════════════
   CONSTRUÇÃO DA ESFERA NEURAL
   ══════════════════════════════════════════════════════ */
function _construirEsfera(memorias) {
  // Limpa grupo anterior
  while (_group.children.length) _group.remove(_group.children[0]);
  _meshes   = [];
  _conexoes = [];
  _selecionado = -1;
  _hovered     = -1;

  const geo = new THREE.SphereGeometry(CEREBRO_CONFIG.PARTICULA_RAIO, 8, 8);

  memorias.forEach((mem, i) => {
    const cor   = new THREE.Color(COR_CATEGORIA[mem.categoria] ?? '#6B7280');
    const mat   = new THREE.MeshBasicMaterial({ color: cor, transparent: true, opacity: 0.9 });
    const mesh  = new THREE.Mesh(geo, mat);
    const pos   = _posLobo(mem.categoria, i);
    mesh.position.copy(pos);
    mesh.userData = { index: i, baseScale: 1 };
    _group.add(mesh);
    _meshes.push(mesh);
  });

  // Sinapses: conecta nós da mesma categoria
  const grupos = {};
  memorias.forEach((m, i) => {
    if (!grupos[m.categoria]) grupos[m.categoria] = [];
    grupos[m.categoria].push(i);
  });

  Object.entries(grupos).forEach(([cat, ids]) => {
    const cor = new THREE.Color(COR_CATEGORIA[cat] ?? '#6B7280');
    for (let a = 0; a < ids.length - 1; a++) {
      for (let b = a + 1; b < ids.length; b++) {
        const pa  = _meshes[ids[a]].position;
        const pb  = _meshes[ids[b]].position;
        const geo = new THREE.BufferGeometry().setFromPoints([pa, pb]);
        const mat = new THREE.LineBasicMaterial({
          color: cor, transparent: true, opacity: 0.15,
        });
        const line = new THREE.Line(geo, mat);
        line.userData.baseOpacity = 0.15;
        _group.add(line);
        _conexoes.push(line);
      }
    }
  });

  _memorias = memorias;
}

/* ══════════════════════════════════════════════════════
   INSPETOR
   ══════════════════════════════════════════════════════ */
function _abrirInspetor(idx) {
  const mem = _memorias[idx];
  if (!mem) return;

  const cor = COR_CATEGORIA[mem.categoria] ?? '#6B7280';
  const elId  = document.getElementById('node-id-display');
  const elCon = document.getElementById('inspector-content');
  if (elId)  elId.textContent = `NEURON_ID: ${String(mem.id).padStart(4,'0')}`;
  if (elCon) elCon.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:12px;">
      <div>
        <span style="font-size:8px;color:var(--muted);display:block;letter-spacing:2px;margin-bottom:4px;">LOBO / REDE ATIVA</span>
        <span style="font-size:10px;font-weight:700;padding:2px 8px;border:1px solid ${cor};color:${cor};letter-spacing:2px;">
          ${(mem.categoria ?? 'GERAL').toUpperCase()}
        </span>
      </div>
      <div>
        <span style="font-size:8px;color:var(--muted);display:block;letter-spacing:2px;margin-bottom:4px;">MEMÓRIA ARMAZENADA</span>
        <p style="background:rgba(1,4,9,0.8);border:1px solid rgba(0,240,255,0.08);padding:8px 10px;color:var(--text);font-family:var(--mono);font-size:10.5px;line-height:1.65;">"${mem.texto}"</p>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:8px;color:var(--muted);padding-top:4px;border-top:1px solid rgba(0,240,255,0.06);">
        <span>ESTADO: ATIVO</span>
        <span style="color:var(--accent);">DESCRIPTOGRAFADO ✓</span>
      </div>
    </div>`;
}

/* ══════════════════════════════════════════════════════
   LOOP DE ANIMAÇÃO
   ══════════════════════════════════════════════════════ */
function _animar() {
  _raf = requestAnimationFrame(_animar);
  _pulseT += CEREBRO_CONFIG.PULSE_SPEED;

  if (!_isDragging) {
    _rotY += CEREBRO_CONFIG.ROTACAO_AUTO;
    _camYaw += 0.002;
  }

  _group.rotation.y = _rotY;
  _group.rotation.x = _rotX;

  const cameraX = Math.sin(_camYaw) * _camRadius * Math.cos(_camPitch);
  const cameraY = Math.sin(_camPitch) * _camRadius;
  const cameraZ = Math.cos(_camYaw) * _camRadius * Math.cos(_camPitch);
  _camera.position.set(cameraX, cameraY, cameraZ);
  _camera.lookAt(0, 0, 0);

  _conexoes.forEach((line, i) => {
    const base  = line.userData.baseOpacity ?? 0.12;
    const pulse = 0.5 + 0.5 * Math.sin(_pulseT + i * 0.4);
    line.material.opacity = base + 0.1 * pulse;
  });

  _meshes.forEach((m, i) => {
    let target = 1.0;
    if (i === _selecionado) target = CEREBRO_CONFIG.SELECIONADO_ESCALA;
    else if (i === _hovered) target = CEREBRO_CONFIG.HOVER_ESCALA;
    m.scale.lerp(new THREE.Vector3(target, target, target), 0.12);
  });

  _renderer.render(_scene, _camera);
}

/* ══════════════════════════════════════════════════════
   RAYCASTING — detecta hover e clique nos neurônios
   ══════════════════════════════════════════════════════ */
function _bindInteracao(canvas) {
  canvas.addEventListener('mousemove', e => {
    const rect = canvas.getBoundingClientRect();
    _mouse.x =  ((e.clientX - rect.left)  / rect.width)  * 2 - 1;
    _mouse.y = -((e.clientY - rect.top)   / rect.height) * 2 + 1;

    _raycaster.setFromCamera(_mouse, _camera);
    const hits = _raycaster.intersectObjects(_meshes);
    _hovered   = hits.length ? hits[0].object.userData.index : -1;
    canvas.style.cursor = _hovered >= 0 ? 'pointer' : 'default';
  });

  canvas.addEventListener('click', e => {
    if (_hovered >= 0) {
      _selecionado = _hovered;
      _abrirInspetor(_selecionado);
    }
  });
}

function _bindDrag(canvas) {
  canvas.addEventListener('mousedown', e => {
    _isDragging = true;
    _lastX = e.clientX;
    _lastY = e.clientY;
  });
  window.addEventListener('mousemove', e => {
    if (!_isDragging) return;
    _rotY += (e.clientX - _lastX) * 0.006;
    _rotX += (e.clientY - _lastY) * 0.006;
    _rotX = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, _rotX));
    _camYaw += (e.clientX - _lastX) * 0.003;
    _camPitch += (e.clientY - _lastY) * 0.0025;
    _camPitch = Math.max(-1.2, Math.min(1.2, _camPitch));
    _lastX = e.clientX;
    _lastY = e.clientY;
  });
  window.addEventListener('mouseup', () => { _isDragging = false; });
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    _camRadius = Math.min(10, Math.max(3.5, _camRadius + (e.deltaY > 0 ? 0.15 : -0.15)));
  }, { passive: false });
}

function _bindResize(container) {
  new ResizeObserver(() => {
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (!_camera || !_renderer) return;
    _camera.aspect = w / h;
    _camera.updateProjectionMatrix();
    _renderer.setSize(w, h);
  }).observe(container);
}

/* ══════════════════════════════════════════════════════
   SYNC COM /api/memorias_hud
   ══════════════════════════════════════════════════════ */
async function syncWithDatabase() {
  const btn      = document.getElementById('sync-btn');
  const icon     = document.getElementById('sync-icon');
  const btnLabel = btn?.querySelector('span');

  if (icon)     icon.classList.remove('hidden');
  if (btnLabel) btnLabel.textContent = 'SINCRONIZANDO...';
  if (btn)      btn.disabled = true;

  try {
    const res = await fetch(`${API}/api/memorias_hud`, {
      headers: { 'Accept': 'application/json' },
      signal:  AbortSignal.timeout(8000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const result = await res.json();
    if (result.status === 'ok' && result.nos?.length > 0) {
      _construirEsfera(result.nos);
      console.log(`[CEREBRO3D] ${result.total} memórias reais carregadas.`);
    } else {
      throw new Error('Sem memórias ou formato inválido');
    }
  } catch (err) {
    console.warn('[CEREBRO3D] API offline — usando mock.', err.message);
    _construirEsfera(MOCK_NODES);
  } finally {
    if (icon)     icon.classList.add('hidden');
    if (btnLabel) btnLabel.textContent = 'SINCRONIZAR MEMÓRIA';
    if (btn)      btn.disabled = false;
  }
}

/* ══════════════════════════════════════════════════════
   INIT
   ══════════════════════════════════════════════════════ */
async function iniciarCerebro3D() {
  const container = document.getElementById('network-container');
  if (!container) {
    console.warn('[CEREBRO3D] #network-container não encontrado.');
    return;
  }

  const W = container.clientWidth || 400;
  const H = container.clientHeight || 400;

  _scene = new THREE.Scene();
  _scene.background = new THREE.Color('#020b14');
  _scene.fog = new THREE.Fog('#020b14', 7, 20);

  _camera = new THREE.PerspectiveCamera(50, W / H, 0.1, 100);
  _camera.position.set(0, 0.5, CEREBRO_CONFIG.CAMERA_Z);

  _renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  _renderer.setSize(W, H);
  _renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  _renderer.domElement.style.cssText =
    'position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab;';
  container.appendChild(_renderer.domElement);

  const ambient = new THREE.AmbientLight('#7dd3fc', 0.9);
  const key = new THREE.PointLight('#22d3ee', 1.5, 20, 2);
  key.position.set(2, 2, 3);
  const rim = new THREE.PointLight('#8b5cf6', 1.2, 20, 2);
  rim.position.set(-3, -2, -2);

  _scene.add(ambient, key, rim);

  const fundo = _criarFundoCerebral();
  _scene.add(fundo);

  _group = new THREE.Group();
  _scene.add(_group);

  _bindDrag(_renderer.domElement);
  _bindInteracao(_renderer.domElement);
  _bindResize(container);

  _construirEsfera(MOCK_NODES);
  _animar();
  await syncWithDatabase();
}

window.syncWithDatabase = syncWithDatabase;
window.iniciarCerebro3D = iniciarCerebro3D;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', iniciarCerebro3D);
} else {
  iniciarCerebro3D();
}
