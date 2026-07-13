#!/usr/bin/env python3
"""
LCU Bridge - Conexão com o cliente do League of Legends via lockfile.
Fornece acesso à API local do cliente (LCU) para obter dados da partida.
"""
import json, time, os, requests
from pathlib import Path
from typing import Optional, Dict, Any, List
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LCUBridge:
    """Conecta ao League Client via lockfile e expõe endpoints."""

    def __init__(self, lockfile_path: str = None):
        self.lockfile_path = lockfile_path or r"F:\Riot Games\League of Legends\lockfile"
        self.port: Optional[int] = None
        self.token: Optional[str] = None
        self.pid: Optional[int] = None
        self.protocol: str = "https"
        self.session = requests.Session()
        self.session.verify = False
        self._connected = False

    # ----------------------------------------------------------------
    def connect(self) -> bool:
        """Lê o lockfile e configura autenticação."""
        if not os.path.exists(self.lockfile_path):
            return False
        try:
            with open(self.lockfile_path) as f:
                parts = f.read().strip().split(':')
                if len(parts) >= 4:
                    self.protocol = parts[0]  # "riot"
                    self.pid = int(parts[1])
                    self.port = int(parts[2])
                    self.token = parts[3]
                    self.session.auth = ("riot", self.token)

                    # Testa conexão
                    r = self.session.get(
                        f"https://127.0.0.1:{self.port}/lol-summoner/v1/current-summoner",
                        timeout=3
                    )
                    self._connected = r.status_code == 200
                    return self._connected
        except Exception:
            pass
        return False

    @property
    def connected(self) -> bool:
        return self._connected

    # ----------------------------------------------------------------
    # ENDPOINTS DA LCU
    # ----------------------------------------------------------------
    def get_current_summoner(self) -> Optional[Dict]:
        """Dados do invocador logado."""
        return self._get("/lol-summoner/v1/current-summoner")

    def get_gameflow_phase(self) -> Optional[str]:
        """Fase atual: Lobby, Matchmaking, InGame, etc."""
        return self._get("/lol-gameflow/v1/gameflow-phase")

    def get_player_list(self) -> List[Dict]:
        """Lista de jogadores na sala/pré-jogo."""
        data = self._get("/lol-lobby/v2/lobby/members")
        return data if isinstance(data, list) else []

    def get_all_summoner_data(self) -> Dict:
        """Dados combinados do invocador."""
        result = {"connected": self._connected}
        if not self._connected:
            return result
        result["summoner"] = self.get_current_summoner()
        result["phase"] = self.get_gameflow_phase()
        result["lobby"] = self.get_player_list()
        return result

    def wait_for_game_start(self, callback=None, interval=2):
        """Aguarda a partida começar. Chama callback a cada mudança de fase."""
        last_phase = ""
        while True:
            phase = self.get_gameflow_phase()
            if phase and phase != last_phase:
                last_phase = phase
                if callback:
                    callback(phase)
                if phase in ("InGame", "InProgress"):
                    return phase
            time.sleep(interval)

    # ----------------------------------------------------------------
    # INTERNO
    # ----------------------------------------------------------------
    def _get(self, endpoint: str) -> Any:
        if not self._connected:
            return None
        try:
            r = self.session.get(
                f"https://127.0.0.1:{self.port}{endpoint}",
                timeout=3
            )
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None

    def _post(self, endpoint: str, data: dict = None) -> Any:
        if not self._connected:
            return None
        try:
            r = self.session.post(
                f"https://127.0.0.1:{self.port}{endpoint}",
                json=data or {},
                timeout=3
            )
            return r.json() if r.status_code in (200, 201) else None
        except Exception:
            return None

    def close(self):
        self.session.close()
        self._connected = False


if __name__ == "__main__":
    lcu = LCUBridge()
    if lcu.connect():
        print(f"✅ Conectado ao LCU na porta {lcu.port}")
        data = lcu.get_all_summoner_data()
        print(json.dumps(data, indent=2, default=str))
    else:
        print("❌ LCU não disponível. League of Legends está aberto?")
