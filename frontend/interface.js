const API = 'http://127.0.0.1:5000';

const input       = document.getElementById('textInput');
const btn         = document.getElementById('btnEnviar');
const chat        = document.getElementById('chat');
const sidebar     = document.getElementById('sidebar');
const overlay     = document.getElementById('overlay');
const sessionList = document.getElementById('session-list');
const label       = document.getElementById('session-label');

const clockH = document.getElementById('clock-h');
const clockM = document.getElementById('clock-m');
const clockS = document.getElementById('clock-s');

let modoHistorico = false;

function atualizarRelogio() {
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  if (clockH) clockH.textContent = pad(now.getHours());
  if (clockM) clockM.textContent = pad(now.getMinutes());
  if (clockS) clockS.textContent = pad(now.getSeconds());
}

atualizarRelogio();
setInterval(atualizarRelogio, 1000);

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    enviar();
  }
  if (e.key === 'Escape') input.value = '';
});

function adicionarMensagem(texto, tipo, historico = false) {
  const div = document.createElement('div');
  div.className = `msg ${tipo}${historico ? ' historico' : ''}`;
  div.innerText = texto;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function mostrarTyping() {
  const div = document.createElement('div');
  div.className = 'msg neura';
  div.id = 'typing';
  div.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function removerTyping() {
  const el = document.getElementById('typing');
  if (el) el.remove();
}

async function enviar() {
  if (modoHistorico) return;

  const texto = input.value.trim();
  if (!texto) return;

  adicionarMensagem(texto, 'user');
  input.value = '';
  input.disabled = true;
  btn.disabled   = true;

  mostrarTyping();

  try {
    const res = await fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mensagem: texto })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    removerTyping();
    adicionarMensagem(data.resposta, 'neura');

  } catch (err) {
    removerTyping();
    adicionarMensagem('// erro: servidor offline ou sem resposta', 'system');
    console.error(err);
  } finally {
    input.disabled = false;
    btn.disabled   = false;
    input.focus();
  }
}

function toggleSidebar() {
  const aberta = sidebar.classList.toggle('open');
  overlay.classList.toggle('visible', aberta);
  if (aberta) carregarSessoes();
}

async function carregarSessoes() {
  sessionList.innerHTML = '<p class="sidebar-loading">// carregando...</p>';

  try {
    const res  = await fetch(`${API}/sessions`);
    const data = await res.json();

    if (!data.length) {
      sessionList.innerHTML = '<p class="sidebar-loading">// nenhuma sessão encontrada</p>';
      return;
    }

    const grupos = {};
    data.forEach(s => {
      const dia = s.data || 'desconhecido';
      if (!grupos[dia]) grupos[dia] = [];
      grupos[dia].push(s);
    });

    sessionList.innerHTML = '';

    Object.entries(grupos).forEach(([dia, sessoes]) => {
      const group = document.createElement('div');
      group.className = 'day-group';

      const dayLabel = document.createElement('div');
      dayLabel.className = 'day-label';
      dayLabel.textContent = formatarDia(dia);
      group.appendChild(dayLabel);

      sessoes.forEach(s => {
        const hora = s.criado_em
          ? new Date(s.criado_em).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
          : '--:--';
        const nome = s.nome || `Sessão ${hora}`;

        const item = document.createElement('div');
        item.className = 'session-item';
        item.dataset.id = s.id;
        item.innerHTML = `
          <div class="s-name-row">
            <span class="s-name">${nome}</span>
            <button class="rename-btn" title="Renomear">✎</button>
          </div>
          <div class="s-meta">${hora} · ${s.total_msgs} msg</div>
        `;

        const nameEl    = item.querySelector('.s-name');
        const renameBtn = item.querySelector('.rename-btn');
        const fn        = () => iniciarRenomear(item, s.id, nome);

        nameEl.addEventListener('dblclick', fn);
        renameBtn.addEventListener('click', fn);
        item.addEventListener('click', e => {
          if (e.target.classList.contains('rename-btn')) return;
          abrirSessao(s.id, item);
        });

        group.appendChild(item);
      });

      sessionList.appendChild(group);
    });

  } catch (err) {
    sessionList.innerHTML = '<p class="sidebar-loading">// erro ao carregar</p>';
  }
}

function formatarDia(dataStr) {
  try {
    const hoje = new Date().toISOString().slice(0, 10);
    if (dataStr === hoje) return 'HOJE';
    const d = new Date(dataStr + 'T00:00:00');
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch { return dataStr; }
}

function iniciarRenomear(item, sessionId, nomeAtual) {
  const nameEl = item.querySelector('.s-name');

  const inputEl = document.createElement('input');
  inputEl.className   = 'rename-input';
  inputEl.value       = nomeAtual.startsWith('Sessão') ? '' : nomeAtual;
  inputEl.placeholder = 'Nome da sessão...';
  inputEl.maxLength   = 40;
  nameEl.replaceWith(inputEl);
  inputEl.focus();

  const confirmar = async () => {
    const novo = inputEl.value.trim();
    if (!novo) { inputEl.replaceWith(nameEl); return; }
    try {
      await fetch(`${API}/sessions/${sessionId}/rename`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nome: novo })
      });
      nameEl.textContent = novo;
    } catch (err) { console.error(err); }
    inputEl.replaceWith(nameEl);
  };

  inputEl.addEventListener('blur', confirmar);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter')  confirmar();
    if (e.key === 'Escape') inputEl.replaceWith(nameEl);
  });
}

async function abrirSessao(sessionId, itemEl) {
  document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
  itemEl.classList.add('active');

  toggleSidebar();

  chat.innerHTML = '';
  modoHistorico  = true;
  input.disabled = true;
  btn.disabled   = true;
  label.textContent = 'HISTÓRICO';

  mostrarBotaoVoltar();
  adicionarMensagem(`// sessão ${sessionId}`, 'system');

  try {
    const resMsg = await fetch(`${API}/sessions/${sessionId}/messages`);
    const msgs   = await resMsg.json();

    if (!msgs.length) {
      adicionarMensagem('// sessão sem mensagens', 'system');
    } else {
      msgs.forEach(m => {
        adicionarMensagem(m.user, 'user', true);
        adicionarMensagem(m.neura, 'neura', true);
      });
    }

    const resMem = await fetch(`${API}/sessions/${sessionId}/memories`);
    const mems   = await resMem.json();

    if (mems.length) {
      adicionarMensagem('// memórias importantes desta sessão:', 'system');
      mems.forEach(m => adicionarMensagem(`→ ${m.texto}`, 'system'));
    }

  } catch (err) {
    adicionarMensagem('// erro ao carregar sessão', 'system');
  }
}

function mostrarBotaoVoltar() {
  let back = document.getElementById('btn-back');
  if (!back) {
    back = document.createElement('button');
    back.id        = 'btn-back';
    back.className = 'back-btn';
    back.textContent = '← VOLTAR';
    back.onclick = voltarSessaoAtual;
    document.getElementById('input-area').insertBefore(
      back,
      document.getElementById('input-area').firstChild
    );
  }
  back.classList.add('visible');
}

function voltarSessaoAtual() {
  modoHistorico  = false;
  input.disabled = false;
  btn.disabled   = false;
  label.textContent = 'ONLINE';

  const back = document.getElementById('btn-back');
  if (back) back.classList.remove('visible');

  chat.innerHTML = '';
  adicionarMensagem('// de volta à sessão atual', 'system');
  input.focus();
}