import paho.mqtt.client as mqtt
import threading
import sys
import os
import time
import termios
import tty
import select
from datetime import datetime

BROKER = "test.mosquitto.org"
PORTA = 1883
TOPICO_BASE = "srm/board/"

# ===== PASTA DE HISTÓRICO =====
PASTA_SRM = os.path.expanduser("~/.srm")
PASTA_HIST = os.path.join(PASTA_SRM, "historico")
os.makedirs(PASTA_HIST, exist_ok=True)


# ===== CORES ANSI =====
class Cor:
    RESET = "\033[0m"
    NEG = "\033[1m"
    VERDE = "\033[92m"
    CIANO = "\033[96m"
    AMARELO = "\033[93m"
    VERMELHO = "\033[91m"
    ROXO = "\033[95m"
    AZUL = "\033[94m"
    CINZA = "\033[90m"


# ===== BOARDS FIXAS =====
BOARDS = {
    "1": "Goon",
    "2": "Anime",
    "3": "Futebol",
    "4": "Random",
    "5": "Resenha",
    "6": "Games",
}

COR_BOARD = {
    "Goon": Cor.ROXO,
    "Anime": Cor.CIANO,
    "Futebol": Cor.VERDE,
    "Random": Cor.AMARELO,
    "Resenha": Cor.AZUL,
    "Games": Cor.VERMELHO,
}


# =========================================================
# ENTRADA DE TERMINAL
# =========================================================

class EntradaTerminal:
    """
    Entrada de texto própria para terminal.

    Diferente de input(), permite que mensagens recebidas
    pelo MQTT sejam exibidas sem destruir o texto que
    o usuário já estava digitando.
    """

    def __init__(self):
        self.lock = threading.RLock()

        self.texto = ""
        self.cursor = 0

        self.ativo = False
        self.prefixo = "> "

        self.fd = sys.stdin.fileno()
        self.config_original = None

    def iniciar(self, prefixo="> "):
        self.prefixo = prefixo
        self.texto = ""
        self.cursor = 0
        self.ativo = True

        self.config_original = termios.tcgetattr(self.fd)

        tty.setraw(self.fd)

        sys.stdout.write(
            Cor.AMARELO +
            self.prefixo +
            Cor.RESET
        )
        sys.stdout.flush()

    def restaurar(self):
        if self.config_original is not None:
            try:
                termios.tcsetattr(
                    self.fd,
                    termios.TCSADRAIN,
                    self.config_original
                )
            except Exception:
                pass

        self.config_original = None
        self.ativo = False

    def redesenhar(self):
        """
        Redesenha a linha atual.
        """

        with self.lock:

            sys.stdout.write("\r\033[K")

            sys.stdout.write(
                Cor.AMARELO +
                self.prefixo +
                Cor.RESET
            )

            sys.stdout.write(self.texto)

            # Move o cursor para a posição correta.
            distancia = len(self.texto) - self.cursor

            if distancia > 0:
                sys.stdout.write(
                    f"\033[{distancia}D"
                )

            sys.stdout.flush()

    def imprimir_mensagem(self, mensagem):
        """
        Imprime algo sem destruir o texto que está sendo digitado.
        """

        with self.lock:

            if not self.ativo:
                print(mensagem)
                return

            # Vai para o começo e limpa a linha atual.
            sys.stdout.write("\r\033[K")

            # Imprime a mensagem recebida.
            sys.stdout.write(mensagem)

            # Nova linha.
            sys.stdout.write("\n")

            # Restaura o prompt e o texto digitado.
            sys.stdout.write(
                Cor.AMARELO +
                self.prefixo +
                Cor.RESET
            )

            sys.stdout.write(self.texto)

            distancia = len(self.texto) - self.cursor

            if distancia > 0:
                sys.stdout.write(
                    f"\033[{distancia}D"
                )

            sys.stdout.flush()

    def ler(self):
        """
        Lê uma linha manualmente.
        """

        self.texto = ""
        self.cursor = 0

        while self.ativo:

            rlist, _, _ = select.select(
                [self.fd],
                [],
                [],
                0.1
            )

            if not rlist:
                continue

            try:
                caractere = os.read(
                    self.fd,
                    1
                ).decode(
                    "utf-8",
                    errors="ignore"
                )

            except Exception:
                break

            if not caractere:
                continue

            # ENTER
            if caractere in ("\r", "\n"):

                with self.lock:

                    resultado = self.texto

                    self.texto = ""
                    self.cursor = 0

                    sys.stdout.write("\r\033[K")
                    sys.stdout.write("\n")
                    sys.stdout.flush()

                return resultado

            # CTRL+C
            if caractere == "\x03":

                with self.lock:
                    self.texto = ""
                    self.cursor = 0

                    sys.stdout.write(
                        "^C\n"
                    )

                    sys.stdout.flush()

                raise KeyboardInterrupt

            # CTRL+D
            if caractere == "\x04":

                if not self.texto:
                    raise EOFError

                continue

            # BACKSPACE
            if caractere in ("\x08", "\x7f"):

                if self.cursor > 0:

                    with self.lock:

                        self.texto = (
                            self.texto[:self.cursor - 1]
                            + self.texto[self.cursor:]
                        )

                        self.cursor -= 1

                        self.redesenhar()

                continue

            # ESC
            if caractere == "\x1b":

                # Tenta ler sequência de teclas.
                sequencia = ""

                while True:

                    rlist, _, _ = select.select(
                        [self.fd],
                        [],
                        [],
                        0.01
                    )

                    if not rlist:
                        break

                    c = os.read(
                        self.fd,
                        1
                    ).decode(
                        "utf-8",
                        errors="ignore"
                    )

                    sequencia += c

                    if len(sequencia) >= 2:
                        break

                # SETA ESQUERDA
                if sequencia == "[D":

                    if self.cursor > 0:
                        self.cursor -= 1
                        self.redesenhar()

                # SETA DIREITA
                elif sequencia == "[C":

                    if self.cursor < len(self.texto):
                        self.cursor += 1
                        self.redesenhar()

                # HOME
                elif sequencia in ("[H", "[1~"):

                    self.cursor = 0
                    self.redesenhar()

                # END
                elif sequencia in ("[F", "[4~"):

                    self.cursor = len(self.texto)
                    self.redesenhar()

                continue

            # TAB
            if caractere == "\t":

                with self.lock:

                    self.texto = (
                        self.texto[:self.cursor]
                        + "    "
                        + self.texto[self.cursor:]
                    )

                    self.cursor += 4

                    self.redesenhar()

                continue

            # Caracteres normais
            if ord(caractere) >= 32:

                with self.lock:

                    self.texto = (
                        self.texto[:self.cursor]
                        + caractere
                        + self.texto[self.cursor:]
                    )

                    self.cursor += len(caractere)

                    self.redesenhar()

        return self.texto


# Entrada global
entrada_terminal = EntradaTerminal()


# ===== FUNÇÕES GERAIS =====

def limpar_tela():
    os.system("clear")


def banner():
    print(
        Cor.CIANO
        + Cor.NEG
        + r"""
   ███████╗██████╗ ███╗   ███╗
   ██╔════╝██╔══██╗████╗ ████║
   ███████╗██████╔╝██╔████╔██║
   ╚════██║██╔══██╗██║╚██╔╝██║
   ███████║██║  ██║██║ ╚═╝ ██║
   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝
"""
        + Cor.RESET
    )

    print(
        Cor.CINZA
        + "        chat em tempo real\n"
        + Cor.RESET
    )


def caminho_hist(board):
    return os.path.join(
        PASTA_HIST,
        f"{board}.log"
    )


def contar_historico(board):
    caminho = caminho_hist(board)

    if not os.path.exists(caminho):
        return 0

    try:
        with open(
            caminho,
            "r",
            encoding="utf-8"
        ) as f:
            return sum(1 for _ in f)

    except Exception:
        return 0


def mostrar_boards():
    print(Cor.NEG + "╔══════════════════════════════╗")
    print("║      BOARDS DISPONÍVEIS      ║")
    print("╠══════════════════════════════╣" + Cor.RESET)

    for num, nome in BOARDS.items():

        cor = COR_BOARD.get(
            nome,
            Cor.RESET
        )

        qtd = contar_historico(nome)

        contagem = (
            f"{Cor.CINZA}({qtd}){Cor.RESET}"
            if qtd
            else ""
        )

        print(
            f"  {Cor.AMARELO}[{num}]{Cor.RESET}  "
            f"{cor}#{nome:<10}{Cor.RESET} "
            f"{contagem}"
        )

    print(
        Cor.NEG
        + "╚══════════════════════════════╝"
        + Cor.RESET
    )


def salvar_mensagem(board, quem, texto):
    caminho = caminho_hist(board)

    timestamp = datetime.now().strftime(
        "%d/%m %H:%M"
    )

    linha = (
        f"{timestamp}|"
        f"{quem}|"
        f"{texto}\n"
    )

    try:

        with open(
            caminho,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(linha)

    except Exception as e:

        entrada_terminal.imprimir_mensagem(
            f"{Cor.VERMELHO}"
            f"[!] Erro ao salvar histórico: {e}"
            f"{Cor.RESET}"
        )


def carregar_historico(board, quantidade=20):

    caminho = caminho_hist(board)

    if not os.path.exists(caminho):
        return []

    try:

        with open(
            caminho,
            "r",
            encoding="utf-8"
        ) as f:

            linhas = f.readlines()

        return linhas[-quantidade:]

    except Exception:
        return []


def limpar_historico(board):

    caminho = caminho_hist(board)

    if os.path.exists(caminho):

        try:
            os.remove(caminho)
            return True

        except Exception:
            return False

    return False


def formatar_linha_hist(linha, board):

    cor = COR_BOARD.get(
        board,
        Cor.RESET
    )

    partes = linha.strip().split(
        "|",
        2
    )

    if len(partes) != 3:
        return None

    ts, quem, texto = partes

    return (
        f"{Cor.CINZA}{ts}{Cor.RESET} "
        f"{cor}[#{board}]{Cor.RESET} "
        f"{Cor.NEG}{quem}{Cor.RESET}: "
        f"{texto}"
    )


class SRM:

    def __init__(self, apelido):

        self.apelido = apelido
        self.board = None
        self.conectado = False

        self.client = mqtt.Client(
            callback_api_version=
            mqtt.CallbackAPIVersion.VERSION1
        )

        self.client.on_connect = self.ao_conectar
        self.client.on_message = self.ao_receber
        self.client.on_disconnect = self.ao_desconectar

    def ao_conectar(
        self,
        client,
        userdata,
        flags,
        rc
    ):

        if rc == 0:

            self.conectado = True

            entrada_terminal.imprimir_mensagem(
                f"{Cor.VERDE}"
                "[✓] Conectado ao servidor SRM."
                f"{Cor.RESET}"
            )

            entrada_terminal.imprimir_mensagem(
                f"{Cor.CINZA}"
                f"    Bem-vindo, "
                f"{Cor.NEG}{self.apelido}"
                f"{Cor.RESET}"
            )

            if self.board:

                client.subscribe(
                    f"{TOPICO_BASE}{self.board}"
                )

        else:

            self.conectado = False

            entrada_terminal.imprimir_mensagem(
                f"{Cor.VERMELHO}"
                f"[✗] Falha na conexão. "
                f"Código: {rc}"
                f"{Cor.RESET}"
            )

    def ao_desconectar(
        self,
        client,
        userdata,
        rc
    ):

        self.conectado = False

        if rc != 0:

            entrada_terminal.imprimir_mensagem(
                f"{Cor.VERMELHO}"
                "[!] Conexão perdida com o servidor."
                f"{Cor.RESET}"
            )

    def ao_receber(
        self,
        client,
        userdata,
        msg
    ):

        try:

            board_nome = msg.topic.replace(
                TOPICO_BASE,
                "",
                1
            )

            texto = msg.payload.decode(
                "utf-8",
                errors="replace"
            )

            cor = COR_BOARD.get(
                board_nome,
                Cor.RESET
            )

            # Ignora a própria mensagem.
            if texto.startswith(
                f"{self.apelido}:"
            ):
                return

            if ":" in texto:

                quem, msg_texto = texto.split(
                    ":",
                    1
                )

                quem = quem.strip()
                msg_texto = msg_texto.strip()

                salvar_mensagem(
                    board_nome,
                    quem,
                    msg_texto
                )

                exibicao = (
                    f"{cor}[#{board_nome}]{Cor.RESET} "
                    f"{Cor.NEG}{quem}{Cor.RESET}: "
                    f"{msg_texto}"
                )

            else:

                salvar_mensagem(
                    board_nome,
                    "sistema",
                    texto
                )

                exibicao = (
                    f"{cor}[#{board_nome}]{Cor.RESET} "
                    f"{texto}"
                )

            entrada_terminal.imprimir_mensagem(
                exibicao
            )

        except Exception as e:

            entrada_terminal.imprimir_mensagem(
                f"{Cor.VERMELHO}"
                f"[!] Erro ao receber mensagem: {e}"
                f"{Cor.RESET}"
            )

    def entrar_board(self, nome_board):

        if nome_board not in BOARDS.values():

            print(
                f"{Cor.VERMELHO}"
                f"[!] Board '{nome_board}' não existe."
                f"{Cor.RESET}"
            )

            return

        if self.board:

            try:

                self.client.unsubscribe(
                    f"{TOPICO_BASE}{self.board}"
                )

            except Exception:
                pass

        self.board = nome_board

        try:

            self.client.subscribe(
                f"{TOPICO_BASE}{nome_board}"
            )

        except Exception as e:

            print(
                f"{Cor.VERMELHO}"
                f"[!] Não foi possível entrar na board: {e}"
                f"{Cor.RESET}"
            )

            return

        cor = COR_BOARD.get(
            nome_board,
            Cor.RESET
        )

        limpar_tela()

        print(
            f"\n{cor}"
            "╔══════════════════════════════╗"
        )

        print(
            f"║   Você entrou em: "
            f"#{nome_board:<10} ║"
        )

        print(
            "╚══════════════════════════════╝"
            f"{Cor.RESET}"
        )

        self.mostrar_historico(
            nome_board,
            20
        )

        print(
            f"\n{Cor.CINZA}"
            "Comandos:"
            f"{Cor.RESET}"
        )

        print(
            f"  {Cor.AMARELO}/boards{Cor.RESET}"
            "     → menu de boards"
        )

        print(
            f"  {Cor.AMARELO}/sair{Cor.RESET}"
            "       → sai do board"
        )

        print(
            f"  {Cor.AMARELO}/historico{Cor.RESET}"
            "  → ver mais mensagens antigas"
        )

        print(
            f"  {Cor.AMARELO}/limpar{Cor.RESET}"
            "     → apaga histórico do board"
        )

        print(
            f"  {Cor.AMARELO}/sairapp{Cor.RESET}"
            "    → fecha o SRM"
        )

        print(
            f"  {Cor.CINZA}<texto>{Cor.RESET}"
            "      → envia mensagem\n"
        )

    def mostrar_historico(
        self,
        board,
        quantidade=20
    ):

        linhas = carregar_historico(
            board,
            quantidade
        )

        if not linhas:

            print(
                f"\n{Cor.CINZA}"
                "    (sem histórico ainda)"
                f"{Cor.RESET}"
            )

            return

        print(
            f"\n{Cor.CINZA}"
            f"───── últimas {len(linhas)} mensagens ─────"
            f"{Cor.RESET}"
        )

        for linha in linhas:

            formatada = formatar_linha_hist(
                linha,
                board
            )

            if formatada:
                print(formatada)

        print(
            f"{Cor.CINZA}"
            "────────────────────────────────"
            f"{Cor.RESET}"
        )

    def sair_board(self):

        if self.board:

            try:

                self.client.unsubscribe(
                    f"{TOPICO_BASE}{self.board}"
                )

            except Exception:
                pass

            print(
                f"{Cor.CINZA}"
                f"[←] Você saiu do board #{self.board}"
                f"{Cor.RESET}"
            )

            self.board = None

    def enviar(self, texto):

        if not self.board:

            entrada_terminal.imprimir_mensagem(
                f"{Cor.VERMELHO}"
                "[!] Entre em um board primeiro."
                f"{Cor.RESET}"
            )

            return

        if not self.conectado:

            entrada_terminal.imprimir_mensagem(
                f"{Cor.VERMELHO}"
                "[!] Você não está conectado ao servidor."
                f"{Cor.RESET}"
            )

            return

        msg = f"{self.apelido}: {texto}"

        try:

            resultado = self.client.publish(
                f"{TOPICO_BASE}{self.board}",
                msg
            )

            if resultado.rc != mqtt.MQTT_ERR_SUCCESS:

                entrada_terminal.imprimir_mensagem(
                    f"{Cor.VERMELHO}"
                    "[!] Erro ao enviar mensagem."
                    f"{Cor.RESET}"
                )

                return

            salvar_mensagem(
                self.board,
                self.apelido,
                texto
            )

        except Exception as e:

            entrada_terminal.imprimir_mensagem(
                f"{Cor.VERMELHO}"
                f"[!] Erro ao enviar: {e}"
                f"{Cor.RESET}"
            )

    def menu_boards(self):

        while True:

            limpar_tela()
            banner()

            print(
                f"{Cor.CINZA}"
                f"Apelido: "
                f"{Cor.NEG}{self.apelido}"
                f"{Cor.RESET}\n"
            )

            mostrar_boards()

            print(
                f"\n  {Cor.VERMELHO}"
                "[0]"
                f"{Cor.RESET} Sair do SRM"
            )

            try:

                nome_entrada = input(
                    f"\n{Cor.AMARELO}"
                    "Escolha uma board: "
                    f"{Cor.RESET}"
                ).strip()

except (
                EOFError,
                KeyboardInterrupt
            ):
                return False

            if escolha == "0":
                return False

            elif escolha in BOARDS:

                self.entrar_board(
                    BOARDS[escolha]
                )

                return True

            else:

                print(
                    f"{Cor.VERMELHO}"
                    "[!] Opção inválida."
                    f"{Cor.RESET}"
                )

                time.sleep(1)

    def ler_comando(self):

        entrada_terminal.iniciar(
            f"{Cor.AMARELO}> {Cor.RESET}"
        )

        try:

            texto = entrada_terminal.ler()

        finally:

            entrada_terminal.restaurar()

        return texto.strip()

    def rodar(self):

        print(
            f"{Cor.CINZA}"
            "[*] Conectando ao servidor..."
            f"{Cor.RESET}"
        )

        try:

            self.client.connect(
                BROKER,
                PORTA,
                60
            )

        except Exception as e:

            print(
                f"{Cor.VERMELHO}"
                f"[✗] Não foi possível conectar: {e}"
                f"{Cor.RESET}"
            )

            print(
                f"{Cor.CINZA}"
                "Verifique sua internet e tente novamente."
                f"{Cor.RESET}"
            )

            return

        threading.Thread(
            target=self.client.loop_forever,
            daemon=True
        ).start()

        time.sleep(0.3)

        ativo = self.menu_boards()

        while ativo:

            try:

                cmd = self.ler_comando()

            except (
                EOFError,
                KeyboardInterrupt
            ):

                break

            if not cmd:
                continue

            if cmd == "/boards":

                self.sair_board()
                ativo = self.menu_boards()

            elif cmd == "/sair":

                self.sair_board()
                ativo = self.menu_boards()

            elif cmd == "/historico":

                if self.board:

                    print()

                    self.mostrar_historico(
                        self.board,
                        100
                    )

                else:

                    print(
                        f"{Cor.VERMELHO}"
                        "[!] Entre em um board primeiro."
                        f"{Cor.RESET}"
                    )

            elif cmd == "/limpar":

                if self.board:

                    if limpar_historico(
                        self.board
                    ):

                        print(
                            f"{Cor.VERDE}"
                            f"[✓] Histórico de "
                            f"#{self.board} apagado."
                            f"{Cor.RESET}"
                        )

                    else:

                        print(
                            f"{Cor.CINZA}"
                            "    Nada para apagar."
                            f"{Cor.RESET}"
                        )

                else:

                    print(
                        f"{Cor.VERMELHO}"
                        "[!] Entre em um board primeiro."
                        f"{Cor.RESET}"
                    )

            elif cmd == "/sairapp":

                break

            else:

                self.enviar(cmd)

        entrada_terminal.restaurar()

        try:

            self.client.disconnect()

        except Exception:
            pass

        print(
            f"\n{Cor.CIANO}"
            "SRM encerrado."
            f"{Cor.RESET}"
        )


if __name__ == "__main__":

    limpar_tela()
    banner()

    try:

        nome = input(
            f"{Cor.AMARELO}"
            "Seu apelido: "
            f"{Cor.RESET}"
        ).strip()

    except (
        EOFError,
        KeyboardInterrupt
    ):

        print(
            f"\n{Cor.CIANO}"
            "SRM encerrado."
            f"{Cor.RESET}"
        )

        sys.exit(0)

    if not nome:
        nome = "anonimo"

    app = SRM(nome)
    app.rodar()
