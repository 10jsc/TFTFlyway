#!/usr/bin/env python3
"""
Riot API - Conexão com a API oficial da Riot Games.
Fornece acesso a dados de summoner, partidas, e histórico.
"""
import requests, time, json
from typing import Optional, Dict, List, Any
from pathlib import Path
from datetime import datetime


class RiotAPI:
    """Wrapper para a Riot Games API com rate limiting e cache."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"X-Riot-Token": api_key or ""})
        self._last_request = 0
        self._min_interval = 0.3  # ~20 requests/min (limite desenvolvimento)

    # ----------------------------------------------------------------
    def set_key(self, api_key: str):
        """Define/chave de API."""
        self.api_key = api_key
        self.session.headers.update({"X-Riot-Token": api_key})

    def _rate_limit(self):
        """Rate limiting básico."""
        elapsed = time.time() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.time()

    # ----------------------------------------------------------------
    # CONTAS / SUMMONER
    # ----------------------------------------------------------------
    def get_account_by_riot_id(self, game_name: str, tag_line: str,
                                region: str = "americas") -> Optional[Dict]:
        """Obtém dados da conta por Riot ID (ex: Jogador#BR1)."""
        self._rate_limit()
        url = (f"https://{region}.api.riotgames.com/riot/account/v1/accounts/"
               f"by-riot-id/{game_name}/{tag_line}")
        return self._get(url)

    def get_summoner_by_puuid(self, puuid: str, region: str = "br1") -> Optional[Dict]:
        """Obtém dados do invocador pelo PUUID."""
        self._rate_limit()
        url = (f"https://{region}.api.riotgames.com/lol/summoner/v4/"
               f"summoners/by-puuid/{puuid}")
        return self._get(url)

    def get_summoner_by_name(self, name: str, region: str = "br1") -> Optional[Dict]:
        """Obtém dados do invocador pelo nome."""
        self._rate_limit()
        import urllib.parse
        name_encoded = urllib.parse.quote(name)
        url = (f"https://{region}.api.riotgames.com/lol/summoner/v4/"
               f"summoners/by-name/{name_encoded}")
        return self._get(url)

    # ----------------------------------------------------------------
    # PARTIDAS TFT
    # ----------------------------------------------------------------
    def get_match_ids(self, puuid: str, count: int = 10,
                       region: str = "americas") -> List[str]:
        """Obtém IDs das últimas N partidas TFT."""
        self._rate_limit()
        url = (f"https://{region}.api.riotgames.com/tft/match/v1/matches/"
               f"by-puuid/{puuid}/ids?count={count}")
        data = self._get(url)
        return data if isinstance(data, list) else []

    def get_match(self, match_id: str, region: str = "americas") -> Optional[Dict]:
        """Obtém dados completos de uma partida TFT."""
        self._rate_limit()
        url = (f"https://{region}.api.riotgames.com/tft/match/v1/matches/{match_id}")
        return self._get(url)

    def analyze_match_participant(self, match: Dict, target_puuid: str) -> Optional[Dict]:
        """Extrai dados de UM participante específico de uma partida."""
        if not match:
            return None
        participants = match.get("info", {}).get("participants", [])
        for p in participants:
            if p.get("puuid") == target_puuid:
                units = p.get("units", [])
                tres_star = sum(1 for u in units if u.get("tier", 0) == 3)
                return {
                    "placement": p.get("placement", 0),
                    "level": p.get("level", 0),
                    "gold_left": p.get("gold_left", 0),
                    "last_round": p.get("last_round", 0),
                    "total_damage_to_players": p.get("total_damage_to_players", 0),
                    "tres_star": tres_star,
                    "units": [{"name": u.get("character_id", "?"),
                               "tier": u.get("tier", 0),
                               "items": u.get("itemNames", [])} for u in units]
                }
        return None

    def get_player_match_history(self, puuid: str, count: int = 10,
                                  region_account: str = "americas",
                                  region_game: str = "br1") -> Dict:
        """Análise completa do histórico de um jogador."""
        # 1. Busca match IDs
        match_ids = self.get_match_ids(puuid, count, region_account)

        resultados = []
        total_3star = 0
        total_top4 = 0

        for mid in match_ids:
            match = self.get_match(mid, region_account)
            stats = self.analyze_match_participant(match, puuid)
            if stats:
                resultados.append(stats)
                total_3star += stats["tres_star"]
                if stats["placement"] <= 4:
                    total_top4 += 1
            time.sleep(0.2)

        n = len(resultados)
        return {
            "partidas_analisadas": n,
            "media_3star": round(total_3star / n, 2) if n > 0 else 0,
            "top4_rate": round((total_top4 / n) * 100, 1) if n > 0 else 0,
            "max_3star": max((r["tres_star"] for r in resultados), default=0),
            "melhor_colocacao": min((r["placement"] for r in resultados), default=0),
            "partidas": resultados,
            "analisado_em": datetime.now().isoformat()
        }

    def get_live_match(self, puuid: str, region: str = "americas") -> Optional[Dict]:
        """Verifica se o jogador está em uma partida ao vivo."""
        self._rate_limit()
        url = (f"https://{region}.api.riotgames.com/lol/spectator/tft/v5/"
               f"active-games/by-summoner/{puuid}")
        return self._get(url)

    # ----------------------------------------------------------------
    def _get(self, url: str) -> Any:
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:
                retry = int(r.headers.get("Retry-After", 5))
                print(f"⚠️ Rate limited. Aguardando {retry}s...")
                time.sleep(retry)
                return self._get(url)
            return None
        except Exception as e:
            print(f"❌ Erro na requisição: {e}")
            return None

    def close(self):
        self.session.close()


if __name__ == "__main__":
    api = RiotApi()
    key = input("🔑 Digite sua Riot API Key: ").strip()
    api.set_key(key)

    game_name = input("Riot ID: ").strip()
    tag_line = input("Tagline: ").strip()
    account = api.get_account_by_riot_id(game_name, tag_line)
    if account:
        print(f"✅ Conta encontrada! PUUID: {account['puuid'][:20]}...")
    else:
        print("❌ Conta não encontrada.")
