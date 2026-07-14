#!/usr/bin/env python3
"""
LCU Bridge - Conexão com o cliente do League of Legends via lockfile.
Fornece acesso à API local do cliente (LCU) para obter dados da partida.
Apenas endpoints de comunicação e anti-cheat - sem automação de jogo.
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
                    self.protocol = parts[0]
                    self.pid = int(parts[1])
                    self.port = int(parts[2])
                    self.token = parts[3]
                    self.session.auth = ("riot", self.token)
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
    def get_current_summoner(self) -> Optional[Dict]:
        return self._get("/lol-summoner/v1/current-summoner")

    def get_gameflow_phase(self) -> Optional[str]:
        return self._get("/lol-gameflow/v1/gameflow-phase")

    def get_player_list(self) -> List[Dict]:
        data = self._get("/lol-lobby/v2/lobby/members")
        return data if isinstance(data, list) else []

    def get_all_summoner_data(self) -> Dict:
        result = {"connected": self._connected}
        if not self._connected:
            return result
        result["summoner"] = self.get_current_summoner()
        result["phase"] = self.get_gameflow_phase()
        result["lobby"] = self.get_player_list()
        return result

    def wait_for_game_start(self, callback=None, interval=2):
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

    def leave_lobby(self) -> bool:
        """Dodge: sai do lobby atual para evitar hacker na sala."""
        try:
            if not self._connected:
                return False
            r = self.session.post(
                f"https://127.0.0.1:{self.port}/lol-lobby/v2/lobby/leave",
                timeout=3
            )
            return r.status_code in (200, 201, 204)
        except Exception:
            return False

    # ----------------------------------------------------------------
    def _get(self, endpoint: str) -> Any:
        if not self._connected:
            return None
        try:
            r = self.session.get(
                f"https://127.0.0.1:{self.port}{endpoint}", timeout=3
            )
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None

    def close(self):
        self.session.close()
        self._connected = False


if __name__ == "__main__":
    lcu = LCUBridge()
    if lcu.connect():
        print(f"Conectado ao LCU na porta {lcu.port}")
        data = lcu.get_all_summoner_data()
        print(json.dumps(data, indent=2, default=str))
    else:
        print("LCU nao disponivel. League of Legends esta aberto?")
