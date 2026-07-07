"""
llm.py — Neura v2.8.0 (DUAL-CLIENT: Groq nuvem + Ollama local)
Interface com dois backends de IA, com roteamento modular por perfil.

Arquitetura de clientes:
  _client_groq  → Groq API (nuvem) — conversa, saudação, didático, segurança
  _client_local → Ollama local     — código/OS (baixa latência), fallback offline

Roteamento por perfil:
  "conversa"    → Groq  openai/gpt-oss-120b     (rápido, fluente, poderoso)
  "didatico"    → Groq  openai/gpt-oss-120b     (mesmo modelo, temperatura menor)
  "seguranca"   → Groq  openai/gpt-oss-120b     (tom defensivo via system prompt)
  "codigo"      → Local qwen2.5-coder:7b         (sem latência de rede, preciso)
  "os"          → Local llama3.2                 (operações de SO, rápido)
  "uncensored"  → Local dolphin-llama3:8b        (opt-in explícito apenas, nunca automático)

Fallback:
  Se Groq falhar (sem internet, rate limit, chave inválida) → Ollama local llama3.2.
  Se Ollama também falhar → mind.py captura e chama _resposta_contingencia().

NOTA SOBRE O PERFIL 'seguranca':
  O perfil usa o mesmo modelo de conversa da Groq. O tom defensivo/educativo
  vem exclusivamente do system prompt montado pelo mind.py — não há modelo
  "uncensored" no pipeline de segurança (esses são propósitos diferentes).

NOTA SOBRE O PERFIL 'uncensored':
  Existe apenas para ser chamado manualmente (perfil="uncensored"). Não é
  incluído em escolher_perfil() — a Neura não decide sozinha usar esse modelo.
  Em máquina sem GPU dedicada, é sensivelmente mais lento que os perfis Groq.
"""

import os
import json
import concurrent.futures
from openai import OpenAI

# Limite de segurança para args e resultados de tools — evita que um
# comando (ex.: cat de um arquivo enorme) estoure o contexto do modelo
# na próxima iteração e degrade a latência ou gere erro 400 da API.
MAX_TOOL_RESULT_CHARS = 6000
MAX_TOOL_ARGS_CHARS   = 20000

# Pool de threads compartilhado para rodar tools pesadas (I/O-bound: leitura
# de arquivo, subprocess, listagem de diretório) em paralelo quando o modelo
# solicita múltiplas tool_calls na mesma iteração, em vez de uma bloquear a
# outra em sequência.
_TOOL_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="neura-tool")

# ══════════════════════════════════════════════════════════════════════════════
# CLIENTES — Groq (nuvem) e Ollama (local)
# ══════════════════════════════════════════════════════════════════════════════

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Cliente Groq — usado para conversa, saudação, didático e segurança
_client_groq = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=_GROQ_API_KEY or "sem-chave",   # placeholder evita crash no import
) if _GROQ_API_KEY else None

# Cliente Ollama — usado para código/OS e como fallback offline
_client_local = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

# Se não houver chave Groq, avisa uma vez no boot (não trava o servidor)
if not _GROQ_API_KEY:
    print("[LLM] ⚠️  GROQ_API_KEY não definida — todas as chamadas usarão Ollama local.")

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
    # Conversa geral, saudação, humor emocional — a "voz" principal da Neura (Groq)
    "conversa": {
        "client":      "groq",
        "model":       "openai/gpt-oss-120b",
        "temperatura": 0.75,
        "max_tokens":  1024,
    },
    # Programação: debug, geração de código, revisão técnica (Ollama local)
    "codigo": {
        "client":      "local",
        "model":       "qwen2.5-coder:7b",
        "temperatura": 0.30,
        "max_tokens":  2048,
    },
    # Operações de SO: listar, ler, criar arquivos (Ollama local, rápido)
    "os": {
        "client":      "local",
        "model":       "llama3.2",
        "temperatura": 0.20,
        "max_tokens":  1024,
    },
    # Cibersegurança — Groq com tom defensivo via system prompt do mind.py
    "seguranca": {
        "client":      "groq",
        "model":       "openai/gpt-oss-120b",
        "temperatura": 0.30,
        "max_tokens":  2048,
    },
    # Didático — explicações passo a passo (Groq, temperatura menor)
    "didatico": {
        "client":      "groq",
        "model":       "openai/gpt-oss-120b",
        "temperatura": 0.55,
        "max_tokens":  1536,
    },
    # ── UNCENSORED — Ollama local, dolphin-llama3:8b ────────────────────────
    # Só é usado se 'perfil="uncensored"' for passado EXPLICITAMENTE por quem
    # chama (mind.py, ou você manualmente). Não entra em escolher_perfil() —
    # a Neura nunca escolhe esse perfil sozinha por heurística de palavras.
    # Em CPU (sem GPU) é lento: espere vários segundos por resposta. Quando a
    # 5060 Ti chegar, isso já roda rápido sem mudar nada aqui, só o driver.
    # Requer: `ollama pull dolphin-llama3:8b`
    "uncensored": {
        "client":      "local",
        "model":       "dolphin-llama3:8b",
        "temperatura": 0.80,
        "max_tokens":  1536,
    },
}

DEFAULT_PERFIL = "conversa"
_FALLBACK_LOCAL = {"client": "local", "model": "llama3.2", "temperatura": 0.7, "max_tokens": 1024}


def _resolver_perfil(perfil: str | None) -> dict:
    """Retorna a config do perfil. Se Groq não estiver disponível, rebaixa para local."""
    cfg = PERFIS.get(perfil or DEFAULT_PERFIL, PERFIS[DEFAULT_PERFIL])
    if cfg["client"] == "groq" and not _client_groq:
        # Sem chave Groq — rebaixa graciosamente para Ollama
        return {**cfg, "client": "local", "model": "llama3.2"}
    return cfg


def _get_client(cfg: dict) -> OpenAI:
    """Retorna o cliente correto baseado na config do perfil."""
    return _client_groq if cfg["client"] == "groq" else _client_local


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
    (checar importância, extrair resumo de memória).
    Tenta o cliente do perfil; se Groq falhar, rebaixa para Ollama local.
    """
    cfg    = _resolver_perfil(perfil)
    client = _get_client(cfg)
    temp   = temperatura if temperatura is not None else cfg["temperatura"]

    try:
        completion = client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=temp,
            max_tokens=cfg["max_tokens"],
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        # Groq falhou — tenta Ollama local como fallback
        if cfg["client"] == "groq":
            print(f"[LLM] Groq falhou em gerar_resposta, tentando local: {e}")
            try:
                completion = _client_local.chat.completions.create(
                    model=_FALLBACK_LOCAL["model"],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temp,
                    max_tokens=_FALLBACK_LOCAL["max_tokens"],
                )
                return (completion.choices[0].message.content or "").strip()
            except Exception as e2:
                print(f"[LLM] Ollama também falhou em gerar_resposta: {e2}")
        else:
            print(f"[LLM] Erro em gerar_resposta (perfil={perfil}): {e}")
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# CONVERSA DIRETA (SEM FERRAMENTAS)
# ══════════════════════════════════════════════════════════════════════════════

def gerar_chat(system_prompt: str, messages: list[dict], perfil: str = DEFAULT_PERFIL) -> str:
    """
    Gera uma resposta simples respeitando o histórico e a persona.
    Tenta o cliente do perfil (Groq ou local); se Groq falhar, rebaixa para Ollama.
    """
    cfg     = _resolver_perfil(perfil)
    client  = _get_client(cfg)
    payload = [{"role": "system", "content": system_prompt}] + messages

    try:
        completion = client.chat.completions.create(
            model=cfg["model"],
            messages=payload,
            temperature=cfg["temperatura"],
            max_tokens=cfg["max_tokens"],
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        if cfg["client"] == "groq":
            print(f"[LLM] Groq falhou em gerar_chat, tentando local: {e}")
            try:
                completion = _client_local.chat.completions.create(
                    model=_FALLBACK_LOCAL["model"],
                    messages=payload,
                    temperature=_FALLBACK_LOCAL["temperatura"],
                    max_tokens=_FALLBACK_LOCAL["max_tokens"],
                )
                return (completion.choices[0].message.content or "").strip()
            except Exception as e2:
                print(f"[LLM] Ollama também falhou em gerar_chat: {e2}")
                raise   # propaga para o try/except do mind.py
        print(f"[LLM] Erro em gerar_chat (perfil={perfil}): {e}")
        raise


# ══════════════════════════════════════════════════════════════════════════════
# LOOP COMPLETO DE TOOL CALLING (CONVERSA + FUNÇÕES OPERACIONAIS)
# ══════════════════════════════════════════════════════════════════════════════

def _executar_tool(tc, executores: dict) -> str:
    """
    Executa um único tool_call de forma segura.
    Garante que o resultado seja sempre uma string limpa — nunca JSON cru
    nem traceback vazando pro chat do Mestre.
    """
    nome = tc.function.name

    # ── Guarda contra payload de argumentos anormalmente grande ─────────────
    raw_args = tc.function.arguments or "{}"
    if len(raw_args) > MAX_TOOL_ARGS_CHARS:
        print(f"[TOOL] ⚠️  Argumentos de '{nome}' excedem {MAX_TOOL_ARGS_CHARS} chars — abortando.")
        return f"// Erro: argumentos de '{nome}' excedem o limite seguro de tamanho."

    # ── Parse dos argumentos ────────────────────────────────────────────────
    try:
        args = json.loads(raw_args)
        if not isinstance(args, dict):
            raise ValueError("Argumentos não são um objeto JSON.")
    except Exception as e:
        print(f"[TOOL] ⚠️  JSON inválido em '{nome}': {e} | raw: {raw_args!r}")
        return f"// Erro: argumentos malformados para '{nome}'. Tente reformular o pedido."

    # ── Ferramenta desconhecida ─────────────────────────────────────────────
    if nome not in executores:
        print(f"[TOOL] ⚠️  Ferramenta '{nome}' não registrada.")
        return f"// Ferramenta '{nome}' não existe. Use apenas as ferramentas disponíveis."

    # ── Execução ────────────────────────────────────────────────────────────
    try:
        resultado = executores[nome](**args)
        # Garante string — resultados None ou não-string são normalizados
        resultado_str = str(resultado) if resultado is not None else "// Operação concluída sem retorno."
    except Exception as e:
        print(f"[TOOL] ⚠️  Erro ao executar '{nome}': {e}")
        resultado_str = f"// Erro ao executar '{nome}': {e}"

    # ── Guarda contra resultado gigante (ex.: cat de arquivo enorme) ────────
    if len(resultado_str) > MAX_TOOL_RESULT_CHARS:
        cortados = len(resultado_str) - MAX_TOOL_RESULT_CHARS
        resultado_str = (
            resultado_str[:MAX_TOOL_RESULT_CHARS]
            + f"\n// [...truncado — {cortados} caracteres a mais omitidos para não estourar o contexto...]"
        )

    print(f"[TOOL] {nome}({_fmt_args(args)}) → {resultado_str[:120]}")
    return resultado_str


def gerar_chat_com_tools(
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    executores: dict,
    perfil: str = DEFAULT_PERFIL,
) -> str:
    """
    Loop iterativo de Tool Calling com roteamento dual Groq/Ollama.

    Fluxo:
      1. Usa o cliente do perfil (Groq para conversa/segurança, local para código/OS).
      2. Se Groq falhar na PRIMEIRA iteração, rebaixa para Ollama e recomeça.
      3. Se o modelo retornar JSON de tool cru no campo 'content' sem tool_calls,
         o parser captura, limpa, e devolve uma mensagem amigável.
      4. Após MAX_TOOL_ITS, força uma chamada final sem tools para fechar a resposta.
    """
    cfg    = _resolver_perfil(perfil)
    client = _get_client(cfg)
    modelo = cfg["model"]
    payload = [{"role": "system", "content": system_prompt}] + messages

    groq_rebaixado = False   # flag para não tentar rebaixar duas vezes

    for iteracao in range(MAX_TOOL_ITS):
        try:
            completion = client.chat.completions.create(
                model=modelo,
                messages=payload,
                tools=tools,
                tool_choice="auto",
                temperature=cfg["temperatura"],
                max_tokens=cfg["max_tokens"],
            )
        except Exception as e:
            # ── Groq caiu: rebaixa uma vez para Ollama local ────────────────
            if cfg["client"] == "groq" and not groq_rebaixado:
                print(f"[LLM] Groq falhou (iter {iteracao}), rebaixando para Ollama: {e}")
                client         = _client_local
                modelo         = _FALLBACK_LOCAL["model"]
                cfg            = {**cfg, "client": "local",
                                  "temperatura": _FALLBACK_LOCAL["temperatura"],
                                  "max_tokens":  _FALLBACK_LOCAL["max_tokens"]}
                groq_rebaixado = True
                continue   # repete a iteração com Ollama
            # Ollama também falhou — propaga para o mind.py tratar
            print(f"[LLM] gerar_chat_com_tools — falha total (iter {iteracao}): {e}")
            raise

        msg_resposta = completion.choices[0].message

        # ── Guarda de JSON cru: modelo às vezes coloca JSON no 'content' ───
        conteudo_bruto = (msg_resposta.content or "").strip()
        if conteudo_bruto and not msg_resposta.tool_calls:
            # Checa se o "texto final" é na verdade um blob JSON de tool call
            try:
                possivel_json = json.loads(conteudo_bruto)
                # Se chegou aqui, o modelo cuspiu JSON — não exibe pro Mestre
                if isinstance(possivel_json, dict) and (
                    "name" in possivel_json or "tool_calls" in possivel_json
                ):
                    print(f"[LLM] ⚠️  JSON cru detectado no content (iter {iteracao}) — descartado.")
                    return "Mestre, tive uma falha no formato da minha resposta. Pode repetir?"
            except (json.JSONDecodeError, TypeError):
                pass   # não é JSON — é texto legítimo, segue normal

        payload.append(msg_resposta)

        # Sem tool_calls → o modelo quer dar uma resposta em texto → finaliza
        if not msg_resposta.tool_calls:
            return conteudo_bruto

        # ── Executa cada ferramenta solicitada (em paralelo quando houver mais de uma) ──
        # Ferramentas operacionais (comando shell, leitura/listagem de arquivo, busca web)
        # são I/O-bound — rodá-las concorrentemente quando o modelo pede várias na mesma
        # rodada evita que uma tool lenta (ex.: os_executar_comando) bloqueie as outras
        # em fila, reduzindo a latência total da rodada de tools.
        tool_calls = msg_resposta.tool_calls
        if len(tool_calls) == 1:
            resultados = [_executar_tool(tool_calls[0], executores)]
        else:
            futures = [_TOOL_POOL.submit(_executar_tool, tc, executores) for tc in tool_calls]
            resultados = [f.result() for f in futures]

        for tc, resultado_str in zip(tool_calls, resultados):
            payload.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      resultado_str,
            })

    # ── Excedeu MAX_TOOL_ITS: força resposta final sem tools ────────────────
    print(f"[LLM] Limite de {MAX_TOOL_ITS} iterações atingido (perfil={perfil}). Forçando resposta final.")

    # Reforço explícito: o histórico está cheio de mensagens no formato de
    # tool call (rodadas anteriores). Mesmo sem 'tools' no payload, o modelo
    # pode tentar repetir esse padrão por inércia e a Groq rejeita a chamada
    # inteira com erro 400 ("Tool choice is none, but model called a tool").
    # Essa instrução extra reduz drasticamente a chance disso acontecer.
    payload_final = payload + [{
        "role": "user",
        "content": (
            "Você atingiu o limite de operações desta rodada. "
            "Responda AGORA apenas em texto puro, resumindo pro Mestre o que "
            "foi feito até aqui. NÃO tente chamar nenhuma função ou ferramenta."
        ),
    }]

    def _resumo_de_emergencia() -> str:
        """
        Último recurso: monta um resumo determinístico a partir das próprias
        tools já executadas no payload, sem depender de nenhum modelo de IA.
        Garante que o Mestre nunca fica sem resposta mesmo se Groq E Ollama
        falharem nessa etapa — o trabalho das tools já foi feito de verdade,
        só a "narração" em texto que não saiu.
        """
        linhas = []
        for msg in payload:
            if isinstance(msg, dict) and msg.get("role") == "tool":
                linhas.append(f"- {msg.get('content', '')[:150]}")
        corpo = "\n".join(linhas) if linhas else "nenhuma ação registrada"
        return (
            "Mestre, completei as operações mas tive uma falha ao gerar o "
            f"resumo em texto. Aqui está o que foi executado:\n{corpo}"
        )

    try:
        resp = client.chat.completions.create(
            model=modelo,
            messages=payload_final,
            temperature=cfg["temperatura"],
            max_tokens=cfg["max_tokens"],
        )
        return (resp.choices[0].message.content or "").strip() or _resumo_de_emergencia()
    except Exception as e:
        print(f"[LLM] Erro na chamada final pós-limite (Groq): {e}")
        # ── Tenta Ollama antes de desistir — essa etapa nunca tentava antes ──
        try:
            resp2 = _client_local.chat.completions.create(
                model=_FALLBACK_LOCAL["model"],
                messages=payload_final,
                temperature=_FALLBACK_LOCAL["temperatura"],
                max_tokens=_FALLBACK_LOCAL["max_tokens"],
            )
            return (resp2.choices[0].message.content or "").strip() or _resumo_de_emergencia()
        except Exception as e2:
            print(f"[LLM] Ollama também falhou na chamada final pós-limite: {e2}")
            # Nunca propaga daqui pra cima — o trabalho das tools já foi feito
            # de verdade, não faz sentido tratar isso como "falha total de IA".
            return _resumo_de_emergencia()


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