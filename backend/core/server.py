"""
server.py — Neura v2.8.1
API Flask conectada ao MongoDB Atlas com suporte à rota da HUD de Memória.
"""

import sys
from pathlib import Path
# Garante que o Python enxergue a raiz do projeto (2 níveis acima de core/) para mapear o módulo 'backend'
sys.path.append(str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
# Correção do caminho: volta 2 níveis para achar o .env na raiz do backend
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

import random

from flask import Flask, request, jsonify
from flask_cors import CORS
from backend.core.mind import decidir_resposta
from backend.Cortex.modules.memory.database import (
    get_all_sessions,
    get_messages_by_session,
    get_important_memories,
    get_all_memories,  # alimenta o cérebro dinâmico
    renomear_sessao,
    ping_db,
)

app = Flask(__name__)
CORS(app)


# ── Utilidade: serializa datetime para ISO string ──────────────────────────────

def fmt_dt(dt):
    """Converte datetime (com ou sem timezone) para string ISO 8601."""
    if dt is None:
        return None
    return dt.isoformat()


# ── Health-check ────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    ok = ping_db()
    status = "ok" if ok else "mongo_offline"
    code   = 200 if ok else 503
    return jsonify({"status": status}), code


# ── Status de hardware / config (blindado contra falha de import) ──────────────

@app.route("/api/status", methods=["GET"])
def api_status():
    """Retorna os status de hardware e configurações da Neura."""
    ok = ping_db()

    # Simulação de oscilação enquanto não temos coleta real de hardware
    cpu_percent = random.randint(8, 18)
    ram_usado   = round(5.8 + random.uniform(-0.3, 0.4), 1)

    # Import isolado: se o voice_manager falhar por qualquer motivo
    # (path errado, módulo ausente, TTS não inicializado), a rota
    # continua respondendo 200 com um valor padrão em vez de 500.
    voz_modo = "AUTO"
    try:
        from backend.tools.spech import voice_manager
        voz_modo = getattr(voice_manager, "mode", "AUTO")
    except Exception as e:
        print(f"[STATUS-API] voice_manager indisponível: {e}")

    return jsonify({
        "status": "success",
        "cpu_percent": cpu_percent,
        "ram_usado_gb": ram_usado,
        "ram_total_gb": 16,
        "mongo_status": "CONECTADO" if ok else "DESCONECTADO",
        "voz_modo": voz_modo,
        "modelo": "openai/gpt-oss-120b"
    })


# ── Chat ───────────────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    data     = request.get_json(silent=True) or {}
    mensagem = data.get("mensagem", "").strip()

    if not mensagem:
        return jsonify({"resposta": "Fala algo, Mestre."})

    resposta = decidir_resposta(mensagem)
    return jsonify({"resposta": resposta})


# ── ROTA DA HUD: Nós de Memória (Cérebro Neural) ────────────────────────────────

_CATEGORIAS = [
    # (nome_categoria, cor_hex, palavras_chave)
    ("identidade",  "#34D399", ["mestre", "mateus", "rato", "stark", "dio", "personalidade"]),
    ("projeto",     "#00BFFF", ["projeto", "neura", "neurafield", "sistema", "app", "banco", "mongodb", "flask", "api"]),
    ("aprendizado", "#A78BFA", ["estudo", "aprend", "curso", "python", "javascript", "programac", "debug", "bug", "erro"]),
    ("objetivo",    "#F59E0B", ["objetivo", "meta", "plano", "quero", "vou", "criar"]),
    ("sentimento",  "#F472B6", ["sinto", "sente", "triste", "feliz", "cansad", "mal", "bem"]),
]

_COR_DEFAULT = "#6B7280"


def _categorizar_memoria(texto: str) -> tuple[str, str]:
    """Retorna a categoria e a cor do nó baseada no texto da memória."""
    t = (texto or "").lower()
    for nome, cor, palavras in _CATEGORIAS:
        if any(p in t for p in palavras):
            return nome, cor
    return "geral", _COR_DEFAULT


@app.route("/api/memorias_hud", methods=["GET"])
def api_memorias_hud():
    """Retorna as memórias reais do MongoDB estruturadas para o Vis.js."""
    try:
        memorias_raw = get_all_memories()
        nos = []

        for idx, mem in enumerate(memorias_raw):
            texto = mem.get("texto", "")
            categoria, cor = _categorizar_memoria(texto)

            nos.append({
                "id": str(mem.get("_id", idx)),
                "texto": texto,
                "categoria": categoria,
                "cor": cor,
            })

        return jsonify({
            "status": "ok",
            "total": len(nos),
            "nos": nos
        })
    except Exception as e:
        print(f"[HUD-API] Erro ao carregar memórias do MongoDB: {e}")
        return jsonify({
            "status": "erro",
            "nos": []
        }), 500


# ── Sessões ────────────────────────────────────────────────────────────────────

@app.route("/sessions", methods=["GET"])
def sessions():
    rows = get_all_sessions()
    return jsonify([
        {
            "id":         r["session_id"],
            "nome":       r.get("nome"),
            "data":       r.get("data"),
            "criado_em":  fmt_dt(r.get("criado_em")),
            "total_msgs": r.get("total_msgs", 0),
        }
        for r in rows
    ])


@app.route("/sessions/<session_id>/messages", methods=["GET"])
def session_messages(session_id):
    rows = get_messages_by_session(session_id)
    return jsonify([
        {
            "user":      r["user"],
            "neura":     r["neura"],
            "criado_em": fmt_dt(r.get("criado_em")),
        }
        for r in rows
    ])


@app.route("/sessions/<session_id>/memories", methods=["GET"])
def session_memories(session_id):
    rows = get_important_memories(session_id)
    return jsonify([
        {
            "texto":     r["texto"],
            "criado_em": fmt_dt(r.get("criado_em")),
        }
        for r in rows
    ])


@app.route("/sessions/<session_id>/rename", methods=["PATCH"])
def rename_session(session_id):
    data      = request.get_json(silent=True) or {}
    novo_nome = data.get("nome", "").strip()

    if not novo_nome:
        return jsonify({"erro": "Nome inválido"}), 400

    renomear_sessao(session_id, novo_nome)
    return jsonify({"ok": True})


if __name__ == "__main__":
    # use_reloader=False é crítico aqui: com debug=True, o reloader do Flask
    # sobe um SEGUNDO processo Python no boot para monitorar mudanças de
    # arquivo. Os dois processos disputam acesso exclusivo à placa de som
    # (ALSA), causando o SIGSEGV em snd_pcm_hw_open(). Sem o reloader,
    # continua em debug (autoreload de erro/traceback), mas com um só processo.
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)