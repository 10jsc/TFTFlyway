#!/usr/bin/env python3
"""
Data Collector - Coleta dados de TODOS os canais disponíveis.
Multi-canal: LCU, Live API, RiotClient, Game Process, Game Logs.
Alimenta o detector com dados consolidados em tempo real.
"""
import json, time, os, threading, subprocess, re, requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class DataCollector:
    """Coleta dados de todos os canais mapeados do TFT."""

    LOCKFILE_PATHS = [
        r"F:\Riot Games\League of Legends\lockfile",
        r"C:\Riot Games\League of Legends\lockfile",
    ]

    def __init__(self, log_dir: str = "data/collections"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # LCU
        self.lcu_port = None
        self.lcu_token = None
        self.lcu_session = requests.Session()
        self.lcu_session.verify = False

        # Live API
        self.live_session = requests.Session()
        self.live_session.verify = False

        # RiotClient
        self.rc_port = None

        # Dados consolidados
        self.data: Dict[str, Any] = {
            "lcu": {},
            "live_api": {},
            "riot_client": {},
            "game_process": {},
            "game_logs": {},
        }

        self._collecting = False
        self._thread: Optional[threading.Thread] = None

    # ================================================================
    # LCU
    # ================================================================
    def connect_lcu(self) -> bool:
        for lf in self.LOCKFILE_PATHS:
            if not os.path.exists(lf):
                continue
            try:
                with open(lf) as f:
                    parts = f.read().strip().split(':')
                    if len(parts) >= 5:
                        self.lcu_port = int(parts[2])
                        self.lcu_token = parts[3]
                        self.lcu_session.auth = ("riot", self.lcu_token)
                        r = self.lcu_session.get(
                            f"https://127.0.0.1:{self.lcu_port}/lol-summoner/v1/current-summoner",
                            timeout=3)
                        if r.status_code == 200:
                            return True
            except Exception:
                pass
        return False

    def collect_lcu(self) -> Dict:
        """Coleta dados de todos os endpoints LCU disponíveis."""
        if not self.lcu_port:
            return {}
        base = f"https://127.0.0.1:{self.lcu_port}"

        endpoints = [
            "/lol-gameflow/v1/gameflow-phase",
            "/lol-gameflow/v1/session",
            "/lol-summoner/v1/current-summoner",
            "/lol-tft/v1/session",
            "/lol-tft/v1/state",
            "/lol-tft/v1/player",
            "/lol-tft/v1/board",
            "/lol-tft/v1/bench",
            "/lol-tft/v1/augments",
            "/lol-tft/v1/traits",
            "/lol-tft/v1/gamestats",
            "/lol-tft-team-planner/v1/teams",
            "/lol-matchmaking/v1/search",
            "/lol-matchmaking/v1/ready-check",
        ]

        results = {}
        for ep in endpoints:
            try:
                r = self.lcu_session.get(f"{base}{ep}", timeout=2)
                if r.status_code != 404:
                    try:
                        data = r.json()
                    except Exception:
                        data = r.text[:500]
                    results[ep] = {"status": r.status_code, "data": data}
            except Exception:
                pass

        self.data["lcu"] = results
        return results

    # ================================================================
    # LIVE CLIENT API
    # ================================================================
    def collect_live_api(self) -> Dict:
        """Coleta dados da Live Client API (porta 2999)."""
        base = "https://127.0.0.1:2999"

        endpoints = [
            "/liveclientdata/activeplayer",
            "/liveclientdata/allgamedata",
            "/liveclientdata/playerlist",
            "/liveclientdata/gamestats",
            "/liveclientdata/events",
            "/liveclientdata/tft/session",
            "/liveclientdata/tft/player",
            "/liveclientdata/tft/players",
            "/liveclientdata/tft/gamestate",
            "/liveclientdata/tft/gold",
            "/liveclientdata/tft/level",
            "/liveclientdata/tft/traits",
            "/liveclientdata/tft/augments",
        ]

        results = {}
        for ep in endpoints:
            try:
                r = self.live_session.get(f"{base}{ep}", timeout=2)
                if r.status_code == 200:
                    try:
                        data = r.json()
                    except Exception:
                        data = r.text[:500]
                    results[ep] = {"status": 200, "data": data}
                elif r.status_code == 204:
                    results[ep] = {"status": 204}
            except Exception:
                pass

        self.data["live_api"] = results
        return results

    # ================================================================
    # RIOT CLIENT
    # ================================================================
    def find_riot_client(self) -> Optional[int]:
        """Descobre a porta do RiotClientServices."""
        ps = r'''
$ErrorActionPreference='SilentlyContinue'
$p=Get-Process -Name "RiotClientServices" -ErrorAction SilentlyContinue
if(-not $p){Write-Host "NAO"; exit 1}
$cmd=(Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)").CommandLine
if($cmd-match'--app-port=(\d+)'){Write-Host $matches[1]; exit 0}
if($cmd-match'--riotclient-app-port=(\d+)'){Write-Host $matches[1]; exit 0}
Write-Host "NAO"
'''
        try:
            r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW)
            out = r.stdout.strip()
            if out and out != "NAO":
                try:
                    self.rc_port = int(out)
                    return self.rc_port
                except ValueError:
                    pass
        except Exception:
            pass
        return None

    def collect_riot_client(self) -> Dict:
        """Tenta endpoints do RiotClient."""
        if not self.rc_port:
            self.find_riot_client()
        if not self.rc_port:
            return {}

        base = f"https://127.0.0.1:{self.rc_port}"
        results = {}

        for ep in ["/api/v1/products", "/api/v1/session",
                     "/api/v1/process-control/products",
                     "/product/league_of_legends/session",
                     "/product/league_of_legends/process"]:
            try:
                r = requests.get(f"{base}{ep}", auth=("riot", self.lcu_token or ""),
                                verify=False, timeout=1)
                if r.status_code not in (404,):
                    results[ep] = {"status": r.status_code, "data": r.text[:300]}
            except Exception:
                pass

        self.data["riot_client"] = results
        return results

    # ================================================================
    # GAME PROCESS
    # ================================================================
    def collect_game_process(self) -> Dict:
        """Extrai informações do processo do jogo."""
        ps = r'''
$p=Get-Process -Name "League of Legends" -ErrorAction SilentlyContinue
if(-not $p){Write-Host "NAO"; exit 1}
$cmd=(Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)").CommandLine
if(-not $cmd){Write-Host "SEM"; exit 1}
Write-Host $cmd
'''
        try:
            r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW)
            if r.returncode == 0 and r.stdout.strip() and "NAO" not in r.stdout:
                cmdline = r.stdout.strip()
                params = {}

                # IP e porta do servidor
                ip_match = re.search(r'"([\d.]+) (\d+) ([^\s"]+) (\d+)"', cmdline)
                if ip_match:
                    params["SERVER_IP"] = ip_match.group(1)
                    params["SERVER_PORT"] = ip_match.group(2)
                    params["AUTH_TOKEN"] = ip_match.group(3)[:30] + "..."
                    params["PLAYER_ID"] = ip_match.group(4)

                # Outros parâmetros
                for param in ["Product", "PlayerID", "GameID", "Region", "PlatformID",
                              "RiotClientPort", "GameBaseDir"]:
                    if param + "=" in cmdline:
                        idx = cmdline.find(param + "=")
                        end = cmdline.find(" ", idx + len(param) + 1)
                        val = cmdline[idx + len(param) + 1:end] if end > idx else cmdline[idx + len(param) + 1:]
                        params[param] = val.strip('"')

                self.data["game_process"] = params
                return params
        except Exception:
            pass

        self.data["game_process"] = {}
        return {}

    # ================================================================
    # GAME LOGS
    # ================================================================
    def collect_game_logs(self) -> Dict:
        """Lê logs recentes do jogo."""
        logs_dir = Path(r"F:\Riot Games\League of Legends\Logs\GameLogs")
        if not logs_dir.exists():
            return {}

        sessions = sorted(logs_dir.iterdir(), key=lambda p: p.name, reverse=True)
        if not sessions:
            return {}

        latest = sessions[0]
        results = {"session": latest.name, "files": {}}

        for f in latest.iterdir():
            if f.suffix in ('.txt', '.log'):
                results["files"][f.name] = {"size": f.stat().st_size}

        self.data["game_logs"] = results
        return results

    # ================================================================
    # COLETA COMPLETA
    # ================================================================
    def collect_all(self) -> Dict:
        """Coleta dados de todos os canais de uma vez."""
        if self.connect_lcu():
            self.collect_lcu()

        self.collect_live_api()

        if self.find_riot_client():
            self.collect_riot_client()

        self.collect_game_process()
        self.collect_game_logs()

        return self.data

    def collect_loop(self, interval: int = 10, callback=None):
        """Loop de coleta contínua em background."""
        if self._collecting:
            return
        self._collecting = True

        def _loop():
            while self._collecting:
                data = self.collect_all()
                if callback:
                    callback(data)

                # Salva coleta
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = self.log_dir / f"coleta_{ts}.json"
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)

                time.sleep(interval)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop_collecting(self):
        self._collecting = False

    def get_summary(self) -> Dict:
        """Resumo do que foi coletado."""
        return {
            "lcu_endpoints": len(self.data.get("lcu", {})),
            "live_api_endpoints": len(self.data.get("live_api", {})),
            "riot_client_endpoints": len(self.data.get("riot_client", {})),
            "game_process": bool(self.data.get("game_process")),
            "game_logs": bool(self.data.get("game_logs")),
            "lcu_conectado": self.lcu_port is not None,
        }


if __name__ == "__main__":
    dc = DataCollector()
    data = dc.collect_all()
    summary = dc.get_summary()
    print(f"✅ Coleta concluída: {json.dumps(summary, indent=2)}")
