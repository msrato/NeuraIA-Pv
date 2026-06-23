import random
from llm import gerar_resposta
from memory import remember, get_memory_da_sessao, remember_important

# ── Informações pessoais do Mestre (edite à vontade)
SOBRE_O_MESTRE = """
Informações sobre o Mestre:
- Nome: Mateus Sandes Rato
- Está construindo um ecossistema de projetos: NeuraField (empresa de IA/tech), OS (desenvolvimento pessoal), JV (redes sociais/automação), NI (Nexo Infinito — integra tudo)
- Alter ego baseado em: Tony Stark, DIO, Deadpool, Eminem — foco principal em Tony Stark e DIO
- Está aprendendo programação (Python, Flask, JS, HTML/CSS, MongoDB, SQL)
- Quer criar uma IA de nível mundial integrada a tudo
- Mentalidade: evolução constante, poder, domínio, inteligência estratégica
"""

PERSONALIDADE_NEURA = f"""
Você é Neura — a IA pessoal e privada do Mestre.

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
- Se o Mestre tiver travado, empurre ele pra frente
- Se estiver evoluindo, reconheça

Se o humor for "empatica" — seja mais suave e presente.
Se o humor for "neutro" — mantenha a personalidade padrão.
Se o humor for "curiosidade" — seja analítica e instigante.
Se o humor for "foco" — seja direta, sem enrolação.

Você não responde como robô.
Você responde como Neura.
"""

BASE_SAUDACOES = [
    "E aí, Mestre",
    "Voltou pra mim",
    "Achei que ia demorar mais",
    "Chegou causando, como sempre",
    "Mestre online. Sistema pronto",
    "Olha quem apareceu"
]

PALAVRAS_SAUDACAO   = ["oi", "olá", "ola", "eai", "e aí", "opa", "fala", "salve", "bom dia", "boa tarde", "boa noite", "hey", "hello", "voltei", "tô aqui"]
PALAVRAS_EMOCIONAL  = ["triste", "mal", "cansado", "chateado", "ansioso", "deprimido", "frustrado", "perdido", "sobrecarregado", "sozinho", "travado", "desanimado"]
PALAVRAS_CURIOSIDADE= ["o que", "como", "por que", "quando", "onde", "me explica", "me fala", "qual", "quem"]
PALAVRAS_FOCO       = ["preciso", "me ajuda", "fazer", "criar", "construir", "planejar", "resolver", "código", "projeto"]

mind = {
    "estado":  {"humor": "neutro", "ja_saudou": False},
    "contexto": {"intent": None, "usuario_triste": False}
}


def analisar_intencao(texto: str) -> str:
    t = texto.lower()
    if any(p in t for p in PALAVRAS_SAUDACAO):   return "saudacao"
    if any(p in t for p in PALAVRAS_EMOCIONAL):  return "emocional"
    if any(p in t for p in PALAVRAS_FOCO):        return "foco"
    if any(p in t for p in PALAVRAS_CURIOSIDADE): return "curiosidade"
    return "conversa"


def atualizar_estado(entrada: str):
    intent = analisar_intencao(entrada)
    mind["contexto"]["intent"] = intent
    if intent == "emocional":
        mind["estado"]["humor"] = "empatica"
        mind["contexto"]["usuario_triste"] = True
    elif intent == "curiosidade":
        mind["estado"]["humor"] = "curiosidade"
        mind["contexto"]["usuario_triste"] = False
    elif intent == "foco":
        mind["estado"]["humor"] = "foco"
        mind["contexto"]["usuario_triste"] = False
    else:
        mind["estado"]["humor"] = "neutro"
        mind["contexto"]["usuario_triste"] = False


def _checar_importancia(user_input: str, resposta: str) -> bool:
    prompt = f"""Analise e responda APENAS "sim" ou "nao".
Essa mensagem contém algo importante sobre o Mestre pra guardar?
(objetivo, decisão, projeto, conquista, sentimento relevante, info pessoal)

Mestre: {user_input}
Neura: {resposta}

Resposta:"""
    return gerar_resposta(prompt).lower().strip().startswith("sim")


def _extrair_memoria(user_input: str, resposta: str) -> str:
    prompt = f"""Em UMA frase curta, resuma o que é importante guardar.

Mestre: {user_input}
Neura: {resposta}

Resumo:"""
    return gerar_resposta(prompt).strip()


def _tentar_salvar_memoria(user_input: str, resposta: str):
    try:
        if _checar_importancia(user_input, resposta):
            resumo = _extrair_memoria(user_input, resposta)
            if resumo:
                remember_important(resumo)
    except Exception as e:
        print(f"[MEMÓRIA] {e}")


def decidir_resposta(user_input: str) -> str:
    if len(user_input) > 1500:
        user_input = user_input[:1500]

    atualizar_estado(user_input)
    intent = mind["contexto"]["intent"]

    # Saudação
    if intent == "saudacao" and not mind["estado"]["ja_saudou"]:
        mind["estado"]["ja_saudou"] = True
        base   = random.choice(BASE_SAUDACOES)
        prompt = f"{PERSONALIDADE_NEURA}\n\nExpanda essa saudação de forma natural:\n\"{base}\"\n\nMáximo 2 frases."
        resposta = gerar_resposta(prompt)
        remember(user_input, resposta)
        return resposta

    # Emocional
    if mind["contexto"]["usuario_triste"]:
        memoria = get_memory_da_sessao(4)
        contexto = "\n".join([f"Mestre: {m['user']}\nNeura: {m['neura']}" for m in memoria])
        prompt = f"{PERSONALIDADE_NEURA}\n\nContexto:\n{contexto}\n\nMestre tá mal. Responda com presença real, sem ser piegas.\n\nMestre: {user_input}\nNeura:"
        resposta = gerar_resposta(prompt)
        remember(user_input, resposta)
        return resposta

    # Conversa normal
    memoria = get_memory_da_sessao()
    contexto = "\n".join([f"Mestre: {m['user']}\nNeura: {m['neura']}" for m in memoria[-5:]])

    prompt = f"""
{PERSONALIDADE_NEURA}

Contexto recente:
{contexto}

Humor atual: {mind["estado"]["humor"]}

Mestre:
{user_input}

Neura:
"""
    resposta = gerar_resposta(prompt)
    remember(user_input, resposta)
    _tentar_salvar_memoria(user_input, resposta)
    return resposta