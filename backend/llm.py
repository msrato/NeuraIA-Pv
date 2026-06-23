from dotenv import load_dotenv
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

import os
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL  = "llama-3.3-70b-versatile"


def gerar_resposta(prompt: str) -> str:
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.75,
            max_tokens=600,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"ERRO GROQ: {e}")
        return "Algo deu errado. Tenta de novo."