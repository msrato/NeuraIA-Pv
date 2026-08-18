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

/* ── Simulação offline (Flask indisponível) ───────────── */
function _simularRecursos() {
  const cpu = Math.floor(Math.random() * 14) + 6;
  const ram = (5.8 + Math.random() * 0.5).toFixed(1);

  const cpuEl = _el('cpu-load');
  const ramEl = _el('ram-load');
  if (cpuEl) cpuEl.textContent = `${cpu}%`;
  if (ramEl) ramEl.textContent = `${ram} / 16 GB`;
}

/* ── Aplica dados reais vindos da API ─────────────────── */
function _aplicarDados(data) {
  /* Hardware */
  const cpuEl = _el('cpu-load');
  const ramEl = _el('ram-load');
  if (cpuEl && data.cpu_percent   != null) cpuEl.textContent = `${data.cpu_percent}%`;
  if (ramEl && data.ram_usado_gb  != null)
    ramEl.textContent = `${data.ram_usado_gb} / ${data.ram_total_gb ?? '??'} GB`;

  /* Status do banco */
  const mongoEl = _el('mongo-status');
  if (mongoEl && data.mongo_status) mongoEl.textContent = data.mongo_status;

  /* Header — modo de voz e modelo ativo */
  const vozEl    = _el('hdr-voz');
  const modeloEl = _el('hdr-modelo');
  if (vozEl    && data.voz_modo) vozEl.textContent    = data.voz_modo;
  if (modeloEl && data.modelo)   modeloEl.textContent = data.modelo;
}

/* ── Fetch de /api/status ─────────────────────────────── */
async function _fetchStatus() {
  try {
    const res = await fetch(`${API}/api/status`, {
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _aplicarDados(data);
  } catch {
    /* Flask offline → simulação para não travar o display */
    _simularRecursos();
  }
}

/* ── Init ─────────────────────────────────────────────── */
window.addEventListener('DOMContentLoaded', () => {
  _fetchStatus();
  setInterval(_fetchStatus, INTERVALO_RECURSOS_S * 1000);
});