import paho.mqtt.client as mqtt
import threading
import sys
import os
import time
from datetime import datetime

BROKER = "test.mosquitto.org"
PORTA = 1883                                         TOPICO_BASE = "srm/board/"

# ===== PASTA DE HISTÓRICO =====
PASTA_SRM = os.path.expanduser("~/.srm")
PASTA_HIST = os.path.join(PASTA_SRM, "historico")    os.makedirs(PASTA_HIST, exist_ok=True)

# ===== CORES ANSI =====                             class Cor:
    RESET   = "\033[0m"
    NEG     = "\033[1m"
    VERDE   = "\033[92m"
    CIANO   = "\033[96m"
    AMARELO = "\033[93m"
    VERMELHO= "\033[91m"
    ROXO    = "\033[95m"
    AZUL    = "\033[94m"
    CINZA   = "\033[90m"

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
    "Goon":     Cor.ROXO,
    "Anime":    Cor.CIANO,
    "Futebol":  Cor.VERDE,
    "Random":   Cor.AMARELO,
    "Resenha":  Cor.AZUL,
    "Games":    Cor.VERMELHO,
}

def limpar_tela():
    os.system("clear")

def banner():
    print(Cor.CIANO + Cor.NEG + """
   ███████╗██████╗ ███╗   ███╗
   ██╔════╝██╔══██╗████╗ ████║
   ███████╗██████╔╝██╔████╔██║
   ╚════██║██╔══██╗██║╚██╔╝██║
   ███████║██║  ██║██║ ╚═╝ ██║
   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝
""" + Cor.RESET)
    print(Cor.CINZA + "        chat em tempo real\n" + Cor.RESET)

def mostrar_boards():
    print(Cor.NEG + "╔══════════════════════════════╗")
    print("║      BOARDS DISPONÍVEIS      ║")
    print("╠══════════════════════════════╣" + Cor.RESET)
    for num, nome in BOARDS.items():
        cor = COR_BOARD.get(nome, Cor.RESET)
        # Mostra quantas mensagens tem no histórico
        qtd = contar_historico(nome)
        contagem = f"{Cor.CINZA}({qtd}){Cor.RESET}" if qtd else ""
        print(f"  {Cor.AMARELO}[{num}]{Cor.RESET}  {cor}#{nome:<10}{Cor.RESET} {contagem}")
    print(Cor.NEG + "╚══════════════════════════════╝" + Cor.RESET)

def caminho_hist(board):
    return os.path.join(PASTA_HIST, f"{board}.log")

def contar_historico(board):
    caminho = caminho_hist(board)
    if not os.path.exists(caminho):
        return 0
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def salvar_mensagem(board, quem, texto):
    """Salva uma mensagem no histórico com timestamp."""
    caminho = caminho_hist(board)
    timestamp = datetime.now().strftime("%d/%m %H:%M")
    linha = f"{timestamp}|{quem}|{texto}\n"
    try:
        with open(caminho, "a", encoding="utf-8") as f:
            f.write(linha)
    except Exception as e:
        print(f"{Cor.VERMELHO}[!] Erro ao salvar histórico: {e}{Cor.RESET}")

def carregar_historico(board, quantidade=20):
    """Retorna as últimas N mensagens do histórico."""
    caminho = caminho_hist(board)
    if not os.path.exists(caminho):
        return []
    try:
        with open(caminho, "r", encoding="utf-8") as f:
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
    """Formata uma linha do histórico para exibição."""
    cor = COR_BOARD.get(board, Cor.RESET)
    partes = linha.strip().split("|", 2)
    if len(partes) != 3:
        return None
    ts, quem, texto = partes
    return (f"{Cor.CINZA}{ts}{Cor.RESET} "
            f"{cor}[#{board}]{Cor.RESET} "
            f"{Cor.NEG}{quem}{Cor.RESET}: {texto}")

class SRM:
    def __init__(self, apelido):
        self.apelido = apelido
        self.board = None
        self.client = mqtt.Client()
        self.client.on_connect = self.ao_conectar
        self.client.on_message = self.ao_receber

    def ao_conectar(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"{Cor.VERDE}[✓] Conectado ao servidor SRM.{Cor.RESET}")
            print(f"{Cor.CINZA}    Bem-vindo, {Cor.NEG}{self.apelido}{Cor.RESET}")
            if self.board:
                client.subscribe(f"{TOPICO_BASE}{self.board}")
        else:
            print(f"{Cor.VERMELHO}[✗] Falha na conexão. Código: {rc}{Cor.RESET}")

    def ao_receber(self, client, userdata, msg):
        board_nome = msg.topic.replace(TOPICO_BASE, "")
        texto = msg.payload.decode()
        cor = COR_BOARD.get(board_nome, Cor.RESET)

        # Ignora a própria mensagem (já salva no envio)
        if texto.startswith(f"{self.apelido}:"):
            return

        # Salva no histórico
        if ":" in texto:
            quem, msg_texto = texto.split(":", 1)
            quem = quem.strip()
            msg_texto = msg_texto.strip()
            salvar_mensagem(board_nome, quem, msg_texto)

            print(f"\n{cor}[#{board_nome}]{Cor.RESET} "
                  f"{Cor.NEG}{quem}{Cor.RESET}: {msg_texto}")
        else:
            salvar_mensagem(board_nome, "sistema", texto)
            print(f"\n{cor}[#{board_nome}]{Cor.RESET} {texto}")

        sys.stdout.write(Cor.AMARELO + "> " + Cor.RESET)
        sys.stdout.flush()

    def entrar_board(self, nome_board):
        if nome_board not in BOARDS.values():
            print(f"{Cor.VERMELHO}[!] Board '{nome_board}' não existe.{Cor.RESET}")
            return

        if self.board:
            self.client.unsubscribe(f"{TOPICO_BASE}{self.board}")

        self.board = nome_board
        self.client.subscribe(f"{TOPICO_BASE}{nome_board}")

        cor = COR_BOARD.get(nome_board, Cor.RESET)
        limpar_tela()
        print(f"\n{cor}╔══════════════════════════════╗")
        print(f"║   Você entrou em: #{nome_board:<10} ║")
        print(f"╚══════════════════════════════╝{Cor.RESET}")

        # ===== MOSTRA HISTÓRICO =====
        self.mostrar_historico(nome_board, 20)

        print(f"\n{Cor.CINZA}Comandos:{Cor.RESET}")
        print(f"  {Cor.AMARELO}/boards{Cor.RESET}     → menu de boards")
        print(f"  {Cor.AMARELO}/sair{Cor.RESET}       → sai do board")
        print(f"  {Cor.AMARELO}/historico{Cor.RESET}  → ver mais mensagens antigas")
        print(f"  {Cor.AMARELO}/limpar{Cor.RESET}     → apaga histórico do board")
        print(f"  {Cor.AMARELO}/sairapp{Cor.RESET}    → fecha o SRM")
        print(f"  {Cor.CINZA}<texto>{Cor.RESET}      → envia mensagem\n")

    def mostrar_historico(self, board, quantidade=20):
        linhas = carregar_historico(board, quantidade)
        if not linhas:
            print(f"\n{Cor.CINZA}    (sem histórico ainda){Cor.RESET}")
            return
        print(f"\n{Cor.CINZA}───── últimas {len(linhas)} mensagens ─────{Cor.RESET}")
        for linha in linhas:
            formatada = formatar_linha_hist(linha, board)
            if formatada:
                print(formatada)
        print(f"{Cor.CINZA}────────────────────────────────{Cor.RESET}")

    def sair_board(self):
        if self.board:
            self.client.unsubscribe(f"{TOPICO_BASE}{self.board}")
            print(f"{Cor.CINZA}[←] Você saiu do board #{self.board}{Cor.RESET}")
            self.board = None

    def enviar(self, texto):
        if not self.board:
            print(f"{Cor.VERMELHO}[!] Entre em um board primeiro.{Cor.RESET}")
            return
        msg = f"{self.apelido}: {texto}"
        self.client.publish(f"{TOPICO_BASE}{self.board}", msg)
        # Salva no histórico local
        salvar_mensagem(self.board, self.apelido, texto)

    def menu_boards(self):
        while True:
            limpar_tela()
            banner()
            print(f"{Cor.CINZA}Apelido: {Cor.NEG}{self.apelido}{Cor.RESET}\n")
            mostrar_boards()
            print(f"\n  {Cor.VERMELHO}[0]{Cor.RESET} Sair do SRM")
            escolha = input(f"\n{Cor.AMARELO}Escolha uma board: {Cor.RESET}").strip()

            if escolha == "0":
                return False
            elif escolha in BOARDS:
                self.entrar_board(BOARDS[escolha])
                return True
            else:
                print(f"{Cor.VERMELHO}[!] Opção inválida.{Cor.RESET}")
                time.sleep(1)

    def rodar(self):
        self.client.connect(BROKER, PORTA, 60)
        threading.Thread(target=self.client.loop_forever, daemon=True).start()

        ativo = self.menu_boards()

        while ativo:
            try:
                cmd = input(Cor.AMARELO + "> " + Cor.RESET).strip()
            except (EOFError, KeyboardInterrupt):
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
                    self.mostrar_historico(self.board, 100)
                else:
                    print(f"{Cor.VERMELHO}[!] Entre em um board primeiro.{Cor.RESET}")
            elif cmd == "/limpar":
                if self.board:
                    if limpar_historico(self.board):
                        print(f"{Cor.VERDE}[✓] Histórico de #{self.board} apagado.{Cor.RESET}")
                    else:
                        print(f"{Cor.CINZA}    Nada para apagar.{Cor.RESET}")
                else:
                    print(f"{Cor.VERMELHO}[!] Entre em um board primeiro.{Cor.RESET}")
            elif cmd == "/sairapp":
                break
            else:
                self.enviar(cmd)

        self.client.disconnect()
        print(f"\n{Cor.CIANO}SRM encerrado.{Cor.RESET}")

if __name__ == "__main__":
    limpar_tela()
    banner()
    nome = input(f"{Cor.AMARELO}Seu apelido: {Cor.RESET}").strip() or "anonimo"
    app = SRM(nome)
    app.rodar()
