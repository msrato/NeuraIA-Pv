/**
 * weather.js — N.E.U.R.A. v2.8.6
 * Responsabilidade única: buscar e exibir clima em tempo real.
 *
 * API usada: Open-Meteo (https://open-meteo.com) — gratuita, sem chave.
 * Geolocalização: navigator.geolocation → fallback para São Paulo se negado.
 *
 * Consome IDs HTML: hdr-clima
 * Atualiza a cada: INTERVALO_MIN minutos
 *
 * Para trocar a cidade padrão ou o intervalo: edite as constantes abaixo.
 * Para trocar de API: substitua apenas _buscarClima(), o resto não muda.
 */

'use strict';

/* ── Configuração ─────────────────────────────────────── */
const INTERVALO_MIN  = 10;                    // atualiza a cada 10 min
const FALLBACK_LAT   = -23.5505;             // São Paulo
const FALLBACK_LON   = -46.6333;

/* Mapeamento WMO weather code → descrição curta em PT-BR
   Ref: https://open-meteo.com/en/docs#weathervariables */
const WMO = {
  0:  'Céu limpo',
  1:  'Predominantemente limpo', 2: 'Parcialmente nublado', 3: 'Nublado',
  45: 'Neblina', 48: 'Neblina com gelo',
  51: 'Garoa leve', 53: 'Garoa moderada', 55: 'Garoa intensa',
  61: 'Chuva fraca', 63: 'Chuva moderada', 65: 'Chuva forte',
  71: 'Neve fraca', 73: 'Neve moderada', 75: 'Neve intensa',
  77: 'Granizo',
  80: 'Pancadas fracas', 81: 'Pancadas moderadas', 82: 'Pancadas fortes',
  95: 'Trovoada', 96: 'Trovoada c/ granizo', 99: 'Trovoada forte',
};

/* ── Núcleo ───────────────────────────────────────────── */
async function _buscarClima(lat, lon) {
  const url =
    `https://api.open-meteo.com/v1/forecast` +
    `?latitude=${lat}&longitude=${lon}` +
    `&current=temperature_2m,weathercode` +
    `&temperature_unit=celsius&timezone=auto`;

  const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
  if (!res.ok) throw new Error(`Open-Meteo HTTP ${res.status}`);
  return res.json();
}

function _cToF(c) {
  return ((c * 9) / 5 + 32).toFixed(0);
}

function _renderizar(data) {
  const el = document.getElementById('hdr-clima');
  if (!el) return;

  const tempC = data.current.temperature_2m;
  const code  = data.current.weathercode;
  const desc  = WMO[code] ?? `Cód ${code}`;

  el.textContent = `${tempC}°C / ${_cToF(tempC)}°F · ${desc}`;
}

function _mostrarErro() {
  const el = document.getElementById('hdr-clima');
  if (el) el.textContent = '-- / -- · offline';
}

async function _atualizar(lat, lon) {
  try {
    const data = await _buscarClima(lat, lon);
    _renderizar(data);
  } catch (err) {
    console.warn('[WEATHER] Falha ao buscar clima:', err.message);
    _mostrarErro();
  }
}

function _iniciar(lat, lon) {
  _atualizar(lat, lon);
  setInterval(() => _atualizar(lat, lon), INTERVALO_MIN * 60 * 1000);
}

/* ── Init: pede geolocalização; usa fallback se negado ── */
window.addEventListener('DOMContentLoaded', () => {
  if (!navigator.geolocation) {
    console.warn('[WEATHER] Geolocalização indisponível — usando fallback SP.');
    _iniciar(FALLBACK_LAT, FALLBACK_LON);
    return;
  }

  navigator.geolocation.getCurrentPosition(
    pos => {
      console.log('[WEATHER] Localização real obtida.');
      _iniciar(pos.coords.latitude, pos.coords.longitude);
    },
    () => {
      console.warn('[WEATHER] Geolocalização negada — usando fallback SP.');
      _iniciar(FALLBACK_LAT, FALLBACK_LON);
    },
    { timeout: 5000 }
  );
});