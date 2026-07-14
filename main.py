#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  TFTFlyway 🛡️ — Sistema Anti-Cheat para TFT                            ║
║                                                                          ║
║  Unifica: LCU Bridge | Live API | Riot API | Coletor Multi-Canal       ║
║           Server Probe | Player Tracker | Detector Híbrido              ║
║           Database | Dashboard Web | Analytics                          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import os, sys, json, time, threading, webbrowser
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Configura encoding UTF-8 para suportar caracteres Unicode no terminal
if sys.stdout.encoding and sys.stdout.encoding.upper() not in ('UTF-8', 'UTF8'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.upper() not in ('UTF-8', 'UTF8'):
    import io
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Adiciona diretório raiz ao path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from core.lcu_bridge import LCUBridge
from core.live_api import LiveAPI
from core.riot_api import RiotAPI
from core.server_probe import ServerProbe
from core.collector import DataCollector
from core.api_key_manager import APIKeyManager
from detector.database import SuspectDatabase
from detector.suspect_detector import SuspectDetector
from detector.player_tracker import PlayerTracker
from analytics.metrics import MetricsEngine

# Cores
class C:
    G='\033[92m'; Y='\033[93m'; R='\033[91m'; B='\033[94m'
    M='\033[95m'; CY='\033[96m'; D='\033[90m'; BOLD='\033[1m'
    RESET='\033[0m'


class TFTFlyway:
    """Sistema principal que orquestra todos os módulos."""

    def __init__(self):
        self.config = self._load_config()
        self.api_key: str = ""

        # Módulos Core
        self.lcu = LCUBridge(self.config.get("lockfile_path"))
        self.live = LiveAPI()
        self.api_key_mgr = APIKeyManager()
        self.riot: RiotAPI = None
        self.collector = DataCollector()
        self.server_probe = ServerProbe()

        # Módulos Detector
        self.db = SuspectDatabase("data/suspects.db")
        self.detector = SuspectDetector(database=self.db)
        self.player_tracker = PlayerTracker(live_api=self.live)
        self.metrics = MetricsEngine(database=self.db)

        # Estado
        self.running = True
        self.meu_nome = ""
        self.meu_puuid = ""

        # Dashboard server
        self._httpd = None

    def _load_config(self) -> dict:
        """Carrega config do .env ou usa defaults."""
        config = {}
        env_file = ROOT / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        config[k.lower()] = v.strip()
        return config

    # ----------------------------------------------------------------
    # SETUP
    # ----------------------------------------------------------------
    def setup(self):
        """Configura conexões iniciais."""
        print(f"\n{C.BOLD}{C.B}╔══════════════════════════════════════╗{C.RESET}")
        print(f"{C.BOLD}{C.B}║     🛡️  TFTFlyway Inicializando      ║{C.RESET}")
        print(f"{C.BOLD}{C.B}╚══════════════════════════════════════╝{C.RESET}\n")

        # 1. LCU
        print(f"{C.D}[1/6]{C.RESET} Conectando LCU...", end=" ")
        if self.lcu.connect():
            print(f"{C.G}✅ OK (porta {self.lcu.port}){C.RESET}")
            summoner = self.lcu.get_current_summoner()
            if summoner:
                self.meu_nome = summoner.get("gameName", "?")
                tag = summoner.get("tagLine", "")
                self.meu_puuid = summoner.get("puuid", "")
                print(f"   👤 {C.BOLD}{self.meu_nome}#{tag}{C.RESET}")
        else:
            print(f"{C.Y}⚠️ LCU indisponível (jogo fechado?){C.RESET}")

        # 2. Live API
        print(f"{C.D}[2/6]{C.RESET} Verificando Live API...", end=" ")
        if self.live.check():
            print(f"{C.G}✅ OK{C.RESET}")
            self.player_tracker.live = self.live
        else:
            print(f"{C.Y}⚠️ Indisponível (fora de partida?){C.RESET}")

        # 3. API Key
        print(f"{C.D}[3/6]{C.RESET} Configurando Riot API...")
        self._setup_riot_api()

        # 4. Detector
        print(f"{C.D}[4/6]{C.RESET} Inicializando detector...")
        self.detector.riot = self.riot
        self.detector.lcu = self.lcu
        self.detector.live = self.live
        self.detector.set_me(self.meu_nome, self.meu_puuid)

        # 5. Server Probe
        print(f"{C.D}[5/6]{C.RESET} Verificando processo do jogo...", end=" ")
        if self.server_probe.extract_game_info():
            info = self.server_probe.server_info
            print(f"{C.G}✅ Servidor: {info['server_ip']}:{info['server_port']}{C.RESET}")
        else:
            print(f"{C.Y}⚠️ Jogo não detectado{C.RESET}")

        # 6. Dashboard
        print(f"{C.D}[6/6]{C.RESET} Preparando dashboard...")
        print(f"\n{C.G}✅ Sistema pronto!{C.RESET}")
        print(f"   📊 Dados salvos em: {ROOT / 'data' / 'suspects.db'}")
        print()

    def _setup_riot_api(self):
        """Configura API Key da Riot com renovacao automatica."""
        self.api_key = self.api_key_mgr.key or self.config.get("riot_api_key", "")

        if not self.api_key:
            if sys.stdin.isatty():
                print(f"\n{C.Y}⚠️ Riot API Key necessária!{C.RESET}")
                manual = input(f"   🔑 Digite (Enter p/ renovar): ").strip()
                if manual:
                    self.api_key = manual
            print(f"   {C.D}Renovando chave...{C.RESET}")

        if self.api_key:
            self.api_key_mgr.key = self.api_key
            self.riot = RiotAPI(self.api_key)

        game_name = self.config.get("riot_id", self.meu_nome or "0Ph4nT3on")
        tagline = self.config.get("tagline", "5083")
        valida = False

        if self.riot:
            account = self.riot.get_account_by_riot_id(game_name, tagline)
            valida = account is not None

        if valida:
            print(f"   {C.G}✅ API Key válida! Conta: {game_name}#{tagline}{C.RESET}")
            if self.api_key_mgr.key and self.api_key_mgr.key != self.api_key:
                self.api_key = self.api_key_mgr.key
            if not self.meu_puuid and account:
                self.meu_puuid = account.get("puuid", "")
                self.detector.set_me(game_name, self.meu_puuid)
        else:
            print(f"   {C.Y}⚠️ API Key inválida. Renovando...{C.RESET}")
            if self.api_key_mgr.renew():
                self.api_key = self.api_key_mgr.key
                self.riot = RiotAPI(self.api_key)
                account2 = self.riot.get_account_by_riot_id(game_name, tagline)
                if account2:
                    print(f"   {C.G}✅ Chave renovada!{C.RESET}")
                    if not self.meu_puuid:
                        self.meu_puuid = account2.get("puuid", "")
                        self.detector.set_me(game_name, self.meu_puuid)
                else:
                    print(f"   {C.R}❌ Falha na renovacao.{C.RESET}")
            else:
                print(f"   {C.R}❌ Não foi possível renovar.{C.RESET}")

    # ----------------------------------------------------------------
    # COMANDOS
    # ----------------------------------------------------------------
    def cmd_scan(self, args=""):
        """Escaneia jogadores na sala atual."""
        print(f"\n{C.BOLD}{C.M}🔎 Escaneando sala...{C.RESET}")

        jogadores = []

        # Tenta Live API
        if self.live.available:
            players = self.live.get_player_list()
            jogadores = [p.get("summonerName", "") for p in players]
        elif self.lcu.connected:
            jogadores = [m.get("summonerName", "") for m in self.lcu.get_player_list()]

        if not jogadores:
            print(f"{C.Y}⚠️ Nenhum jogador encontrado. Em uma partida?{C.RESET}")
            return

        print(f"   👥 {len(jogadores)} jogador(es):")
        for j in jogadores:
            print(f"      • {j}")

        resultados = self.detector.escanear_sala(jogadores)
        hackers = [r for r in resultados if r.get("is_hacker")]

        print(f"\n{'═' * 50}")
        if hackers:
            print(f"{C.R}🚨 {len(hackers)} HACKER(S) DETECTADO(S)!{C.RESET}")
            for h in hackers:
                print(f"   • {h['player']} — Score: {h['score_total']} ({h['nivel']})")
        else:
            print(f"{C.G}✅ Nenhum hacker detectado.{C.RESET}")

        # Salva métricas
        self.db.register_metrics(
            total_matches=1,
            hackers_found=len(hackers),
            suspects_found=len([r for r in resultados if r.get("score_total", 0) > 0]),
            avg_score=sum(r.get("score_total", 0) for r in resultados) / len(resultados) if resultados else 0
        )

    def cmd_prescan(self, args=""):
        """🔍 PRÉ-SCAN: Analisa jogadores no lobby ANTES da partida."""
        print(f"\n{C.BOLD}{C.M}╔══════════════════════════════════════╗{C.RESET}")
        print(f"{C.BOLD}{C.M}║      🔍 PRÉ-SCAN DE LOBBY            ║{C.RESET}")
        print(f"{C.BOLD}{C.M}╚══════════════════════════════════════╝{C.RESET}")

        jogadores = []
        fase = self.lcu.get_gameflow_phase() if self.lcu.connected else ""

        if fase in ("InGame", "InProgress"):
            if self.live.check():
                players = self.live.get_player_list()
                jogadores = [{"summonerName": p.get("summonerName", "")} for p in players]
            if not jogadores and self.lcu.connected:
                try:
                    import requests as req
                    r = req.get(f"https://127.0.0.1:{self.lcu.port}/lol-tft/v1/session",
                               auth=("riot", self.lcu.token), verify=False, timeout=2)
                    if r.status_code == 200:
                        data = r.json()
                        ps = data.get("players", data.get("participants", []))
                        jogadores = [{"summonerName": p.get("summonerName", p.get("name", "?"))} for p in ps]
                except:
                    pass
        elif self.lcu.connected:
            jogadores = self.lcu.get_player_list()

        if not jogadores:
            print(f"   {C.Y}⚠️ Nenhum jogador encontrado.")
            if not fase:
                print(f"   {C.Y}   LCU desconectado. League of Legends está aberto?{C.RESET}")
            elif fase in ("InGame", "InProgress"):
                print(f"   {C.Y}   Live API indisponível. Habilite nas config do LoL.{C.RESET}")
            else:
                print(f"   {C.Y}   Fase atual: {fase}. Entre em um lobby primeiro.{C.RESET}")
            return

        nomes = [j.get("summonerName", "?") for j in jogadores]
        print(f"   👥 {len(nomes)} jogador(es) encontrados (fase: {fase}):")
        for n in nomes:
            print(f"      • {n}")

        resultado = self.detector.prescan_lobby(nomes)
        if not resultado.get("jogadores"):
            print(f"\n   {C.Y}Não foi possível analisar os jogadores.{C.RESET}")
            return

        print(f"\n{C.BOLD}{C.CY}{'═'*50}{C.RESET}")
        for p in resultado["jogadores"]:
            cor = C.R if p["score"] >= 60 else (C.Y if p["score"] >= 30 else C.D)
            print(f"   {cor}{p['player']:20s}{C.RESET} | "
                  f"Score: {cor}{p['score']:>5.1f}{C.RESET} | "
                  f"{p['nivel']:8s} | {p['fonte']}")

        risco = resultado["risco_medio"]
        print(f"\n   📊 Risco médio: ", end="")
        if risco >= 60:
            print(f"{C.R}{risco}/100 — ALTO!{C.RESET}")
        elif risco >= 30:
            print(f"{C.Y}{risco}/100 — Moderado{C.RESET}")
        else:
            print(f"{C.G}{risco}/100 — Baixo{C.RESET}")

        if resultado["hacker_encontrado"]:
            print(f"\n{C.R}{'🔴'*25}{C.RESET}")
            print(f"{C.BOLD}{C.R}🚨 DODGE RECOMENDADO! HACKER NA SALA!{C.RESET}")
            print(f"{C.R}{'🔴'*25}{C.RESET}")
            for a in resultado["alertas"]:
                print(f"   {C.R}{a}{C.RESET}")
            print(f"\n{C.R}⚠️ Saia da fila imediatamente!{C.RESET}")
        elif resultado["alertas"]:
            print(f"\n{C.Y}⚠️ Jogadores suspeitos:{C.RESET}")
            for a in resultado["alertas"]:
                print(f"   {a}")
        else:
            print(f"\n{C.G}✅ Sala segura!{C.RESET}")
        print()

    def cmd_monitor(self, args=""):
        """Inicia monitoramento contínuo."""
        interval = int(args) if args.isdigit() else 10
        print(f"{C.BOLD}{C.M}🤖 Monitoramento contínuo (a cada {interval}s){C.RESET}")
        print(f"{C.D}   Pressione Ctrl+C para parar{C.RESET}")
        self.detector.iniciar_monitoramento(interval)
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.detector.parar_monitoramento()
            print(f"\n{C.Y}⏹️ Monitoramento parado.{C.RESET}")

    def cmd_auto(self, args=""):
        """🤖 MODO AUTOMÁTICO: Detecta partida, monitora, para sozinho."""
        interval = int(args) if args.isdigit() else 5
        print(f"\n{C.BOLD}{C.M}╔══════════════════════════════════════╗{C.RESET}")
        print(f"{C.BOLD}{C.M}║      🤖 TFTFlyway MODO AUTOMÁTICO    ║{C.RESET}")
        print(f"{C.BOLD}{C.M}╚══════════════════════════════════════╝{C.RESET}")
        print(f"   {C.D}Aguardando início de partida...{C.RESET}")
        print(f"   {C.D}Monitoramento a cada {interval}s{C.RESET}")
        print(f"   {C.D}Pressione Ctrl+C para parar{C.RESET}\n")

        self.running = True
        last_phase = ""
        em_partida = False
        total_varreduras = 0

        try:
            while self.running:
                phase = self.lcu.get_gameflow_phase() if self.lcu.connected else None
                if not phase:
                    phase = "Desconectado"

                if phase != last_phase:
                    print(f"   {C.CY}📌 Fase: {phase}{C.RESET}")
                    last_phase = phase

                    # PRÉ-SCAN automático quando entra no lobby
                    if phase in ("Lobby", "Matchmaking", "ReadyCheck"):
                        print(f"\n{C.CY}🔍 Pré-scan do lobby...{C.RESET}")
                        lobby_players = self.lcu.get_player_list()
                        if lobby_players:
                            nomes = [j.get("summonerName", "?") for j in lobby_players]
                            resultado = self.detector.prescan_lobby(nomes)
                            if resultado["hacker_encontrado"]:
                                print(f"\n{C.R}{'🔴'*25}{C.RESET}")
                                print(f"{C.BOLD}{C.R}🚨 DODGE! HACKER NA SALA!{C.RESET}")
                                print(f"{C.R}{'🔴'*25}{C.RESET}")
                                for a in resultado["alertas"]:
                                    print(f"   {C.R}{a}{C.RESET}")
                            elif resultado["alertas"]:
                                print(f"\n{C.Y}⚠️ Suspeitos:{C.RESET}")
                                for a in resultado["alertas"]:
                                    print(f"   {a}")
                            else:
                                print(f"\n{C.G}✅ Sala segura!{C.RESET}")

                if phase in ("InGame", "InProgress") and not em_partida:
                    em_partida = True
                    total_varreduras = 0
                    print(f"\n{C.G}{'='*50}{C.RESET}")
                    print(f"{C.G}🎮 PARTIDA INICIADA! Aguardando Live API...{C.RESET}")
                    print(f"{C.G}{'='*50}{C.RESET}")

                    # Aguarda Live API ficar disponivel
                    for tentativa in range(15):
                        if self.live.check():
                            self.player_tracker.live = self.live
                            print(f"   {C.G}✅ Live API online!{C.RESET}")
                            break
                        print(f"   {C.D}Aguardando Live API ({tentativa+1}/15)...{C.RESET}")
                        time.sleep(2)
                    else:
                        print(f"   {C.Y}⚠️ Live API não respondeu. Usando LCU.{C.RESET}")

                    print(f"{C.G}🚀 Monitorando partida...{C.RESET}")
                    self.detector.iniciar_monitoramento(interval)

                elif phase not in ("InGame", "InProgress", "Reconnect", "PreEndOfGame") and em_partida:
                    em_partida = False
                    self.detector.parar_monitoramento()
                    print(f"\n{C.Y}{'='*50}{C.RESET}")
                    print(f"{C.Y}⏹️ Partida encerrada ({phase}){C.RESET}")
                    print(f"{C.Y}{'='*50}{C.RESET}")

                    relatorio = self.detector.get_relatorio()
                    hackers = relatorio.get("hackers", [])
                    if hackers:
                        print(f"\n{C.R}🚨 Hackers detectados:{C.RESET}")
                        for h in hackers:
                            print(f"   ⚠️ {C.BOLD}{h}{C.RESET}")
                    else:
                        print(f"\n{C.G}✅ Partida limpa!{C.RESET}")
                    print(f"   📊 Total de varreduras: {total_varreduras}")
                    print(f"\n{C.D}Aguardando próxima partida...{C.RESET}\n")

                if em_partida:
                    total_varreduras += 1

                time.sleep(2)

        except KeyboardInterrupt:
            self.detector.parar_monitoramento()
            print(f"\n{C.Y}⏹️ Modo automático encerrado.{C.RESET}")

    def cmd_report(self, args=""):
        """Exibe relatório completo."""
        print(f"\n{C.BOLD}{C.M}📊 RELATÓRIO TFTFlyway{C.RESET}")
        print(f"{'═' * 50}")

        relatorio = self.detector.get_relatorio()
        print(f"\n{C.BOLD}Sessão:{C.RESET}")
        print(f"   Hackers detectados: {relatorio['sessao']['hackers_detectados']}")
        print(f"   Jogadores observados: {relatorio['sessao']['jogadores_observados']}")

        if relatorio["banco"]:
            print(f"\n{C.BOLD}Banco de Dados:{C.RESET}")
            for k, v in relatorio["banco"].items():
                print(f"   {k}: {v}")

        if relatorio["hackers"]:
            print(f"\n{C.R}🚨 Hackers na sessão:{C.RESET}")
            for h in relatorio["hackers"]:
                print(f"   • {h}")

    def cmd_dashboard(self, args=""):
        """Inicia servidor web do dashboard."""
        port = int(args) if args.isdigit() else 8000

        # Gera data.json
        dashboard_data = self.metrics.get_dashboard_json()
        with open(ROOT / "web" / "data.json", "w", encoding="utf-8") as f:
            f.write(dashboard_data)
        print(f"{C.G}✅ Dados exportados para web/data.json{C.RESET}")

        # Handler que serve arquivos da pasta web/
        os.chdir(str(ROOT / "web"))

        handler = SimpleHTTPRequestHandler
        self._httpd = HTTPServer(("0.0.0.0", port), handler)

        url = f"http://localhost:{port}"
        print(f"\n{C.BOLD}{C.CY}📊 Dashboard TFTFlyway{C.RESET}")
        print(f"{'═' * 50}")
        print(f"   🌐 {url}")
        print(f"   {C.D}Ctrl+C para parar{C.RESET}")
        print(f"{'═' * 50}")

        webbrowser.open(url)

        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            self._httpd.shutdown()
            print(f"\n{C.Y}⏹️ Dashboard parado.{C.RESET}")
        finally:
            os.chdir(str(ROOT))

    def cmd_search(self, args=""):
        """Busca um jogador específico."""
        if not args:
            print(f"{C.Y}Uso: search <nome_do_jogador>{C.RESET}")
            return
        resultado = self.detector.escanear_jogador(args)
        if resultado.get("error"):
            print(f"{C.R}❌ Erro ao analisar {args}{C.RESET}")
        else:
            self._print_resultado(args, resultado)

    # ----------------------------------------------------------------
    # NOVOS COMANDOS
    # ----------------------------------------------------------------
    def cmd_probe(self, args=""):
        """Sonda o servidor TFT diretamente."""
        print(f"\n{C.BOLD}{C.M}📡 Testando conexão com servidor TFT...{C.RESET}")

        info = self.server_probe.extract_game_info()
        if not info:
            print(f"{C.Y}⚠️ Jogo não está rodando. Entre em uma partida.{C.RESET}")
            return

        print(f"   🖥️ Servidor: {info['server_ip']}:{info['server_port']}")
        print(f"   🆔 PlayerID: {info.get('player_id', '?')}")
        print(f"   🎮 GameID: {info.get('GameID', '?')}")

        # Latência
        latencia = self.server_probe.get_latency()
        if latencia:
            print(f"   ⏱️ Latência: {latencia}ms")

        # Testa protocolos
        print(f"\n{C.BOLD}Testando protocolos...{C.RESET}")
        results = self.server_probe.probe_server()
        if results:
            print(f"{C.G}✅ {len(results)} resposta(s) do servidor{C.RESET}")
            for r in results:
                print(f"   • {r['formato']} ({r['tipo']}) — {r.get('resposta_hex', '')[:30]}")
        else:
            print(f"{C.Y}⚠️ Nenhuma resposta do servidor (protocolo criptografado){C.RESET}")

    def cmd_track(self, args=""):
        """Inicia rastreamento em tempo real da partida."""
        interval = float(args) if args.replace('.','',1).isdigit() else 2.0

        if not self.live.available:
            print(f"{C.Y}⚠️ Live API indisponível. Em uma partida?{C.RESET}")
            return

        print(f"{C.BOLD}{C.M}🎯 Rastreador de partida iniciado (a cada {interval}s){C.RESET}")
        print(f"{C.D}   Pressione Ctrl+C para parar{C.RESET}")

        self.player_tracker.start_tracking(interval)

        # Callback para suspeitos
        def on_suspicious(data):
            player = data.get("player", "?")
            patterns = data.get("patterns", [])
            print(f"\n{C.Y}⚠️ Padrão suspeito em {player}:{C.RESET}")
            for p in patterns:
                print(f"   • {p.get('detail', '')}")

        self.player_tracker.on_suspicious(on_suspicious)

        try:
            while self.running:
                # Mostra status a cada 30s
                time.sleep(30)
                total = len(self.player_tracker.snapshots)
                players = len(self.player_tracker.suspicious_patterns)
                print(f"   📊 {total} snapshots | {players} jogadores com padrões suspeitos")
        except KeyboardInterrupt:
            self.player_tracker.stop_tracking()
            print(f"\n{C.Y}⏹️ Rastreamento parado.{C.RESET}")

    def cmd_collect(self, args=""):
        """Coleta dados de todos os canais disponíveis."""
        print(f"{C.BOLD}{C.M}📦 Coletando dados de todos os canais...{C.RESET}")

        data = self.collector.collect_all()
        summary = self.collector.get_summary()

        print(f"\n{C.BOLD}Resultados:{C.RESET}")
        print(f"   LCU: {'✅' if summary['lcu_endpoints'] > 0 else '❌'} ({summary['lcu_endpoints']} endpoints)")
        print(f"   Live API: {'✅' if summary['live_api_endpoints'] > 0 else '❌'} ({summary['live_api_endpoints']} endpoints)")
        print(f"   RiotClient: {'✅' if summary['riot_client_endpoints'] > 0 else '❌'}")
        print(f"   Game Process: {'✅' if summary['game_process'] else '❌'}")

        if data.get("game_process"):
            gp = data["game_process"]
            print(f"\n{C.CY}Informações do Servidor:{C.RESET}")
            print(f"   IP: {gp.get('SERVER_IP', '?')}")
            print(f"   Porta: {gp.get('SERVER_PORT', '?')}")
            print(f"   GameID: {gp.get('GameID', '?')}")

    def cmd_players(self, args=""):
        """Mostra jogadores na partida com dados ao vivo."""
        if not self.live.available:
            print(f"{C.Y}⚠️ Live API indisponível. Em uma partida?{C.RESET}")
            return

        players = self.live.get_all_players_summary()
        active = self.live.get_active_player()

        print(f"\n{C.BOLD}{C.CY}👥 Jogadores na Partida{C.RESET}")
        print(f"{'═' * 60}")
        for p in players:
            nome = p.get("name", "?")
            if "#" in nome:
                nome = nome.split("#")[0]
            champ = p.get("champion", "?")
            lvl = p.get("level", "?")
            items = len(p.get("items", []))

            # Destaca o próprio jogador
            prefix = f"{C.G}▶{C.RESET}" if nome.lower() == self.meu_nome.lower() else " "
            print(f" {prefix} {C.BOLD}{nome[:15]:15s}{C.RESET} | {champ[:10]:10s} | Lvl {lvl} | {items} itens")
        print(f"{'═' * 60}")
        if active:
            gold = active.get("currentGold", 0)
            level = active.get("level", 0)
            print(f"   🪙 Gold: {gold}  |  📊 Level: {level}")

    def cmd_blacklist(self, args=""):
        """Mostra lista negra de hackers confirmados."""
        if not self.db:
            print(f"{C.Y}⚠️ Banco de dados não disponível{C.RESET}")
            return

        hackers = self.db.get_hackers_only()
        if not hackers:
            print(f"\n{C.G}✅ Nenhum hacker na lista negra.{C.RESET}")
            return

        print(f"\n{C.R}🚨 LISTA NEGRA — {len(hackers)} HACKER(S) CONFIRMADO(S){C.RESET}")
        print(f"{'═' * 60}")
        for i, h in enumerate(hackers, 1):
            print(f"\n{i}. {C.BOLD}{h['summoner_name']}{C.RESET}")
            print(f"   Score máximo: {h['max_score']} | Nível: {h['nivel_max']}")
            print(f"   Encontros: {h['total_meets']}")
            print(f"   Último: {h['last_seen'][:19]}")
            if h.get('puuid'):
                print(f"   PUUID: {h['puuid'][:20]}...")
        print(f"\n{'═' * 60}")

    def _print_resultado(self, nome, res):
        print(f"\n{C.BOLD}Resultado para {nome}:{C.RESET}")
        print(f"   Score: {res.get('score_total', 0)}")
        print(f"   Nível: {res.get('nivel', 'N/A')}")
        print(f"   Hacker: {'🚨 SIM' if res.get('is_hacker') else '✅ NÃO'}")
        if res.get("razoes"):
            print(f"   Razões:")
            for r in res["razoes"]:
                print(f"      {r}")

    def cmd_help(self, args=""):
        """Ajuda."""
        print(f"""
{C.BOLD}{C.CY}🛡️ TFTFlyway Comandos{C.RESET}
{'═' * 50}
{C.BOLD}Anti-Cheat / Detecção:{C.RESET}
  {C.G}scan{C.RESET}                          Escaneia jogadores na sala atual
  {C.G}prescan{C.RESET}                       🔍 PRÉ-SCAN do lobby (antes da partida)
  {C.G}monitor [N]{C.RESET}                   Monitoramento contínuo (N=intervalo)
  {C.G}auto [N]{C.RESET}                      🤖 Modo automático (detecta partida)
  {C.G}search <nome>{C.RESET}                 Analisa um jogador específico
  {C.G}blacklist{C.RESET}                     Lista negra de hackers confirmados

{C.BOLD}Rastreamento:{C.RESET}
  {C.G}track [N]{C.RESET}                     Rastreia partida em tempo real (N=intervalo)
  {C.G}players{C.RESET}                       Mostra jogadores com dados ao vivo
  {C.G}probe{C.RESET}                         Sonda o servidor TFT diretamente
  {C.G}collect{C.RESET}                       Coleta dados de todos os canais

{C.BOLD}Dados:{C.RESET}
  {C.G}report{C.RESET}                        Relatório da sessão
  {C.G}dashboard [porta]{C.RESET}             Abre dashboard web (default: 8000)
  {C.G}export{C.RESET}                        Exporta dados para JSON

{C.BOLD}Sistema:{C.RESET}
  {C.G}status{C.RESET}                        Status das conexões
  {C.G}quit{C.RESET} ou {C.G}exit{C.RESET}               Sair
{'═' * 50}
""")

    def cmd_status(self, args=""):
        """Status das conexões."""
        print(f"\n{C.BOLD}{C.CY}📡 Status do Sistema{C.RESET}")
        print(f"{'═' * 50}")
        print(f"   LCU:          {'🟢 Online' if self.lcu.connected else '🔴 Offline'}")
        print(f"   Live API:     {'🟢 Online' if self.live.available else '🔴 Offline'}")
        print(f"   Riot API:     {'🟢 Configurada' if self.riot and self.riot.api_key else '🔴 Não configurada'}")
        print(f"   Server Probe: {'🟢 Jogo detectado' if self.server_probe.in_game else '🔴 Offline'}")
        print(f"   Tracker:      {'🟢 Ativo' if self.player_tracker.tracking else '🔴 Parado'}")
        if self.db:
            summary = self.db.get_summary()
            print(f"   DB:           🟢 {summary.get('total_suspects', 0)} suspeitos, {summary.get('hackers', 0)} hackers")
        print(f"   Detector:     {'🟢 Ativo' if self.detector._monitoring else '🔴 Parado'}")

    def cmd_export(self, args=""):
        """Exporta dados."""
        path = self.metrics.export_json()
        print(f"{C.G}✅ Dados exportados para: {path}{C.RESET}")

    # ----------------------------------------------------------------
    # MENU INTERATIVO
    # ----------------------------------------------------------------
    def menu(self):
        """Loop principal do menu interativo."""
        print(f"\n{C.BOLD}{C.CY}🛡️ TFTFlyway — Menu Interativo{C.RESET}")
        print(f"{C.D}   Digite 'help' para comandos disponíveis{C.RESET}")

        while self.running:
            try:
                cmd = input(f"\n{C.BOLD}tft> {C.RESET}").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not cmd:
                continue

            # Parseia comando + argumentos
            parts = cmd.split(maxsplit=1)
            command = parts[0]
            args = parts[1] if len(parts) > 1 else ""

            method = getattr(self, f"cmd_{command}", None)
            if method:
                method(args)
            elif command in ("quit", "exit", "q"):
                print(f"{C.Y}👋 Encerrando...{C.RESET}")
                break
            else:
                print(f"{C.R}❌ Comando desconhecido: {command}{C.RESET}")
                print(f"   Digite {C.G}help{C.RESET} para ver os comandos disponíveis")

        self.shutdown()

    def shutdown(self):
        """Limpa recursos."""
        self.running = False
        self.detector.parar_monitoramento()
        self.player_tracker.stop_tracking()
        self.collector.stop_collecting()
        if self.lcu:
            self.lcu.close()
        if self.live:
            self.live.close()
        if self.db:
            self.db.close()
        if self._httpd:
            self._httpd.shutdown()
        print(f"{C.G}✅ Sistema encerrado.{C.RESET}")

    # ----------------------------------------------------------------
    # MODO DIRETO
    # ----------------------------------------------------------------
    def run_command(self, cmd: str):
        """Executa um comando direto (sem menu)."""
        parts = cmd.split(maxsplit=1)
        command = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        method = getattr(self, f"cmd_{command}", None)
        if method:
            method(args)
        else:
            print(f"Comando desconhecido: {command}")


# ===================================================================
# MAIN
# ===================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="🛡️ TFTFlyway — Sistema Anti-Cheat para TFT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python main.py                          # Menu interativo
  python main.py scan                     # Escaneia sala uma vez
  python main.py auto                     # 🤖 Modo automático
  python main.py monitor                  # Monitoramento contínuo
  python main.py dashboard                # Dashboard web
  python main.py search "Jogador#BR1"     # Busca jogador
  python main.py report                   # Relatório
        """
    )
    parser.add_argument("command", nargs="?", help="Comando para executar")
    parser.add_argument("args", nargs="*", help="Argumentos do comando")

    args = parser.parse_args()

    system = TFTFlyway()
    system.setup()

    if args.command:
        # Modo direto
        cmd = args.command
        if args.args:
            cmd += " " + " ".join(args.args)
        system.run_command(cmd)
        # Se for comando único, não entra no menu (exceto monitor/dashboard que são contínuos)
        if args.command not in ("monitor", "dashboard"):
            system.shutdown()
    else:
        # Menu interativo
        system.menu()


if __name__ == "__main__":
    main()
