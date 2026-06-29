"""
llm.py — Neura v2.7.0 (LOCAL - OLLAMA, multi-modelo)
Interface com a API local do Ollama, com roteamento modular por perfil.

Funções públicas:
  escolher_perfil(texto)                                    → decide qual perfil usar
  gerar_resposta(prompt, perfil=...)                        → chamadas internas simples
  gerar_chat(system, messages, perfil=...)                  → conversa sem ferramentas
  gerar_chat_com_tools(system, messages, tools, exec, perfil=...) → conversa com tool calling

NOTA SOBRE O PERFIL 'seguranca':
  Existem modelos "uncensored" no Ollama voltados a cibersegurança ofensiva
  (ex.: variantes WhiteRabbitNeo). Eles não entram neste roteamento — o
  model card deles já vem com instrução pra contornar recusas de segurança,
  o que não é algo que eu vou cabear no pipeline da Neura. O perfil
  'seguranca' usa o MESMO modelo de código, só com temperatura mais baixa;
  o tom defensivo/educativo vem do system prompt que o mind.py monta.
"""

import os
import json
from openai import OpenAI

# ── Cliente Local Ollama (Formato compatível com OpenAI) ───────────────────────

_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"  # O Ollama local não exige chave real, mas precisa de uma string
)

MAX_TOOL_ITS = 6      # iterações máximas do loop de tool calling


# ══════════════════════════════════════════════════════════════════════════════
# PERFIS — roteamento modular de modelos
# ══════════════════════════════════════════════════════════════════════════════
#
# Cada perfil define qual modelo do Ollama usar e seus parâmetros padrão.
# mind.py escolhe o perfil (via escolher_perfil ou manualmente) e passa
# pelo parâmetro 'perfil' nas três funções públicas abaixo — não precisa
# saber o nome real da tag do modelo, só o nome do perfil.

PERFIS = {
    # Conversa geral, saudação, humor emocional — a "voz" padrão da Neura
    "conversa": {
        "model":       "llama3.2",
        "temperatura": 0.75,
        "max_tokens":  1024,
    },
    # Programação: debug, geração de código, revisão técnica
    "codigo": {
        "model":       "qwen2.5-coder:7b",
        "temperatura": 0.30,   # mais determinístico — precisão > criatividade
        "max_tokens":  2048,   # blocos de código costumam ser mais longos
    },
    # Cibersegurança — MESMO modelo de código, tom defensivo vem do system prompt
    "seguranca": {
        "model":       "qwen2.5-coder:7b",
        "temperatura": 0.30,
        "max_tokens":  2048,
    },
    # Didático — explicações, "como funciona", ensino passo a passo
    "didatico": {
        "model":       "llama3.2",
        "temperatura": 0.55,   # menos "solto" que a conversa casual
        "max_tokens":  1536,
    },
}

DEFAULT_PERFIL = "conversa"


def _resolver_perfil(perfil: str) -> dict:
    """Retorna a config do perfil, ou a config padrão se o nome não existir."""
    return PERFIS.get(perfil, PERFIS[DEFAULT_PERFIL])


# ── Heurística de roteamento (mind.py pode usar isso, ou escolher manualmente) ─

_PALAVRAS_SEGURANCA = [
    "vulnerabilidade", "vulnerável", "vulneravel", "segurança", "seguranca",
    "exploit", "criptografia", "senha", "firewall", "pentest", "owasp",
    "injeção sql", "sql injection", "xss", "csrf", "autenticação",
    "autenticacao", "hash", "criptografar", "malware", "phishing", "cve",
]
_PALAVRAS_CODIGO = [
    "código", "codigo", "função", "funcao", "classe", "bug", "debug",
    "refatora", "refatorar", "python", "javascript", "flask", "html",
    "css", "sql", "api", "endpoint", "biblioteca", "import ", "compilar",
    "exception", "traceback", "stack trace", "algoritmo", "script",
]
_PALAVRAS_DIDATICO = [
    "me explica", "explica como", "o que é", "o que e", "como funciona",
    "me ensina", "qual a diferença", "diferenca entre", "por que",
]


def escolher_perfil(texto: str) -> str:
    """
    Decide qual perfil de modelo usar com base no conteúdo da mensagem.
    Ordem de prioridade: segurança > código > didático > conversa.

    Segurança vem primeiro porque perguntas de segurança quase sempre
    também mencionam código — sem essa prioridade, cairiam em 'codigo' e
    perderiam o tom defensivo/educativo do perfil de segurança.

    mind.py pode chamar isso automaticamente, ou ignorar e escolher o
    perfil manualmente (ex.: forçar 'codigo' quando uma tool os_criar_arquivo
    for chamada com um caminho terminando em '.py').
    """
    if not texto:
        return DEFAULT_PERFIL

    t = texto.lower()

    if any(p in t for p in _PALAVRAS_SEGURANCA):
        return "seguranca"
    if any(p in t for p in _PALAVRAS_CODIGO):
        return "codigo"
    if any(p in t for p in _PALAVRAS_DIDATICO):
        return "didatico"
    return DEFAULT_PERFIL


# ══════════════════════════════════════════════════════════════════════════════
# CHAMADA INTERNA SIMPLES
# ══════════════════════════════════════════════════════════════════════════════

def gerar_resposta(prompt: str, perfil: str = DEFAULT_PERFIL, temperatura: float | None = None) -> str:
    """
    Single-turn sem sistema — para tarefas internas do mind.py
    (checar importância, extrair resumo de memória). Por padrão usa o
    perfil 'conversa'; passe 'perfil' se quiser rotear pra outro modelo.
    """
    cfg = _resolver_perfil(perfil)
    try:
        completion = _client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=temperatura if temperatura is not None else cfg["temperatura"],
            max_tokens=cfg["max_tokens"],
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[LLM] Erro em gerar_resposta (perfil={perfil}): {e}")
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# CONVERSA DIRETA (SEM FERRAMENTAS)
# ══════════════════════════════════════════════════════════════════════════════

def gerar_chat(system_prompt: str, messages: list[dict], perfil: str = DEFAULT_PERFIL) -> str:
    """
    Gera uma resposta simples respeitando o histórico e a persona,
    roteada pro modelo definido no perfil escolhido.
    """
    cfg = _resolver_perfil(perfil)
    payload = [{"role": "system", "content": system_prompt}] + messages

    try:
        completion = _client.chat.completions.create(
            model=cfg["model"],
            messages=payload,
            temperature=cfg["temperatura"],
            max_tokens=cfg["max_tokens"],
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[LLM] Erro em gerar_chat (perfil={perfil}): {e}")
        return "Mestre, meu cérebro local deu um pequeno estalo. Pode repetir?"


# ══════════════════════════════════════════════════════════════════════════════
# LOOP COMPLETO DE TOOL CALLING (CONVERSA + FUNÇÕES OPERACIONAIS)
# ══════════════════════════════════════════════════════════════════════════════

def gerar_chat_com_tools(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    executores: dict,
    perfil: str = DEFAULT_PERFIL,
) -> str:
    """
    Loop iterativo de Tool Calling, rodando inteiro no modelo do perfil
    escolhido (o mesmo modelo é usado em todas as iterações do loop —
    trocar de modelo no meio do loop custaria um reload caro no Ollama).
    Executa as funções em Python do os_control e devolve os resultados
    ao modelo local até que ele decida gerar um texto final pro Mestre.
    """
    cfg    = _resolver_perfil(perfil)
    modelo = cfg["model"]
    payload = [{"role": "system", "content": system_prompt}] + messages

    for iteracao in range(MAX_TOOL_ITS):
        try:
            completion = _client.chat.completions.create(
                model=modelo,
                messages=payload,
                tools=tools,
                tool_choice="auto",
                temperature=cfg["temperatura"],
                max_tokens=cfg["max_tokens"],
            )
        except Exception as e:
            print(f"[LLM] gerar_chat_com_tools — erro na API local (perfil={perfil}, iter {iteracao}): {e}")
            return "Mestre, tive uma falha ao tentar processar essa ação no meu motor local."

        msg_resposta = completion.choices[0].message
        payload.append(msg_resposta)

        # Se o modelo não quiser chamar nenhuma ferramenta, terminou! Retorna o texto.
        if not msg_resposta.tool_calls:
            return (msg_resposta.content or "").strip()

        # Execução sequencial das ferramentas solicitadas pelo modelo
        for tc in msg_resposta.tool_calls:
            nome = tc.function.name

            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}

            if nome in executores:
                try:
                    resultado = executores[nome](**args)
                except Exception as e:
                    resultado = f"// Erro interno ao executar '{nome}': {e}"
            else:
                resultado = f"// Ferramenta '{nome}' não registrada nos executores."

            print(f"[TOOL] {nome}({_fmt_args(args)}) → {resultado[:120]}")

            # Resultado da tool anexado de volta ao payload para a IA ler na próxima iteração
            payload.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      resultado,
            })

    # Excedeu MAX_TOOL_ITS — tenta uma última chamada sem ferramentas para forçar resposta final
    print(f"[LLM] Limite de {MAX_TOOL_ITS} iterações atingido (perfil={perfil}). Forçando resposta final.")
    try:
        resp = _client.chat.completions.create(
            model=modelo,
            messages=payload,
            temperature=cfg["temperatura"],
            max_tokens=cfg["max_tokens"],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[LLM] Erro na chamada final pós-limite: {e}")
        return "Mestre, atingi o limite de operações locais encadeadas. Me fala o que precisa de outra forma."


# ── Helper de debug ────────────────────────────────────────────────────────────

def _fmt_args(args: dict) -> str:
    """Formata argumentos para log sem vazar strings longas."""
    resumo = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 60:
            resumo[k] = v[:60] + "..."
        else:
            resumo[k] = v
    return str(resumo)