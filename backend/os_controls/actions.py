"""
os_control.py — Neura v2.0.0
Módulo de controle do sistema operacional.

Todas as operações de arquivo são restritas a self.base_path.
Qualquer tentativa de acesso fora dessa pasta é bloqueada.
"""

import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime


class OSControl:

    def __init__(self):
        # Pasta raiz de trabalho — a IA nunca opera fora daqui
        self.base_path = os.path.expanduser("~/Documentos/Projetos/Pessoais")

        # Garante que a pasta existe ao iniciar
        os.makedirs(self.base_path, exist_ok=True)

    # ══════════════════════════════════════════════════════════════
    # SEGURANÇA — validação obrigatória para todos os métodos
    # ══════════════════════════════════════════════════════════════

    def _validar_caminho(self, caminho_relativo: str) -> str | None:
        """
        Resolve o caminho completo e verifica se está dentro de base_path.
        Retorna o caminho absoluto seguro, ou None se for inválido.

        Bloqueia ataques de path traversal como '../../etc/passwd'.

        Sanitização defensiva (CORRIGIDO):
        O modelo às vezes manda o caminho com barra inicial — ex: '/IAs & Chatbots' —
        pensando nele como "absoluto a partir da raiz do projeto". Sem tratar isso,
        os.path.join(base_path, '/sub') IGNORA base_path inteiro (comportamento
        documentado do próprio os.path.join quando o segundo argumento começa com
        '/'), o caminho final "vaza" pra fora da sandbox e cai no bloqueio de
        path traversal por engano — mesmo sem nenhuma intenção maliciosa.
        Aspas residuais e espaços nas pontas (artefatos comuns de tool calling)
        também são limpos aqui, sem afrouxar a trava de segurança abaixo.
        """
        if caminho_relativo is None:
            caminho_relativo = ""

        caminho_relativo = caminho_relativo.strip().strip("'\"")
        caminho_relativo = caminho_relativo.lstrip("/\\")  # remove barra(s) inicial(is)

        if not caminho_relativo:
            caminho_relativo = "."

        caminho_completo = os.path.realpath(
            os.path.join(self.base_path, caminho_relativo)
        )
        base_real = os.path.realpath(self.base_path)

        if caminho_completo != base_real and not caminho_completo.startswith(base_real + os.sep):
            return None  # Tentativa de sair da pasta base!

        return caminho_completo

    # ══════════════════════════════════════════════════════════════
    # LEITURA E LISTAGEM
    # ══════════════════════════════════════════════════════════════

    def listar_arquivos(self, diretorio: str = "") -> str:
        """
        Lista o conteúdo de um diretório dentro de base_path.
        Retorna uma string formatada em árvore (pastas e arquivos).
        """
        caminho_alvo = self._validar_caminho(diretorio)
        if not caminho_alvo or not os.path.isdir(caminho_alvo):
            return f"// Erro: Diretório inválido ou acesso negado: '{diretorio}'"

        try:
            itens = os.listdir(caminho_alvo)
            if not itens:
                return f"// O diretório '{diretorio or 'raiz'}' está vazio."

            # ── ADICIONADO: Ajuste na string para evitar que a IA invente subpastas "base" ──
            nome_exibicao = f"raiz do diretório de projetos" if not diretorio else f"subpasta '{diretorio}'"
            linhas = [f"// Listagem da {nome_exibicao}:"]

            # Separa pastas de arquivos para organizar a exibição
            pastas = []
            arquivos = []

            for item in itens:
                if item.startswith('.'):  # ignora arquivos ocultos de sistema
                    continue
                caminho_item = os.path.join(caminho_alvo, item)
                if os.path.isdir(caminho_item):
                    pastas.append(item)
                else:
                    arquivos.append(item)

            pastas.sort()
            arquivos.sort()

            for p in pastas:
                linhas.append(f"  📁 {p}")

            for a in arquivos:
                caminho_arq = os.path.join(caminho_alvo, a)
                tamanho = os.path.getsize(caminho_arq)
                
                if tamanho < 1024:
                    tam_str = f"{tamanho} bytes"
                elif tamanho < 1024 * 1024:
                    tam_str = f"{tamanho / 1024:.1f} KB"
                else:
                    tam_str = f"{tamanho / (1024 * 1024):.1f} MB"

                linhas.append(f"  📄 {a}  ({tam_str})")

            return "\n".join(linhas)

        except Exception as e:
            return f"// Erro ao listar diretório: {str(e)}"

    def ler_arquivo(self, caminho: str) -> str:
        """
        Lê todo o conteúdo de um arquivo de texto dentro de base_path.
        """
        caminho_alvo = self._validar_caminho(caminho)
        if not caminho_alvo or not os.path.isfile(caminho_alvo):
            return f"// Erro: Arquivo inválido ou não encontrado: '{caminho}'"

        try:
            with open(caminho_alvo, 'r', encoding='utf-8', errors='replace') as f:
                conteudo = f.read()
            return conteudo
        except Exception as e:
            return f"// Erro ao ler arquivo: {str(e)}"

    # ══════════════════════════════════════════════════════════════
    # CRIAÇÃO E MANIPULAÇÃO
    # ══════════════════════════════════════════════════════════════

    def criar_arquivo(self, caminho: str, conteudo: str) -> str:
        """
        Cria um arquivo com o conteúdo especificado.
        Se as pastas intermediárias não existirem, elas são criadas.
        Falha se o arquivo já existir.
        """
        caminho_alvo = self._validar_caminho(caminho)
        if not caminho_alvo:
            return f"// Erro: Caminho inválido ou proibido: '{caminho}'"

        if os.path.exists(caminho_alvo):
            return f"// Erro: O arquivo '{caminho}' já existe. Use editar_arquivo para sobrescrever."

        try:
            # Garante que a subpasta existe antes de criar o arquivo
            os.makedirs(os.path.dirname(caminho_alvo), exist_ok=True)

            with open(caminho_alvo, 'w', encoding='utf-8') as f:
                f.write(conteudo)

            n_linhas = len(conteudo.splitlines())
            return f"// Sucesso: arquivo criado em '{caminho}' ({n_linhas} linhas)."
        except Exception as e:
            return f"// Erro ao criar arquivo: {str(e)}"

    def criar_diretorio(self, caminho: str) -> str:
        """
        Cria uma nova pasta (e subpastas se necessário) dentro de base_path.
        """
        caminho_alvo = self._validar_caminho(caminho)
        if not caminho_alvo:
            return f"// Erro: Caminho inválido ou proibido: '{caminho}'"

        try:
            os.makedirs(caminho_alvo, exist_ok=True)
            return f"// Sucesso: diretório criado em '{caminho}'."
        except Exception as e:
            return f"// Erro ao criar diretório: {str(e)}"

    # ══════════════════════════════════════════════════════════════
    # EDIÇÃO DE CONTEÚDO (Com Backups de Segurança)
    # ══════════════════════════════════════════════════════════════

    def _criar_backup(self, caminho_absoluto: str) -> None:
        """Método interno para gerar backup .bak antes de alterações destrutivas."""
        if os.path.isfile(caminho_absoluto):
            shutil.copy2(caminho_absoluto, caminho_absoluto + ".bak")

    def editar_arquivo(self, caminho: str, novo_conteudo: str) -> str:
        """
        Sobrescreve COMPLETAMENTE um arquivo existente.
        Cria um backup (.bak) automático antes.
        """
        caminho_alvo = self._validar_caminho(caminho)
        if not caminho_alvo or not os.path.isfile(caminho_alvo):
            return f"// Erro: Arquivo inválido ou não encontrado: '{caminho}'"

        try:
            self._criar_backup(caminho_alvo)

            with open(caminho_alvo, 'w', encoding='utf-8') as f:
                f.write(novo_conteudo)

            n_linhas = len(novo_conteudo.splitlines())
            return f"// Sucesso: arquivo '{caminho}' sobrescrito ({n_linhas} linhas). Backup .bak gerado."
        except Exception as e:
            return f"// Erro ao editar arquivo: {str(e)}"

    def editar_trecho(self, caminho: str, texto_antigo: str, texto_novo: str) -> str:
        """
        Substituição precisa: localiza um bloco exato de texto e altera por outro.
        Garante que modificações pequenas não corrompam o resto do arquivo.
        """
        caminho_alvo = self._validar_caminho(caminho)
        if not caminho_alvo or not os.path.isfile(caminho_alvo):
            return f"// Erro: Arquivo inválido ou não encontrado: '{caminho}'"

        try:
            with open(caminho_alvo, 'r', encoding='utf-8') as f:
                conteudo_atual = f.read()

            if texto_antigo not in conteudo_atual:
                return "// Erro: O trecho antigo especificado não foi encontrado no arquivo de forma idêntica."

            self._criar_backup(caminho_alvo)

            # Faz a substituição cirúrgica apenas da primeira ocorrência
            novo_conteudo = conteudo_atual.replace(texto_antigo, texto_novo, 1)

            with open(caminho_alvo, 'w', encoding='utf-8') as f:
                f.write(novo_conteudo)

            return f"// Sucesso: trecho de '{caminho}' editado cirurgicamente. Backup .bak gerado."
        except Exception as e:
            return f"// Erro ao editar trecho: {str(e)}"

    def adicionar_conteudo(self, caminho: str, conteudo: str, posicao: str = "fim") -> str:
        """
        Adiciona conteúdo no 'inicio' ou no 'fim' (padrão) de um arquivo existente.
        """
        caminho_alvo = self._validar_caminho(caminho)
        if not caminho_alvo or not os.path.isfile(caminho_alvo):
            return f"// Erro: Arquivo inválido ou não encontrado: '{caminho}'"

        try:
            self._criar_backup(caminho_alvo)

            if posicao == "inicio":
                with open(caminho_alvo, 'r', encoding='utf-8') as f:
                    atual = f.read()
                with open(caminho_alvo, 'w', encoding='utf-8') as f:
                    f.write(conteudo + "\n" + atual)
            else:
                with open(caminho_alvo, 'a', encoding='utf-8') as f:
                    f.write("\n" + conteudo)

            return f"// Sucesso: conteúdo anexado ao {posicao} de '{caminho}'."
        except Exception as e:
            return f"// Erro ao adicionar conteúdo: {str(e)}"

    # ══════════════════════════════════════════════════════════════
    # REMOÇÃO E REORGANIZAÇÃO
    # ══════════════════════════════════════════════════════════════

    def deletar_arquivo(self, caminho: str) -> str:
        """
        Deleta um arquivo movendo-o primeiro para uma pasta segura oculta (.lixeira/).
        """
        caminho_alvo = self._validar_caminho(caminho)
        if not caminho_alvo or not os.path.isfile(caminho_alvo):
            return f"// Erro: Arquivo inválido ou não encontrado: '{caminho}'"

        try:
            pasta_lixeira = os.path.join(self.base_path, ".lixeira")
            os.makedirs(pasta_lixeira, exist_ok=True)

            nome_arquivo = os.path.basename(caminho_alvo)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
            alvo_lixeira = os.path.join(pasta_lixeira, timestamp + nome_arquivo)

            shutil.move(caminho_alvo, alvo_lixeira)
            return f"// Sucesso: '{caminho}' movido para a lixeira interna segura."
        except Exception as e:
            return f"// Erro ao deletar arquivo: {str(e)}"

    def deletar_pasta(self, caminho: str) -> str:
        """
        Remove permanentemente uma pasta e tudo dentro dela. RESTRITO E PERIGOSO.
        """
        caminho_alvo = self._validar_caminho(caminho)
        if not caminho_alvo or not os.path.isdir(caminho_alvo):
            return f"// Erro: Diretório inválido ou não encontrado: '{caminho}'"

        if caminho_alvo == os.path.realpath(self.base_path):
            return "// Erro crítico: Bloqueado tentativa de deletar a pasta raiz de projetos inteira!"

        try:
            shutil.rmtree(caminho_alvo)
            return f"// Sucesso: pasta '{caminho}' e conteúdos apagados permanentemente."
        except Exception as e:
            return f"// Erro ao deletar pasta: {str(e)}"

    def renomear(self, caminho: str, novo_nome: str) -> str:
        """
        Move ou renomeia um arquivo/diretório dentro de base_path.
        """
        origem = self._validar_caminho(caminho)
        destino = self._validar_caminho(novo_nome)

        if not origem or not os.path.exists(origem):
            return f"// Erro: Item de origem inválido: '{caminho}'"
        if not destino:
            return f"// Erro: Caminho de destino proibido ou inválido: '{novo_nome}'"
        if os.path.exists(destino):
            return f"// Erro: O destino '{novo_nome}' já existe."

        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.move(origem, destino)
            return f"// Sucesso: '{caminho}' movido/renomeado para '{novo_nome}'."
        except Exception as e:
            return f"// Erro ao renomear: {str(e)}"

    # ══════════════════════════════════════════════════════════════
    # EXECUÇÃO DE COMANDOS
    # ══════════════════════════════════════════════════════════════

    def executar_comando(self, comando: str, timeout: int = 15) -> str:
        """
        Executa um comando no terminal do Ubuntu.

        O comando roda com o diretório de trabalho em base_path.
        Use para rodar scripts, instalar pacotes, git, etc.

        Parâmetros:
          comando  → string do comando (ex: 'python3 script.py')
          timeout  → segundos máximos de espera (padrão: 15)
        """
        try:
            resultado = subprocess.run(
                comando,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.base_path,          # sempre roda dentro da pasta segura
            )

            saida = resultado.stdout.strip()
            erro  = resultado.stderr.strip()

            if resultado.returncode == 0:
                return saida if saida else "// Comando executado com sucesso (sem saída)."
            else:
                detalhes = erro if erro else saida
                return f"// Erro no comando (código {resultado.returncode}):\n{detalhes}"

        except subprocess.TimeoutExpired:
            return f"// Timeout: o comando excedeu {timeout}s e foi interrompido."
        except Exception as e:
            return f"// Falha crítica ao executar: {str(e)}"