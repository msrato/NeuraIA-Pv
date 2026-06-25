"""
llm.py — Neura v2.5.0
Interface com a API da Groq.

Funções públicas:
  gerar_resposta(prompt)                        → chamadas internas simples
                                                    (checar importância, extrair memória)
  gerar_chat(system, messages)                   → conversa simples, sem tools
                                                    (usado na saudação)
  gerar_chat_com_tools(system, messages, tools,
                        executores)              → conversa principal, com
                                                    suporte a tool calling
                                                    (usado na busca na web)

NOTA DE MIGRAÇÃO (24/06/2026):
  llama-3.3-70b-versatile foi anunciado como depreciado pela Groq em
  17/06/2026, com desligamento em 16/08/2026. Migrado para
  openai/gpt-oss-120b (recomendação oficial da Groq), que também suporta
  tool calling nativo — necessário para a busca na web.
  Ref: https://console.groq.com/docs/deprecations
"""

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

import json
import os
from groq import Groq

# ── Cliente ────────────────────────────────────────────────────────────────────

_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

MODEL       = "openai/gpt-oss-120b"   # migrado de llama-3.3-70b-versatile (deprecado, shutdown 16/08/26)
TEMP_CHAT   = 0.75   # conversa principal — criativa mas coerente
TEMP_UTIL   = 0.20   # tarefas internas — determinística
MAX_TOKENS  = 600
MAX_TOOL_ROUNDS = 3   # limite de idas-e-voltas de tool call, evita loop


# ── Chamada interna simples ────────────────────────────────────────────────────

def gerar_resposta(prompt: str, temperatura: float = TEMP_UTIL) -> str:
    """
    Chamada single-turn para tarefas internas do mind.py
    (checar importância, extrair resumo de memória, etc.).
    Não usa contexto de sistema — apenas um único turno user/assistant.
    """
    try:
        resp = _client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperatura,
            max_tokens=MAX_TOKENS,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] gerar_resposta — erro: {e}")
        return ""


# ── Chamada de chat simples (sem tools) ─────────────────────────────────────────

def gerar_chat(system: str, messages: list[dict]) -> str:
    """
    Chamada multi-turn com system prompt separado — formato nativo da API de chat.
    Sem tool calling — usada onde não precisamos de busca (ex.: saudação).

    Parâmetros:
      system   → string com a personalidade/contexto da Neura
      messages → lista de dicts [{"role": "user"|"assistant", "content": "..."}]
                 O último elemento deve ser a mensagem atual do Mestre.

    Retorna a resposta da Neura como string.
    """
    if not messages:
        return ""

    payload = [{"role": "system", "content": system}] + messages

    try:
        resp = _client.chat.completions.create(
            model=MODEL,
            messages=payload,
            temperature=TEMP_CHAT,
            max_tokens=MAX_TOKENS,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] gerar_chat — erro: {e}")
        return "Algo deu errado, Mestre. Tenta de novo."


# ── Chamada de chat com tool calling (busca na web) ─────────────────────────────

def gerar_chat_com_tools(
    system: str,
    messages: list[dict],
    tools: list[dict],
    executores: dict,
) -> str:
    """
    Chamada multi-turn com suporte a tool calling nativo da API.

    A Neura recebe a definição das ferramentas disponíveis (ex.: buscar_web)
    e decide por conta própria se precisa chamá-las, com base na pergunta
    do Mestre. Quando ela pede uma tool call, este código executa a função
    Python correspondente e devolve o resultado pra ela formular a resposta
    final — tudo isso de forma transparente pra quem chamou esta função.

    Parâmetros:
      system     → personalidade/contexto da Neura
      messages   → histórico (último elemento = mensagem atual do Mestre)
      tools      → lista de definições de ferramentas (formato OpenAI-style)
      executores → dict {nome_da_tool: função python que recebe **kwargs
                   e retorna uma string com o resultado}

    Retorna a resposta final da Neura, já com os resultados das tools
    (se usadas) incorporados na fala.
    """
    if not messages:
        return ""

    payload = [{"role": "system", "content": system}] + list(messages)

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            resp = _client.chat.completions.create(
                model=MODEL,
                messages=payload,
                temperature=TEMP_CHAT,
                max_tokens=MAX_TOKENS,
                tools=tools,
                tool_choice="auto",
            )
        except Exception as e:
            print(f"[LLM] gerar_chat_com_tools — erro: {e}")
            return "Algo deu errado, Mestre. Tenta de novo."

        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)

        # Sem tool call → resposta final, pode retornar
        if not tool_calls:
            return (msg.content or "").strip()

        # Registra a "intenção" da Neura de chamar a(s) tool(s) no histórico
        payload.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        })

        # Executa cada tool call solicitada e devolve o resultado
        for tc in tool_calls:
            nome = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            executor = executores.get(nome)
            if executor:
                try:
                    resultado = executor(**args)
                except Exception as e:
                    resultado = f"Erro ao executar {nome}: {e}"
            else:
                resultado = f"Ferramenta '{nome}' não implementada."

            payload.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": nome,
                "content": str(resultado),
            })

    # Passou do limite de rounds sem resposta final — força uma última
    # chamada sem tools pra garantir que algo seja retornado ao Mestre
    try:
        resp = _client.chat.completions.create(
            model=MODEL,
            messages=payload,
            temperature=TEMP_CHAT,
            max_tokens=MAX_TOKENS,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] gerar_chat_com_tools — erro final: {e}")
        return "Algo deu errado, Mestre. Tenta de novo."