import os
import re
import soundfile as sf
from kokoro_onnx import Kokoro
from gtts import gTTS

# ---------------------------------------------------------------------------
# LIMPEZA DE TEXTO PARA VOZ
# ---------------------------------------------------------------------------
# O texto que chega aqui é o MESMO exibido no chat — com Markdown (**negrito**)
# e emojis. Nem Kokoro nem gTTS entendem essas marcações; eles tentam
# pronunciar os caracteres literalmente ("asterisco asterisco..."). Essa
# limpeza vale SÓ para a fala — o texto original continua intacto no chat
# e no banco de dados.

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"   # símbolos, pictogramas, emojis diversos
    "\U00002600-\U000027BF"   # símbolos diversos + dingbats
    "\U0001F1E6-\U0001F1FF"   # bandeiras (letras regionais)
    "\U00002190-\U000021FF"   # setas
    "\U00002B00-\U00002BFF"   # símbolos diversos adicionais
    "\U0000FE0F"              # seletor de variação (torna emoji "colorido")
    "]+",
    flags=re.UNICODE,
)

# Remove marcadores de Markdown comuns: **negrito**, *itálico*, `código`, # títulos
_MARKDOWN_PATTERN = re.compile(r'(\*\*|\*|__|`{1,3}|#{1,6}\s?)')


def _limpar_para_voz(texto: str) -> str:
    """Remove Markdown e emojis antes de enviar o texto para síntese de voz."""
    if not texto:
        return texto
    limpo = _MARKDOWN_PATTERN.sub('', texto)
    limpo = _EMOJI_PATTERN.sub('', limpo)
    limpo = re.sub(r'\s+', ' ', limpo).strip()
    return limpo

# ---------------------------------------------------------------------------
# GERENCIADOR DE MODO DE VOZ
# ---------------------------------------------------------------------------

class SpeechMode:
    MUDO    = "MUDO"     # Silêncio total — nenhum motor é acionado
    AUTO    = "AUTO"     # Fala automática a cada resposta gerada
    COMMAND = "COMMAND"  # Fala apenas sob demanda (clique / chamada explícita)

class VoiceManager:
    def __init__(self, initial_mode: str = SpeechMode.AUTO):
        self._mode = initial_mode

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str):
        """Altera o modo de voz em tempo de execução."""
        if mode not in (SpeechMode.MUDO, SpeechMode.AUTO, SpeechMode.COMMAND):
            raise ValueError(
                f"[NEURA-VOICE] Modo inválido: '{mode}'. "
                f"Use SpeechMode.MUDO, .AUTO ou .COMMAND."
            )
        self._mode = mode
        print(f"[NEURA-VOICE] Modo alterado para: {self._mode}")

    def is_muted(self) -> bool:
        return self._mode == SpeechMode.MUDO

# Instância global — importada pelos demais módulos do projeto
voice_manager = VoiceManager(initial_mode=SpeechMode.AUTO)

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO DE CAMINHOS E MODELO
# ---------------------------------------------------------------------------

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH  = os.path.abspath(os.path.join(BASE_DIR, "kokoro_model", "onnx", "kokoro-v1.0.int8.onnx"))
VOICES_PATH = os.path.abspath(os.path.join(BASE_DIR, "kokoro_model", "onnx", "voices-v1.0.bin"))
OUTPUT_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "output.mp3"))
KOKORO_WAV_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "kokoro_output.wav"))

# Inicialização segura do Kokoro-ONNX
try:
    kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
except Exception as e:
    print(f"[NEURA-VOICE] Aviso: Kokoro local não pôde ser iniciado ({e}). Usando gTTS.")
    kokoro = None

# ---------------------------------------------------------------------------
# MOTORES DE SÍNTESE (baixo nível — use neura_talk() de fora daqui)
# ---------------------------------------------------------------------------

def speak_kokoro(text: str) -> bool:
    """Motor principal — Kokoro-ONNX local (português-BR)."""
    if not text or not kokoro:
        return False

    if voice_manager.is_muted():
        print(f"[NEURA-VOICE] (MUDO) {text}")
        return True  # não é falha, não dispara fallback

    try:
        print(f"[NEURA-KOKORO] Sintetizando localmente: \"{text}\"")
        samples, sample_rate = kokoro.create(text, voice="pf_dora", speed=1.0, lang="pt-br")

        # IMPORTANTE: nunca usar sd.play()/sd.wait() aqui — essas chamadas
        # acessam o ALSA DIRETO DE DENTRO do processo Flask. Se o dispositivo
        # de áudio não abrir (mesmo problema de sempre), a chamada pode ficar
        # travada PARA SEMPRE, prendendo a requisição /chat inteira sem erro
        # nenhum aparecer no log. Por isso: escreve em .wav e toca via
        # subprocesso isolado (paplay, nativo do Pulse/PipeWire) com timeout
        # de segurança — trava no máximo 10s, nunca mais que isso.
        sf.write(KOKORO_WAV_PATH, samples, sample_rate)
        retorno = os.system(f'timeout 10 paplay "{KOKORO_WAV_PATH}" > /dev/null 2>&1')

        if retorno != 0:
            exit_code = os.WEXITSTATUS(retorno) if os.WIFEXITED(retorno) else retorno
            print(
                f"[NEURA-KOKORO] ⚠️ paplay falhou ou expirou o timeout de 10s "
                f"(exit={exit_code}). Alternando para gTTS..."
            )
            return False

        return True
    except Exception as e:
        print(f"[NEURA-KOKORO] Falha na síntese local ({type(e).__name__}): {e}. Alternando para gTTS...")
        return False


def speak(text: str) -> bool:
    """
    Motor de backup — gTTS em nuvem (português-BR).
    Otimizado para evitar conflito de barramento de áudio (SIGSEGV) no Ubuntu.
    """
    if not text:
        return False

    if voice_manager.is_muted():
        print(f"[NEURA-VOICE] (MUDO) {text}")
        return True

    try:
        print(f"[NEURA-GTTS] Sintetizando via nuvem: \"{text}\"")
        tts = gTTS(text=text, lang='pt', tld='com.br')
        tts.save(OUTPUT_PATH)

        # Correção Crítica de Áudio: força o mpg123 a usar o PulseAudio/PipeWire
        # (compartilhado), nunca o ALSA direto (modo exclusivo → SIGSEGV em
        # snd_pcm_hw_open() já confirmado em produção).
        retorno = os.system(f'mpg123 -o pulse -q "{OUTPUT_PATH}" > /dev/null 2>&1')

        if retorno != 0:
            exit_code = os.WEXITSTATUS(retorno) if os.WIFEXITED(retorno) else retorno
            print(
                f"[NEURA-VOICE] ⚠️ mpg123 -o pulse falhou (exit={exit_code}). "
                f"NÃO tentando fallback via ALSA direto — foi exatamente essa "
                f"rota sem proteção que causou o SIGSEGV em snd_pcm_hw_open() "
                f"anteriormente. Áudio omitido nesta resposta.\n"
                f"[NEURA-VOICE] Diagnóstico: rode 'mpg123 -o help' pra confirmar "
                f"se o módulo 'pulse' está compilado nesse binário, e 'pactl info' "
                f"pra confirmar se o servidor Pulse/PipeWire está acessível a "
                f"partir deste processo (pode faltar PULSE_SERVER/XDG_RUNTIME_DIR "
                f"se o server.py subiu via autostart fora da sessão gráfica)."
            )
            return False

        return True
    except Exception as e:
        print(f"[NEURA-VOICE] Erro ao reproduzir áudio: {e}")
        return False

# ---------------------------------------------------------------------------
# FUNÇÃO PRINCIPAL — ponto de entrada para toda a síntese da Neura
# ---------------------------------------------------------------------------

def neura_talk(text: str, force_command: bool = False) -> bool:
    """
    Gerencia a decisão de falar com base no modo atual do voice_manager.
    """
    if not text:
        return False

    # Limpa Markdown/emoji ANTES de decidir o modo — o texto original (para
    # chat/histórico) não é afetado, isso é uma cópia só para a fala.
    text = _limpar_para_voz(text)
    if not text:
        return False   # sobrou só markdown/emoji, nada pra falar de fato

    mode = voice_manager.mode

    # ── MUDO: silêncio total ────────────────────────────────────────────────
    if mode == SpeechMode.MUDO:
        print(f"[NEURA-VOICE] (MUDO) {text}")
        return True

    # ── AUTO: fala sempre que chamada ───────────────────────────────────────
    if mode == SpeechMode.AUTO:
        print(f"[NEURA-VOICE] (AUTO) Disparando síntese...")
        sucesso = speak_kokoro(text)
        if not sucesso:
            sucesso = speak(text)  # fallback gTTS
        return sucesso

    # ── COMMAND: só fala se a flag vier marcada ──────────────────────────────
    if mode == SpeechMode.COMMAND:
        if force_command:
            print(f"[NEURA-VOICE] (COMMAND) Comando recebido — disparando síntese...")
            sucesso = speak_kokoro(text)
            if not sucesso:
                sucesso = speak(text)  # fallback gTTS
            return sucesso
        else:
            # silêncio por decisão de modo, não é erro
            print(f"[NEURA-VOICE] (COMMAND) Aguardando comando — texto retido.")
            return False

    return False  # modo desconhecido — não faz nada

# ---------------------------------------------------------------------------
# PONTO DE ENTRADA / TESTE
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 50)
    print("  Teste do Sistema de Voz da Neura")
    print("=" * 50)

    # Modo MUDO — sem áudio
    voice_manager.set_mode(SpeechMode.MUDO)
    neura_talk("Isso não deve tocar nenhum som.")

    # Modo COMMAND sem force — retido
    voice_manager.set_mode(SpeechMode.COMMAND)
    neura_talk("Isso também não toca — aguarda comando.")

    # Modo COMMAND com force — toca
    neura_talk("Command confirmed. Playing now.", force_command=True)

    # Modo AUTO — toca automaticamente
    voice_manager.set_mode(SpeechMode.AUTO)
    neura_talk("System online. Neural interface fully initialized.")