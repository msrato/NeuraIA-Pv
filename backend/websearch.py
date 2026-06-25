"""
websearch.py — Neura v2.5.0
Busca na web em tempo real, via Tavily API.

Usado como tool call pela Neura (ver TOOLS em mind.py) — ela mesma decide
quando precisa chamar isso, com base na pergunta do Mestre.

Variável de ambiente necessária no .env:
  TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx

Instalação:
  pip install tavily-python
"""

import os
from tavily import TavilyClient

# ── Cliente (singleton lazy) ───────────────────────────────────────────────────

_client: TavilyClient | None = None


def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "TAVILY_API_KEY não definida. Adicione ao arquivo .env"
            )
        _client = TavilyClient(api_key=api_key)
    return _client


# ── Função pública (chamada pelo tool calling em llm.py) ───────────────────────

def buscar_web(query: str, max_resultados: int = 4) -> str:
    """
    Executa uma busca na web e retorna um texto plano resumido,
    pronto para ser injetado de volta no modelo como resultado de tool call.

    Parâmetros:
      query          → termos de busca (definidos pela própria Neura)
      max_resultados → quantidade de resultados a incluir no resumo

    Nunca lança exceção para fora — em caso de erro, retorna uma string
    explicando que a busca falhou, para a Neura conseguir lidar com isso
    na resposta (em vez de quebrar a conversa toda).
    """
    try:
        client = _get_client()
        resp = client.search(
            query=query,
            max_results=max_resultados,
            include_answer=True,
        )

        partes = []

        resposta_direta = resp.get("answer")
        if resposta_direta:
            partes.append(f"Resposta direta: {resposta_direta}")

        for r in resp.get("results", [])[:max_resultados]:
            titulo = r.get("title", "sem título")
            conteudo = (r.get("content") or "")[:400]
            url = r.get("url", "")
            partes.append(f"- {titulo}: {conteudo} (fonte: {url})")

        if not partes:
            return "Nenhum resultado relevante encontrado para essa busca."

        return "\n".join(partes)

    except EnvironmentError as e:
        print(f"[WEBSEARCH] config ausente: {e}")
        return "Busca na web não está configurada (falta TAVILY_API_KEY)."
    except Exception as e:
        print(f"[WEBSEARCH] erro: {e}")
        return "Busca na web indisponível agora. Tenta de novo em um instante."