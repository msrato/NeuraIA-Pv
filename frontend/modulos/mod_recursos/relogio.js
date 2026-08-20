/**
 * relogio.js — N.E.U.R.A. v2.8.6
 * Responsabilidade única: manter o relógio HH:MM:SS em tempo real.
 *
 * Depende de: nada (zero dependências externas)
 * Consome IDs HTML: clock-h, clock-m, clock-s
 *
 * Para adicionar/tirar lógica de tempo: edite só este arquivo.
 */

'use strict';

(function iniciarRelogio() {
  const h = document.getElementById('clock-h');
  const m = document.getElementById('clock-m');
  const s = document.getElementById('clock-s');

  function tick() {
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    if (h) h.textContent = pad(now.getHours());
    if (m) m.textContent = pad(now.getMinutes());
    if (s) s.textContent = pad(now.getSeconds());
  }

  tick();
  setInterval(tick, 1000);
})();