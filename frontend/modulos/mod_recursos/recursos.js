/**
 * recursos.js — N.E.U.R.A. v2.8.6
 * Responsabilidade única: monitorar e exibir recursos de hardware e status
 * do servidor Flask em tempo real.
 *
 * Depende de: API global (declarada em interface.js, carregado antes)
 * Consome IDs HTML: cpu-load, ram-load, mongo-status, hdr-voz, hdr-modelo
 * Endpoint Flask esperado: GET /api/status
 *
 * Resposta esperada de /api/status:
 * {
 *   cpu_percent:    number,   // ex: 14
 *   ram_usado_gb:   number,   // ex: 6.2
 *   ram_total_gb:   number,   // ex: 16
 *   mongo_status:   string,   // "CONECTADO" | "OFFLINE"
 *   voz_modo:       string,   // "AUTO" | "MUDO" | "COMMAND"
 *   modelo:         string,   // "llama-3.3-70b-versatile"
 * }
 *
 * Instalar psutil no Flask para dados reais:
 *   pip install psutil
 *   No server.py:
 *     import psutil
 *     @app.route('/api/status')
 *     def api_status():
 *         return jsonify({
 *             'cpu_percent':  psutil.cpu_percent(interval=0.2),
 *             'ram_usado_gb': round(psutil.virtual_memory().used / 1e9, 1),
 *             'ram_total_gb': round(psutil.virtual_memory().total / 1e9, 1),
 *             'mongo_status': 'CONECTADO',
 *             'voz_modo':     voice_manager.mode,
 *             'modelo':       'llama-3.3-70b',
 *         })
 *
 * Para adicionar métricas novas: adicione o campo no Flask e mapeie aqui
 * em _aplicarDados(). Nenhum outro arquivo precisa mudar.
 */

'use strict';

/* ── Configuração ─────────────────────────────────────── */
const INTERVALO_RECURSOS_S = 5;    // atualiza hardware a cada 5s
const INTERVALO_STATUS_S   = 10;   // atualiza header (voz/modelo) a cada 10s
const TIMEOUT_MS           = 2500;

/* ── Elementos do DOM ─────────────────────────────────── */
const _el = id => document.getElementById(id);

/* ── Estado global do HUD ──────────────────────────────── */
window.NEURA_HUD = window.NEURA_HUD || {
  status: {
    cpu: null,
    ram: null,
    mongo: null,
    voz: null,
    visao: null,
    modelo: null,
    clima: null,
    localizacao: null,
  },
};

function _normalizarTexto(value, fallback = '--') {
  if (value === null || value === undefined || value === '') return fallback;
  return String(value);
}

/* ── Simulação offline (Flask indisponível) ───────────── */
function _simularRecursos() {
  const cpu = Math.floor(Math.random() * 14) + 6;
  const ram = (5.8 + Math.random() * 0.5).toFixed(1);

  if (_el('cpu-load')) _el('cpu-load').textContent = `${cpu}%`;
  if (_el('ram-load')) _el('ram-load').textContent = `${ram} / 16 GB`;

  if (_el('hdr-voz')) _el('hdr-voz').textContent = _normalizarTexto(window.NEURA_HUD.status.voz, 'AUTO');
  if (_el('hdr-modelo')) _el('hdr-modelo').textContent = _normalizarTexto(window.NEURA_HUD.status.modelo, 'openai/gpt-oss-120b');
  if (_el('hdr-visao')) _el('hdr-visao').textContent = _normalizarTexto(window.NEURA_HUD.status.visao, 'INATIVO');
}

/* ── Aplica dados reais vindos da API ─────────────────── */
function _aplicarDados(data = {}) {
  const cpuEl = _el('cpu-load');
  const ramEl = _el('ram-load');
  const mongoEl = _el('mongo-status');
  const vozEl = _el('hdr-voz');
  const modeloEl = _el('hdr-modelo');
  const visaoEl = _el('hdr-visao');

  if (cpuEl && data.cpu_percent != null) cpuEl.textContent = `${data.cpu_percent}%`;
  if (ramEl && data.ram_usado_gb != null) {
    const total = data.ram_total_gb != null ? data.ram_total_gb : '??';
    ramEl.textContent = `${data.ram_usado_gb} / ${total} GB`;
  }

  if (mongoEl && data.mongo_status) mongoEl.textContent = data.mongo_status;

  if (vozEl && data.voz_modo) {
    const valor = data.voz_modo.toUpperCase();
    vozEl.textContent = valor;
    window.NEURA_HUD.status.voz = valor;
  }

  if (modeloEl && data.modelo) {
    modeloEl.textContent = data.modelo;
    window.NEURA_HUD.status.modelo = data.modelo;
  }

  if (visaoEl && data.visao_modo) {
    const valor = data.visao_modo.toUpperCase();
    visaoEl.textContent = valor;
    window.NEURA_HUD.status.visao = valor;
  }

  if (data.status) window.NEURA_HUD.status.sistema = data.status;
}

/* ── Endpoints de fonte de dados do HUD ───────────────── */
const HUD_API_ENDPOINTS = {
  status: '/api/status',
  clima: '/api/clima',
  localizacao: '/api/localizacao',
  visao: '/api/visao',
  modelo: '/api/modelo',
};

async function _fetchJson(url, fallback = null, timeout = TIMEOUT_MS) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(timeout) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`[HUD] Falha em ${url}:`, err.message);
    return fallback;
  }
}

/* ── Fetch de /api/status ─────────────────────────────── */
async function _fetchStatus() {
  const data = await _fetchJson(`${API}${HUD_API_ENDPOINTS.status}`, null, TIMEOUT_MS);
  if (data) {
    _aplicarDados(data);
    return;
  }

  _simularRecursos();
}

/* ── Preparação para APIs em tempo real ────────────────── */
async function _fetchLocalizacao() {
  if (!navigator.geolocation) {
    window.NEURA_HUD.status.localizacao = 'São Paulo';
    return;
  }

  const pos = await new Promise(resolve => {
    navigator.geolocation.getCurrentPosition(
      pos => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => resolve({ lat: -23.5505, lon: -46.6333 }),
      { timeout: 5000 }
    );
  });

  window.NEURA_HUD.status.localizacao = pos;
  return pos;
}

async function _fetchClima() {
  const location = await _fetchLocalizacao();
  if (!location) return;

  const data = await _fetchJson(
    `https://api.open-meteo.com/v1/forecast?latitude=${location.lat}&longitude=${location.lon}&current=temperature_2m,weathercode&temperature_unit=celsius&timezone=auto`,
    null,
    6000
  );

  if (data && data.current) {
    const tempC = data.current.temperature_2m;
    const tempF = ((tempC * 9) / 5 + 32).toFixed(0);
    const weatherCode = data.current.weathercode;
    const clima = `${tempC}°C / ${tempF}°F · ${weatherCode ?? 'offline'}`;
    const climaEl = _el('hdr-clima');
    if (climaEl) climaEl.textContent = clima;
    window.NEURA_HUD.status.clima = clima;
  }
}

/* ── Init ─────────────────────────────────────────────── */
window.addEventListener('DOMContentLoaded', () => {
  _fetchStatus();
  _fetchClima();
  setInterval(_fetchStatus, INTERVALO_RECURSOS_S * 1000);
  setInterval(_fetchClima, 10 * 60 * 1000);
});