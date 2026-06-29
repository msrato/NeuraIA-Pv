import os
import sys
from dotenv import load_dotenv
from gtts import gTTS

load_dotenv()

# Caminho ABSOLUTO garantido para o arquivo de áudio na raiz do seu projeto
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # backend/tools
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..")) # NeuraPv-v2.5.0
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "output.mp3")

def speak(text):
    """Motor de Voz Oficial da Neura usando gTTS (Português do Brasil)"""
    if not text:
        return
        
    try:
        print(f"[NEURA-VOICE] Sintetizando: \"{text}\"")
        
        # Configura para o Português brasileiro
        tts = gTTS(text=text, lang='pt', tld='com.br')
        tts.save(OUTPUT_PATH)
        
        # Executa o mpg123 usando o caminho absoluto com aspas para evitar problemas com espaços no diretório
        os.system(f'mpg123 "{OUTPUT_PATH}" > /dev/null 2>&1')
        return True
    except Exception as e:
        print(f"[NEURA-VOICE] Erro ao reproduzir áudio: {e}")
        return False

if __name__ == "__main__":
    print("Iniciando Sistema de Voz da Neura...")
    speak("Sistema online. Interface de áudio inicializada com sucesso em português.")