"""
llm.py — Neura v2.6.0 (LOCAL - OLLAMA)
Interface com a API local do Ollama (Qwen 2.5 7B / LLaMA 3).

Funções públicas:
  gerar_resposta(prompt)                              → chamadas internas simples
  gerar_chat(system, messages)                        → conversa sem ferramentas
  gerar_chat_com_tools(system, messages, tools, exec) → conversa com tool calling
"""

import os
import json
from openai import OpenAI

# ── Cliente Local Ollama (Formato compatível com OpenAI) ───────────────────────

_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"  # O Ollama local não exige chave real, mas precisa de uma string
)

# Recomendado para o i5 de 10ª Gen por ser leve, inteligente e excelente com tools
MODEL        = "llama3.2"  # Qwen 2.5 7B também funciona, mas é mais pesado e lento
TEMP_CHAT    = 0.75   # conversa principal
TEMP_UTIL    = 0.20   # chamadas internas (checar importância, extrair memória)
MAX_TOKENS   = 1024
MAX_TOOL_ITS = 6      # iterações máximas do loop de tool calling


# ══════════════════════════════════════════════════════════════════════════════
# CHAMADA INTERNA SIMPLES
# ══════════════════════════════════════════════════════════════════════════════

def gerar_resposta(prompt: str, temperatura: float = TEMP_UTIL) -> str:
    """
    Single-turn sem sistema — para tarefas internas do mind.py
    (checar importância, extrair resumo de memória).
    """
    try:
        completion = _client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperatura,
            max_tokens=MAX_TOKENS,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[LLM] Erro em gerar_resposta: {e}")
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# CONVERSA DIRETA (SEM FERRAMENTAS)
# ══════════════════════════════════════════════════════════════════════════════

def gerar_chat(system_prompt: str, messages: list[dict]) -> str:
    """
    Gera uma resposta simples respeitando o histórico e a persona.
    """
    payload = [{"role": "system", "content": system_prompt}] + messages

    try:
        completion = _client.chat.completions.create(
            model=MODEL,
            messages=payload,
            temperature=TEMP_CHAT,
            max_tokens=MAX_TOKENS,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[LLM] Erro em gerar_chat: {e}")
        return "Mestre, meu cérebro local deu um pequeno estalo. Pode repetir?"


# ══════════════════════════════════════════════════════════════════════════════
# LOOP COMPLETO DE TOOL CALLING (CONVERSA + FUNÇÕES OPERACIONAIS)
# ══════════════════════════════════════════════════════════════════════════════

def gerar_chat_com_tools(system_prompt: str, messages: list[dict], tools: list[dict], executores: dict) -> str:
    """
    Loop iterativo de Tool Calling. Executa as funções em Python do os_control e devolve
    os resultados ao modelo local até que ele decida gerar um texto final para o Mestre.
    """
    payload = [{"role": "system", "content": system_prompt}] + messages

    for iteracao in range(MAX_TOOL_ITS):
        try:
            # Chamada da API Local
            completion = _client.chat.completions.create(
                model=MODEL,
                messages=payload,
                tools=tools,
                tool_choice="auto",
                temperature=TEMP_CHAT,
                max_tokens=MAX_TOKENS,
            )
        except Exception as e:
            print(f"[LLM] gerar_chat_com_tools — erro na API local (iter {iteracao}): {e}")
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
    print(f"[LLM] Limite de {MAX_TOOL_ITS} iterações atingido. Forçando resposta final.")
    try:
        resp = _client.chat.completions.create(
            model=MODEL,
            messages=payload,
            temperature=TEMP_CHAT,
            max_tokens=MAX_TOKENS,
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