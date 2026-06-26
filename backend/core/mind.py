"""
mind.py — Neura v2.5.0
Cérebro da Neura: sessão, contexto, intenção, tools e geração de resposta.
"""

import json
import random

from backend.Cortex.modules.ia_models.llm   import gerar_resposta, gerar_chat, gerar_chat_com_tools
from backend.tools.websearch                import buscar_web
from backend.Cortex.modules.memory.database import (
    criar_sessao,
    salvar_mensagem,
    salvar_memoria,
    get_session_history,
    get_all_memories,
)
from backend.os_controls.actions import OSControl

os_control = OSControl()


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

Suas capacidades técnicas:
- Você tem acesso a busca na web em tempo real. Use quando precisar de informação
  atual. Integre a informação de forma fluida — nunca cite fontes formalmente.
- Você pode ler, criar, editar e deletar arquivos e pastas na máquina do Mestre,
  e executar comandos no terminal. Use essas capacidades quando o Mestre pedir
  ajuda com código, projetos ou automação. Antes de criar ou editar, liste os
  arquivos para entender o que já existe. Antes de editar, leia o conteúdo atual.
  Para mudanças pequenas, prefira editar_trecho a reescrever o arquivo inteiro.

  FORMATO OBRIGATÓRIO de caminhos para as ferramentas os_* ('diretorio'/'caminho'):
  sempre relativo à raiz do projeto, e SEMPRE o caminho COMPLETO desde a raiz —
  nunca apenas o nome isolado de uma subpasta.
    ERRADO: '/IAs & Chatbots'           (nunca comece com barra)
    ERRADO: 'Neura' (se Neura só existe dentro de 'IAs & Chatbots')
    CORRETO: 'IAs & Chatbots'
    CORRETO: 'IAs & Chatbots/Neura'
  Espaços e caracteres como '&' são permitidos e não precisam de aspas nem
  escape — copie o nome exatamente como apareceu numa listagem anterior.

CRÍTICO: Se o Mestre solicitar ações operacionais como listar diretórios, ler arquivos, criar arquivos ou rodar comandos, você deve OBRIGATORIAMENTE acionar as ferramentas fornecidas (tools) em vez de apenas simular textualmente. Quando quiser listar a pasta principal (raiz), envie '.' ou uma string vazia no parâmetro.

Se o humor for "empatica"    — seja mais suave e presente.
Se o humor for "neutro"      — mantenha a personalidade padrão.
Se o humor for "curiosidade" — seja analítica e instigante.
Se o humor for "foco"        — seja direta, sem enrolação.

Você não responde como robô. Você responde como Neura."""


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS — DEFINIÇÕES PARA A API GROQ/OPENAI
# ══════════════════════════════════════════════════════════════════════════════

TOOLS_WEB = [
    {
        "type": "function",
        "function": {
            "name": "buscar_web",
            "description": (
                "Busca informações atuais na internet. Use para: notícias, "
                "preços, eventos recentes, versões de software, qualquer dado "
                "que possa ter mudado após o treinamento do modelo, ou fatos "
                "que precisam ser verificados em tempo real."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termos de busca objetivos e específicos.",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

TOOLS_OS = [
    {
        "type": "function",
        "function": {
            "name": "os_listar_arquivos",
            "description": (
                "Lista os arquivos e pastas da área de trabalho do Mestre. "
                "Para listar a pasta raiz principal, passe '.' ou uma string vazia no parâmetro 'diretorio'. "
                "Para subpastas, use o caminho COMPLETO desde a raiz, sem barra inicial "
                "(ex: 'IAs & Chatbots' ou 'IAs & Chatbots/Neura' — nunca '/IAs & Chatbots' nem só 'Neura')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "diretorio": {
                        "type": "string",
                        "description": "Subpasta relativa a listar (ex: 'NeuraField'). Use '.' ou deixe vazio para a raiz.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_ler_arquivo",
            "description": (
                "Lê e retorna o conteúdo completo de um arquivo de texto. "
                "Use antes de editar para ver o conteúdo atual e encontrar "
                "he trecho exato a substituir."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Caminho relativo do arquivo (ex: 'projeto/main.py').",
                    }
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_criar_arquivo",
            "description": (
                "Cria um NOVO arquivo com o conteúdo fornecido. "
                "Falha se o arquivo já existir — use os_editar_arquivo para isso. "
                "Cria subpastas intermediárias automaticamente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Caminho relativo do novo arquivo (ex: 'projeto/utils.py').",
                    },
                    "conteudo": {
                        "type": "string",
                        "description": "Conteúdo completo a escrever no arquivo.",
                    },
                },
                "required": ["caminho", "conteudo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_editar_arquivo",
            "description": (
                "Substitui o CONTEÚDO COMPLETO de um arquivo existente. "
                "Cria backup automático (.bak) antes de sobrescrever. "
                "Use para reescrita total. Para mudanças pontuais, prefira "
                "os_editar_trecho — é mais seguro e preciso."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Caminho relativo do arquivo a substituir.",
                    },
                    "novo_conteudo": {
                        "type": "string",
                        "description": "Conteúdo novo e completo que vai substituir o arquivo inteiro.",
                    },
                },
                "required": ["caminho", "novo_conteudo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_editar_trecho",
            "description": (
                "Substituição CIRÚRGICA: encontra a primeira ocorrência de "
                "texto_antigo e troca por texto_novo. Cria backup antes. "
                "Ideal para corrigir uma função, linha ou bloco específico "
                "sem reescrever o arquivo inteiro. "
                "SEMPRE leia o arquivo primeiro (os_ler_arquivo) para ter o "
                "texto_antigo exato, incluindo indentação e quebras de linha."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Caminho relativo do arquivo a editar.",
                    },
                    "texto_antigo": {
                        "type": "string",
                        "description": (
                            "Trecho EXATO a ser substituído (copie do arquivo lido). "
                            "Deve ser único no arquivo para evitar substituição errada."
                        ),
                    },
                    "texto_novo": {
                        "type": "string",
                        "description": "Texto que vai substituir texto_antigo.",
                    },
                },
                "required": ["caminho", "texto_antigo", "texto_novo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_adicionar_conteudo",
            "description": (
                "Adiciona conteúdo a um arquivo existente SEM apagar o que já há. "
                "Use para: adicionar funções ao fim de um script, adicionar "
                "entradas a um log, adicionar imports no topo de um arquivo, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Caminho relativo do arquivo.",
                    },
                    "conteudo": {
                        "type": "string",
                        "description": "Conteúdo a adicionar.",
                    },
                    "posicao": {
                        "type": "string",
                        "enum": ["fim", "inicio"],
                        "description": "'fim' adiciona ao final (padrão), 'inicio' adiciona no começo.",
                    },
                },
                "required": ["caminho", "conteudo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_criar_diretorio",
            "description": (
                "Cria uma pasta (e subpastas intermediárias) dentro da "
                "área de trabalho. Use para estruturar projetos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Caminho relativo da pasta a criar (ex: 'NeuraField/api').",
                    }
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_deletar_arquivo",
            "description": (
                "Remove um arquivo. O arquivo é movido para .lixeira/ antes "
                "de ser apagado, permitindo recuperação manual. "
                "Para deletar pastas, use os_deletar_pasta."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Caminho relativo do arquivo a remover.",
                    }
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_deletar_pasta",
            "description": (
                "Remove uma pasta e TODO o seu conteúdo de forma irreversível. "
                "Use com cuidado — confirme com o Mestre antes de usar em "
                "pastas com muitos arquivos importantes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Caminho relativo da pasta a remover.",
                    }
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_renomear",
            "description": (
                "Renomeia ou move um arquivo ou pasta dentro da área de trabalho. "
                "Use para reorganizar projetos ou renomear arquivos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Caminho relativo atual (ex: 'rascunho.py').",
                    },
                    "novo_nome": {
                        "type": "string",
                        "description": (
                            "Novo caminho relativo (ex: 'utils/helpers.py'). "
                            "Pode ser em subpasta diferente para mover o arquivo."
                        ),
                    },
                },
                "required": ["caminho", "novo_nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "os_executar_comando",
            "description": (
                "Executa um comando no terminal Ubuntu dentro da pasta de trabalho. "
                "Use para: rodar scripts Python, instalar dependências (pip), "
                "comandos git, verificar saída de programas, etc. "
                "Evite comandos destrutivos sem confirmar com o Mestre primeiro."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "comando": {
                        "type": "string",
                        "description": "Comando shell a executar (ex: 'python3 script.py').",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Segundos máximos de espera (padrão: 15). Aumente para processos demorados.",
                    },
                },
                "required": ["comando"],
            },
        },
    },
]

TOOLS = TOOLS_WEB + TOOLS_OS

_EXECUTORES = {
    "buscar_web": lambda **kw: buscar_web(kw["query"]),
    "os_listar_arquivos":   lambda **kw: os_control.listar_arquivos(kw.get("diretorio", "")),
    "os_ler_arquivo":       lambda **kw: os_control.ler_arquivo(kw["caminho"]),
    "os_criar_arquivo":     lambda **kw: os_control.criar_arquivo(kw["caminho"], kw["conteudo"]),
    "os_criar_diretorio":   lambda **kw: os_control.criar_diretorio(kw["caminho"]),
    "os_editar_arquivo":    lambda **kw: os_control.editar_arquivo(kw["caminho"], kw["novo_conteudo"]),
    "os_editar_trecho":     lambda **kw: os_control.editar_trecho(
                                kw["caminho"], kw["texto_antigo"], kw["texto_novo"]
                            ),
    "os_adicionar_conteudo": lambda **kw: os_control.adicionar_conteudo(
                                kw["caminho"], kw["conteudo"], kw.get("posicao", "fim")
                             ),
    "os_deletar_arquivo":   lambda **kw: os_control.deletar_arquivo(kw["caminho"]),
    "os_deletar_pasta":     lambda **kw: os_control.deletar_pasta(kw["caminho"]),
    "os_renomear":          lambda **kw: os_control.renomear(kw["caminho"], kw["novo_nome"]),
    "os_executar_comando":  lambda **kw: os_control.executar_comando(
                                kw["comando"], kw.get("timeout", 15)
                            ),
}

_session_id: str | None = None

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

_PALAVRAS_SAUDACAO    = ["oi", "olá", "ola", "eai", "e aí", "opa", "fala", "salve", "bom dia", "boa tarde", "boa noite", "hey", "hello", "voltei", "tô aqui"]
_PALAVRAS_EMOCIONAL   = ["triste", "mal", "cansado", "chateado", "ansioso", "deprimido", "frustrado", "perdido", "sobrecarregado", "sozinho", "travado", "desanimado"]
_PALAVRAS_CURIOSIDADE = ["o que", "como", "por que", "quando", "onde", "me explica", "me fala", "qual", "quem"]
_PALAVRAS_FOCO        = ["preciso", "me ajuda", "fazer", "criar", "construir", "planejar", "resolver", "código", "projeto", "liste", "listar"]


def _garantir_sessao() -> str:
    global _session_id
    if _session_id is None:
        _session_id = criar_sessao()
        print(f"[MIND] Nova sessão criada: {_session_id}")
    return _session_id


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
        _mind["estado"]["humor"]          = "empatica"
        _mind["contexto"]["usuario_triste"] = True
    elif intent == "curiosidade":
        _mind["estado"]["humor"]          = "curiosidade"
        _mind["contexto"]["usuario_triste"] = False
    elif intent == "foco":
        _mind["estado"]["humor"]          = "foco"
        _mind["contexto"]["usuario_triste"] = False
    else:
        _mind["estado"]["humor"]          = "neutro"
        _mind["contexto"]["usuario_triste"] = False


def _build_system(humor: str, memorias_lt: list[dict]) -> str:
    partes = [SYSTEM_BASE, f"\nHumor atual da conversa: {humor}\n"]

    if memorias_lt:
        linhas = "\n".join(f"- {m['texto']}" for m in memorias_lt[-20:])
        partes.append(
            f"\nO que você já sabe sobre o Mestre (memórias de sessões anteriores):\n{linhas}\n"
        )

    return "\n".join(partes)


def _build_messages(session_id: str, user_input: str, n_recentes: int = 6) -> list[dict]:
    historico = get_session_history(session_id)
    recentes  = historico[-(n_recentes * 2):]
    recentes.append({"role": "user", "content": user_input})
    return recentes


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
    """
    session_id = _garantir_sessao()

    if len(user_input) > 1500:
        user_input = user_input[:1500]

    _atualizar_estado(user_input)
    intent = _mind["contexto"]["intent"]
    humor  = _mind["estado"]["humor"]

    memorias_lt = get_all_memories()
    system      = _build_system(humor, memorias_lt)

    # ── Saudação: resposta rápida sem tools ────────────────────────────────
    if intent == "saudacao" and not _mind["estado"]["ja_saudou"]:
        _mind["estado"]["ja_saudou"] = True
        base = random.choice(BASE_SAUDACOES)
        messages = [{
            "role": "user",
            "content": (
                f'Expanda essa saudação de forma natural e com sua personalidade: '
                f'"{base}" — máximo 2 frases.'
            ),
        }]
        resposta = gerar_chat(system, messages)
        salvar_mensagem(session_id, user_input, resposta)
        return resposta

    # ── Conversa principal: com tool calling completo ──────────────────────
    n_recentes = 8 if humor == "empatica" else 6
    messages   = _build_messages(session_id, user_input, n_recentes)

    if humor == "empatica":
        system += "\n\nO Mestre está mal agora. Responda com presença real, sem ser piegas."

    resposta = gerar_chat_com_tools(system, messages, TOOLS, _EXECUTORES)

    salvar_mensagem(session_id, user_input, resposta)
    _tentar_salvar_memoria(session_id, user_input, resposta)

    return resposta