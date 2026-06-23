"""
server.py — Neura v2.0.0
API Flask conectada ao MongoDB Atlas.
"""

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from flask import Flask, request, jsonify
from flask_cors import CORS
from mind import decidir_resposta
from memory import (
    get_all_sessions,
    get_messages_by_session,
    get_important_memories,
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


# ── Health-check ───────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    ok = ping_db()
    status = "ok" if ok else "mongo_offline"
    code   = 200 if ok else 503
    return jsonify({"status": status}), code


# ── Chat ───────────────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    data     = request.get_json(silent=True) or {}
    mensagem = data.get("mensagem", "").strip()

    if not mensagem:
        return jsonify({"resposta": "Fala algo, Mestre."})

    resposta = decidir_resposta(mensagem)
    return jsonify({"resposta": resposta})


# ── Sessões ────────────────────────────────────────────────────────────────────

@app.route("/sessions", methods=["GET"])
def sessions():
    """
    Retorna todas as sessões ordenadas por data desc.
    Cada sessão inclui total de mensagens para exibir na sidebar.
    """
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
    """Retorna as mensagens (pares user/neura) de uma sessão."""
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
    """Retorna as memórias importantes de uma sessão."""
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
    """Renomeia uma sessão."""
    data      = request.get_json(silent=True) or {}
    novo_nome = data.get("nome", "").strip()

    if not novo_nome:
        return jsonify({"erro": "Nome inválido"}), 400

    renomear_sessao(session_id, novo_nome)
    return jsonify({"ok": True})


# ── Entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)