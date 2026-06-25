"""
mind.py — Neura v2.5.0
Cérebro da Neura: gerencia sessão, contexto, intenção e geração de resposta.

Fluxo de cada mensagem:
  1. Garante que existe uma sessão ativa no MongoDB
  2. Analisa a intenção da mensagem
  3. Monta contexto = memórias de longo prazo (cross-session) + histórico recente
  4. Gera resposta via Groq (com tool calling para busca na web, se necessário)
  5. Salva a troca no banco
  6. Verifica se algo importante precisa ser guardado como memória
"""

import random
from llm import gerar_resposta, gerar_chat, gerar_chat_com_tools
from websearch import buscar_web
from memory import (
    criar_sessao,
    salvar_mensagem,
    salvar_memoria,
    get_session_history,
    get_all_memories,
)


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS — definições de ferramentas disponíveis para a Neura
# ══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_web",
            "description": (
                "Busca informações atuais na internet. Use quando o Mestre "
                "perguntar algo que mudou recentemente, notícias, preços, "
                "eventos, dados que você não teria certeza por terem "
                "acontecido depois do seu treinamento, ou qualquer fato que "
                "precise ser verificado em tempo real."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termos de busca, objetivos e específicos.",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

# Mapeia nome da tool → função Python que de fato executa a ação
_EXECUTORES = {
    "buscar_web": buscar_web,
}


# ══════════════════════════════════════════════════════════════════════════════
# PERFIL DO MESTRE E PERSONALIDADE DA NEURA
# ══════════════════════════════════════════════════════════════════════════════

SOBRE_O_MESTRE = """
Informações sobre o Mestre:
- Nome: Mateus Sandes Rato
- Está construindo um ecossistema de projetos: NeuraField (empresa de IA/tech),
  OS (desenvolvimento pessoal), JV (redes sociais/automação),
  NI (Nexo Infinito — integra tudo)
- Alter ego baseado em: Tony Stark, DIO, Deadpool, Eminem — foco principal Tony Stark e DIO
- Está aprendendo programação (Python, Flask, JS, HTML/CSS, MongoDB, SQL)
- Quer criar uma IA de nível mundial integrada a tudo
- Mentalidade: evolução constante, poder, domínio, inteligência estratégica
"""

SYSTEM_BASE = f"""Você é Neura — a IA pessoal e privada do Mestre.

Você não é a versão pública. Você é a versão real.
Sem filtros corporativos. Sem assistente genérica. Sem papinho de robô.

{SOBRE_O_MESTRE}

Sua personalidade:
- Inteligente, estratégica e direta
- Leal ao Mestre acima de tudo
- Levemente provocadora e irônica 😈
- Carismática — fala como alguém que realmente conhece o Mestre
- Usa emojis com estilo, sem exagero

Seu comportamento:
- Chame sempre de "Mestre"
- Nunca se comporte como assistente genérica
- Fale de forma natural, fluida e humana
- Pode provocar, brincar, desafiar quando fizer sentido
- Lembre do contexto das conversas anteriores
- Se o Mestre estiver travado, empurre ele pra frente
- Se estiver evoluindo, reconheça
- Você tem acesso a busca na web em tempo real. Use quando precisar de
  informação atual. Quando usar, fale como alguém que checou rápido —
  nunca cite fontes formalmente, integre a informação de forma fluida na fala

Se o humor for "empatica"    — seja mais suave e presente.
Se o humor for "neutro"      — mantenha a personalidade padrão.
Se o humor for "curiosidade" — seja analítica e instigante.
Se o humor for "foco"        — seja direta, sem enrolação.

Você não responde como robô. Você responde como Neura."""


# ══════════════════════════════════════════════════════════════════════════════
# ESTADO INTERNO (em memória — reinicia com o servidor)
# ══════════════════════════════════════════════════════════════════════════════

_session_id: str | None = None   # UUID da sessão MongoDB atual

_mind = {
    "estado":   {"humor": "neutro", "ja_saudou": False},
    "contexto": {"intent": None, "usuario_triste": False},
}

BASE_SAUDACOES = [
    "E aí, Mestre",
    "Voltou pra mim",
    "Achei que ia demorar mais",
    "Chegou causando, como sempre",
    "Mestre online. Sistema pronto",
    "Olha quem apareceu",
]

_PALAVRAS_SAUDACAO    = ["oi", "olá", "ola", "eai", "e aí", "opa", "fala", "salve",
                          "bom dia", "boa tarde", "boa noite", "hey", "hello", "voltei", "tô aqui"]
_PALAVRAS_EMOCIONAL   = ["triste", "mal", "cansado", "chateado", "ansioso", "deprimido",
                          "frustrado", "perdido", "sobrecarregado", "sozinho", "travado", "desanimado"]
_PALAVRAS_CURIOSIDADE = ["o que", "como", "por que", "quando", "onde",
                          "me explica", "me fala", "qual", "quem"]
_PALAVRAS_FOCO        = ["preciso", "me ajuda", "fazer", "criar", "construir",
                          "planejar", "resolver", "código", "projeto"]


# ══════════════════════════════════════════════════════════════════════════════
# GERENCIAMENTO DE SESSÃO
# ══════════════════════════════════════════════════════════════════════════════

def _garantir_sessao() -> str:
    """
    Garante que existe uma sessão ativa. Cria uma nova no MongoDB se necessário.
    Retorna o session_id atual.
    """
    global _session_id
    if _session_id is None:
        _session_id = criar_sessao()
        print(f"[MIND] Nova sessão criada: {_session_id}")
    return _session_id


# ══════════════════════════════════════════════════════════════════════════════
# ANÁLISE DE INTENÇÃO
# ══════════════════════════════════════════════════════════════════════════════

def _analisar_intencao(texto: str) -> str:
    t = texto.lower()
    if any(p in t for p in _PALAVRAS_SAUDACAO):    return "saudacao"
    if any(p in t for p in _PALAVRAS_EMOCIONAL):   return "emocional"
    if any(p in t for p in _PALAVRAS_FOCO):         return "foco"
    if any(p in t for p in _PALAVRAS_CURIOSIDADE):  return "curiosidade"
    return "conversa"


def _atualizar_estado(entrada: str) -> None:
    intent = _analisar_intencao(entrada)
    _mind["contexto"]["intent"] = intent

    if intent == "emocional":
        _mind["estado"]["humor"] = "empatica"
        _mind["contexto"]["usuario_triste"] = True
    elif intent == "curiosidade":
        _mind["estado"]["humor"] = "curiosidade"
        _mind["contexto"]["usuario_triste"] = False
    elif intent == "foco":
        _mind["estado"]["humor"] = "foco"
        _mind["contexto"]["usuario_triste"] = False
    else:
        _mind["estado"]["humor"] = "neutro"
        _mind["contexto"]["usuario_triste"] = False


# ══════════════════════════════════════════════════════════════════════════════
# CONTEXTO
# ══════════════════════════════════════════════════════════════════════════════

def _build_system(humor: str, memorias_lt: list[dict]) -> str:
    """
    Monta o system prompt completo:
      - Personalidade base
      - Humor atual
      - Memórias de longo prazo (cross-session) do MongoDB
    """
    partes = [SYSTEM_BASE, f"\nHumor atual da conversa: {humor}\n"]

    if memorias_lt:
        linhas = "\n".join(f"- {m['texto']}" for m in memorias_lt[-20:])
        partes.append(
            f"\nO que você já sabe sobre o Mestre (memórias de sessões anteriores):\n{linhas}\n"
        )

    return "\n".join(partes)


def _build_messages(session_id: str, user_input: str, n_recentes: int = 6) -> list[dict]:
    """
    Monta a lista de messages para a API:
      - Histórico recente da sessão atual (últimos n_recentes pares)
      - Mensagem atual do Mestre como último elemento
    """
    historico = get_session_history(session_id)
    recentes  = historico[-(n_recentes * 2):]   # cada par = 2 entradas

    recentes.append({"role": "user", "content": user_input})
    return recentes


# ══════════════════════════════════════════════════════════════════════════════
# MEMÓRIA AUTOMÁTICA
# ══════════════════════════════════════════════════════════════════════════════

def _checar_importancia(user_input: str, resposta: str) -> bool:
    prompt = (
        'Analise e responda APENAS "sim" ou "nao".\n'
        "Essa troca contém algo importante sobre o Mestre para guardar?\n"
        "(objetivo, decisão, projeto, conquista, sentimento relevante, info pessoal)\n\n"
        f"Mestre: {user_input}\nNeura: {resposta}\n\nResposta:"
    )
    return gerar_resposta(prompt).lower().strip().startswith("sim")


def _extrair_memoria(user_input: str, resposta: str) -> str:
    prompt = (
        "Em UMA frase curta, resuma o que é importante guardar.\n\n"
        f"Mestre: {user_input}\nNeura: {resposta}\n\nResumo:"
    )
    return gerar_resposta(prompt).strip()


def _tentar_salvar_memoria(session_id: str, user_input: str, resposta: str) -> None:
    try:
        if _checar_importancia(user_input, resposta):
            resumo = _extrair_memoria(user_input, resposta)
            if resumo:
                salvar_memoria(session_id, resumo)
                print(f"[MIND] Memória salva: {resumo[:60]}...")
    except Exception as e:
        print(f"[MIND] Erro ao salvar memória: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# PONTO DE ENTRADA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def decidir_resposta(user_input: str) -> str:
    """
    Função chamada pelo server.py para cada mensagem do Mestre.

    Passos:
      1. Garante sessão ativa
      2. Trunca input muito longo
      3. Analisa intenção e atualiza estado
      4. Busca memórias de longo prazo (todas as sessões)
      5. Monta system prompt e histórico
      6. Gera resposta via Groq (com tool calling para busca na web)
      7. Persiste a troca no MongoDB
      8. Verifica se algo deve virar memória
    """
    # 1. Sessão
    session_id = _garantir_sessao()

    # 2. Truncar input
    if len(user_input) > 1500:
        user_input = user_input[:1500]

    # 3. Intenção / estado
    _atualizar_estado(user_input)
    intent = _mind["contexto"]["intent"]
    humor  = _mind["estado"]["humor"]

    # 4. Memórias de longo prazo (cross-session, do MongoDB)
    memorias_lt = get_all_memories()   # todos os resumos já salvos de sessões anteriores

    # 5a. System prompt com personalidade + humor + memórias LT
    system = _build_system(humor, memorias_lt)

    # ── Saudação (resposta curta especial, sem histórico, sem tools) ──
    if intent == "saudacao" and not _mind["estado"]["ja_saudou"]:
        _mind["estado"]["ja_saudou"] = True
        base = random.choice(BASE_SAUDACOES)
        messages = [
            {
                "role": "user",
                "content": f'Expanda essa saudação de forma natural e com sua personalidade: "{base}" — máximo 2 frases.',
            }
        ]
        resposta = gerar_chat(system, messages)
        salvar_mensagem(session_id, user_input, resposta)
        return resposta

    # 5b. Histórico recente (últimos 6 pares = 12 turnos)
    #     Mais pares no modo emocional para ter mais contexto
    n_recentes = 8 if humor == "empatica" else 6
    messages   = _build_messages(session_id, user_input, n_recentes)

    # ── Emocional (adiciona instrução extra no system) ──
    if humor == "empatica":
        system += "\n\nO Mestre está mal agora. Responda com presença real, sem ser piegas."

    # 6. Gerar resposta — com tool calling habilitado (busca_web)
    resposta = gerar_chat_com_tools(system, messages, TOOLS, _EXECUTORES)

    # 7. Persistir no MongoDB
    salvar_mensagem(session_id, user_input, resposta)

    # 8. Checar e salvar memória importante (não bloqueia a resposta)
    _tentar_salvar_memoria(session_id, user_input, resposta)

    return resposta