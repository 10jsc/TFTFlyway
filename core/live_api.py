#!/usr/bin/env python3
"""
Live Client API - Conexão com a API de dados ao vivo do LoL (porta 2999).
Fornece dados em tempo real durante a partida: gold, level, itens, etc.
"""
import requests, time
from typing import Optional, Dict, List, Any
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LiveAPI:
    """Acessa a Live Client Data API durante a partida."""

    def __init__(self, host: str = "127.0.0.1", port: int = 2999):
        self.base_url = f"https://{host}:{port}"
        self.session = requests.Session()
        self.session.verify = False
        self._available = False

    # ----------------------------------------------------------------
    def check(self) -> bool:
        """Verifica se a Live API está respondendo."""
        try:
            r = self.session.get(f"{self.base_url}/liveclientdata/activeplayer", timeout=2)
            self._available = r.status_code == 200
            return self._available
        except Exception:
            self._available = False
            return False

    @property
    def available(self) -> bool:
        return self._available

    # ----------------------------------------------------------------
    # ENDPOINTS
    # ----------------------------------------------------------------
    def get_active_player(self) -> Optional[Dict]:
        """Dados do jogador ativo (gold, level, campeão)."""
        return self._get("/liveclientdata/activeplayer")

    def get_player_list(self) -> List[Dict]:
        """Lista de todos os jogadores na partida."""
        data = self._get("/liveclientdata/playerlist")
        return data if isinstance(data, list) else []

    def get_gold(self) -> Optional[float]:
        """Ouro atual do jogador."""
        data = self.get_active_player()
        if data:
            return data.get("currentGold")
        return None

    def get_level(self) -> Optional[int]:
        """Nível atual do jogador."""
        data = self.get_active_player()
        if data:
            return data.get("level")
        return None

    def get_all_players_summary(self) -> List[Dict]:
        """Resumo de todos os jogadores na partida."""
        players = self.get_player_list()
        summary = []
        for p in players:
            summary.append({
                "name": p.get("summonerName", "?"),
                "champion": p.get("championName", "?"),
                "team": p.get("team", "?"),
                "position": p.get("position", "?"),
                "level": p.get("level", 0),
                "items": p.get("items", []),
                "scores": p.get("scores", {}),
            })
        return summary

    # ----------------------------------------------------------------
    def _get(self, endpoint: str) -> Any:
        try:
            r = self.session.get(f"{self.base_url}{endpoint}", timeout=2)
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None

    def close(self):
        self.session.close()
        self._available = False


if __name__ == "__main__":
    live = LiveAPI()
    if live.check():
        print("✅ Live API disponível!")
        print(f"Gold: {live.get_gold()}")
        print(f"Level: {live.get_level()}")
    else:
        print("❌ Live API não respondendo. Jogo está rodando?")
