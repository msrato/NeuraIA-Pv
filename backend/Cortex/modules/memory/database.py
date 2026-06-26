"""
memory.py — Neura v2.0.0
Camada de acesso ao MongoDB Atlas.

Collections:
  sessions  → metadados de cada conversa
  messages  → pares (user, neura) por sessão
  memories  → memórias importantes extraídas pelo mind.py

Variável de ambiente necessária no .env:
  MONGODB_URI=mongodb+srv://<user>:<senha>@<cluster>.mongodb.net/?retryWrites=true&w=majority
"""

import os
import uuid
from datetime import datetime, timezone

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure


# ── Conexão (singleton lazy) ───────────────────────────────────────────────────

_client: MongoClient | None = None
_db = None

def _get_db():
    """Retorna (e cria, se necessário) a conexão com o banco 'neura'."""
    global _client, _db
    if _db is None:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise EnvironmentError(
                "MONGODB_URI não definida. Adicione ao arquivo .env"
            )
        _client = MongoClient(uri, serverSelectionTimeoutMS=5_000)
        _db = _client["neura"]
        _ensure_indexes(_db)
    return _db


def _ensure_indexes(db) -> None:
    """Cria índices na primeira conexão (idempotente)."""
    db.sessions.create_index("session_id", unique=True)
    db.messages.create_index([("session_id", ASCENDING), ("criado_em", ASCENDING)])
    db.memories.create_index([("session_id", ASCENDING), ("criado_em", ASCENDING)])


# ── Utilitário ─────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Diagnóstico ────────────────────────────────────────────────────────────────

def ping_db() -> bool:
    """Retorna True se o MongoDB está acessível."""
    try:
        _get_db().command("ping")
        return True
    except (ConnectionFailure, Exception):
        return False


# ══════════════════════════════════════════════════════════════════════════════
# SESSÕES
# ══════════════════════════════════════════════════════════════════════════════

def criar_sessao() -> str:
    """
    Cria uma nova sessão no banco e retorna o session_id (UUID string).
    Chamado pelo mind.py no início de cada conversa.
    """
    db = _get_db()
    session_id = str(uuid.uuid4())
    agora = _now()

    db.sessions.insert_one({
        "session_id": session_id,
        "nome":       None,
        "criado_em":  agora,
        "data":       agora.strftime("%Y-%m-%d"),   # para agrupar por dia na sidebar
    })
    return session_id


def get_all_sessions() -> list[dict]:
    """
    Retorna todas as sessões ordenadas da mais recente para a mais antiga,
    com contagem de mensagens (total_msgs) calculada via aggregation.
    """
    db = _get_db()

    pipeline = [
        # Junta com a collection de mensagens para contar
        {
            "$lookup": {
                "from":         "messages",
                "localField":   "session_id",
                "foreignField": "session_id",
                "as":           "_msgs",
            }
        },
        # Projeta apenas os campos necessários
        {
            "$project": {
                "_id":        0,
                "session_id": 1,
                "nome":       1,
                "data":       1,
                "criado_em":  1,
                "total_msgs": {"$size": "$_msgs"},
            }
        },
        {"$sort": {"criado_em": DESCENDING}},
    ]

    return list(db.sessions.aggregate(pipeline))


def renomear_sessao(session_id: str, novo_nome: str) -> None:
    """Atualiza o nome de exibição de uma sessão na sidebar."""
    db = _get_db()
    db.sessions.update_one(
        {"session_id": session_id},
        {"$set": {"nome": novo_nome}},
    )


# ══════════════════════════════════════════════════════════════════════════════
# MENSAGENS
# ══════════════════════════════════════════════════════════════════════════════

def salvar_mensagem(session_id: str, user_msg: str, neura_msg: str) -> None:
    """
    Persiste um par (user, neura) na sessão.
    Chamado pelo mind.py após cada resposta gerada.
    """
    db = _get_db()
    db.messages.insert_one({
        "session_id": session_id,
        "user":       user_msg,
        "neura":      neura_msg,
        "criado_em":  _now(),
    })


def get_messages_by_session(session_id: str) -> list[dict]:
    """Retorna todos os pares user/neura de uma sessão, em ordem cronológica."""
    db = _get_db()
    return list(db.messages.find(
        {"session_id": session_id},
        {"_id": 0, "user": 1, "neura": 1, "criado_em": 1},
        sort=[("criado_em", ASCENDING)],
    ))


def get_session_history(session_id: str) -> list[dict]:
    """
    Retorna o histórico formatado para uso como contexto pelo mind.py
    (lista de dicts com role 'user'/'assistant').
    """
    msgs = get_messages_by_session(session_id)
    history = []
    for m in msgs:
        history.append({"role": "user",      "content": m["user"]})
        history.append({"role": "assistant",  "content": m["neura"]})
    return history


# ══════════════════════════════════════════════════════════════════════════════
# MEMÓRIAS IMPORTANTES
# ══════════════════════════════════════════════════════════════════════════════

def salvar_memoria(session_id: str, texto: str) -> None:
    """
    Persiste uma memória importante extraída pelo mind.py
    (ex.: fatos sobre o Mestre, preferências, decisões-chave).
    """
    db = _get_db()
    db.memories.insert_one({
        "session_id": session_id,
        "texto":      texto,
        "criado_em":  _now(),
    })


def get_important_memories(session_id: str) -> list[dict]:
    """Retorna as memórias de uma sessão em ordem cronológica."""
    db = _get_db()
    return list(db.memories.find(
        {"session_id": session_id},
        {"_id": 0, "texto": 1, "criado_em": 1},
        sort=[("criado_em", ASCENDING)],
    ))


def get_all_memories(session_id: str | None = None) -> list[dict]:
    """
    Retorna memórias de todas as sessões (ou de uma sessão específica).
    Útil para o mind.py construir contexto de longo prazo.
    """
    db = _get_db()
    filtro = {"session_id": session_id} if session_id else {}
    return list(db.memories.find(
        filtro,
        {"_id": 0, "session_id": 1, "texto": 1, "criado_em": 1},
        sort=[("criado_em", ASCENDING)],
    ))