#!/usr/bin/env python3
"""
Player Tracker - Rastreia jogadores em partidas TFT.
Monitora reserva, board, gold, level e composição dos oponentes.
Alimenta o detector com dados comportamentais para análise anti-cheat.
"""
import json, time, threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from collections import defaultdict, deque


class PlayerTracker:
    """Rastreia jogadores e seus dados durante a partida TFT."""

    def __init__(self, live_api=None, lcu_bridge=None, log_dir: str = "data/tracking"):
        self.live = live_api
        self.lcu = lcu_bridge
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Dados dos jogadores na partida atual
        self.players: Dict[str, Dict] = {}
        self.match_id: str = ""
        self.match_start: Optional[float] = None

        # Histórico de snapshots (para análise de APM e padrões)
        self.snapshots: List[Dict] = []
        self.max_snapshots = 300  # ~5 min com intervalo de 1s

        # Padrões suspeitos detectados
        self.suspicious_patterns: Dict[str, List[Dict]] = defaultdict(list)

        # Callbacks
        self._on_snapshot_callbacks: List[Callable] = []
        self._on_suspicious_callbacks: List[Callable] = []

        # Threading
        self._tracking = False
        self._thread: Optional[threading.Thread] = None
        self._interval = 2.0  # segundos entre snapshots

        # Config de detecção
        self.config = {
            "apm_threshold": 250,       # Ações por minuto suspeito
            "gold_anomaly_threshold": 15, # Variação de gold suspeita
            "level_up_time_threshold": 30, # Tempo mínimo entre level ups (segundos)
            "reaction_threshold_ms": 100,  # Tempo de reação mínimo suspeito (ms)
        }

    @property
    def tracking(self) -> bool:
        return self._tracking

    # ----------------------------------------------------------------
    def on_snapshot(self, callback: Callable):
        self._on_snapshot_callbacks.append(callback)

    def on_suspicious(self, callback: Callable):
        self._on_suspicious_callbacks.append(callback)

    # ----------------------------------------------------------------
    def take_snapshot(self) -> Optional[Dict]:
        """Captura um snapshot do estado atual de todos os jogadores."""
        if not self.live or not self.live.available:
            return None

        snapshot = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "players": []
        }

        player_list = self.live.get_player_list()
        for p in player_list:
            name = p.get("summonerName", "?")
            # Remove #
            if "#" in name:
                name = name.split("#")[0]

            player_data = {
                "name": name,
                "champion": p.get("championName", "?"),
                "level": p.get("level", 0),
                "team": p.get("team", "?"),
                "items": p.get("items", []),
                "scores": p.get("scores", {}),
            }

            # Se é o jogador ativo, pega gold
            active = self.live.get_active_player()
            if active and active.get("summonerName", "").lower() == name.lower():
                player_data["gold"] = active.get("currentGold", 0)
                player_data["level"] = active.get("level", 0)
                player_data["champion"] = active.get("championName", player_data["champion"])

            snapshot["players"].append(player_data)

        self.snapshots.append(snapshot)
        if len(self.snapshots) > self.max_snapshots:
            self.snapshots.pop(0)

        # Analisa padrões suspeitos
        self._analyze_snapshot(snapshot)

        for cb in self._on_snapshot_callbacks:
            cb(snapshot)

        return snapshot

    # ----------------------------------------------------------------
    def _analyze_snapshot(self, snapshot: Dict):
        """Analisa snapshot em busca de padrões suspeitos."""
        for player in snapshot["players"]:
            name = player["name"]
            patterns = []

            # 1. Verifica velocidade de level up (muito rápido?)
            level_history = self._get_player_history(name, "level")
            if len(level_history) >= 3:
                recent = level_history[-3:]
                if all(l >= 7 for l in recent):  # Level alto muito cedo
                    patterns.append({
                        "type": "level_anomaly",
                        "detail": f"Level {recent[-1]} muito cedo",
                        "confidence": 0.6
                    })

            # 2. Verifica gold suspeito (muito gold sem fonte clara)
            gold = player.get("gold", 0)
            if gold > 50 and self._get_match_elapsed() < 180:  # >50 gold nos primeiros 3 min
                patterns.append({
                    "type": "gold_anomaly",
                    "detail": f"Gold elevado: {gold}",
                    "confidence": 0.5
                })

            # 3. Verifica composição suspeita (muitos 3 estrelas cedo)
            # (essa análise será feita via API depois da partida)

            if patterns:
                self.suspicious_patterns[name].extend(patterns)
                for cb in self._on_suspicious_callbacks:
                    cb({"player": name, "patterns": patterns, "snapshot": snapshot})

    def _get_player_history(self, name: str, key: str) -> List:
        """Retorna histórico de um campo específico para um jogador."""
        values = []
        for snap in self.snapshots[-20:]:  # Últimos 20 snapshots
            for p in snap.get("players", []):
                pname = p.get("name", "")
                if "#" in pname:
                    pname = pname.split("#")[0]
                if pname.lower() == name.lower() and key in p:
                    values.append(p[key])
        return values

    def _get_match_elapsed(self) -> float:
        """Tempo decorrido da partida em segundos."""
        if self.match_start:
            return time.time() - self.match_start
        return 0

    # ----------------------------------------------------------------
    # ANÁLISE COMPORTAMENTAL AGREGADA
    # ----------------------------------------------------------------
    def analyze_player_behavior(self, player_name: str) -> Dict:
        """Analisa comportamento de um jogador durante a partida."""
        result = {
            "player": player_name,
            "metrics": {},
            "patterns": [],
            "is_suspicious": False
        }

        # APM estimado (mudanças de estado por minuto)
        name_variations = []
        if "#" in player_name:
            name_variations.append(player_name.split("#")[0])
        name_variations.append(player_name)

        player_snaps = []
        for snap in self.snapshots:
            for p in snap.get("players", []):
                pname = p.get("name", "")
                if "#" in pname:
                    pname = pname.split("#")[0]
                if pname.lower() == player_name.lower():
                    player_snaps.append(p)

        if len(player_snaps) >= 10:
            # Calcula taxa de mudança de itens/nível
            changes = 0
            for i in range(1, len(player_snaps)):
                if (player_snaps[i].get("level", 0) != player_snaps[i-1].get("level", 0) or
                    player_snaps[i].get("items", []) != player_snaps[i-1].get("items", [])):
                    changes += 1

            elapsed_min = len(self.snapshots) * self._interval / 60
            apm = changes / elapsed_min if elapsed_min > 0 else 0

            result["metrics"]["estimated_apm"] = round(apm, 1)
            result["metrics"]["snapshots"] = len(player_snaps)
            result["is_suspicious"] = apm > self.config["apm_threshold"]

            if apm > self.config["apm_threshold"]:
                result["patterns"].append({
                    "type": "high_apm",
                    "detail": f"APM estimado: {apm:.1f} (threshold: {self.config['apm_threshold']})",
                    "confidence": min(1.0, apm / 500)
                })

        # Padrões suspeitos detectados durante a partida
        if player_name in self.suspicious_patterns:
            result["patterns"].extend(self.suspicious_patterns[player_name])

        result["is_suspicious"] = any(
            p.get("confidence", 0) > 0.7 for p in result["patterns"]
        ) or result.get("metrics", {}).get("estimated_apm", 0) > self.config["apm_threshold"]

        return result

    # ----------------------------------------------------------------
    # CONTROLE
    # ----------------------------------------------------------------
    def start_tracking(self, interval: float = 2.0):
        """Inicia rastreamento contínuo."""
        if self._tracking:
            return

        self._interval = interval
        self._tracking = True
        self.match_start = time.time()
        self._thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self._thread.start()

    def stop_tracking(self):
        self._tracking = False
        self._save_session()

    def _tracking_loop(self):
        while self._tracking:
            try:
                self.take_snapshot()
            except Exception as e:
                pass
            time.sleep(self._interval)

    def _save_session(self):
        """Salva dados da sessão de rastreamento."""
        if not self.snapshots:
            return

        session_data = {
            "match_id": self.match_id,
            "duration": self._get_match_elapsed(),
            "total_snapshots": len(self.snapshots),
            "players_tracked": len(self.players),
            "suspicious_patterns": dict(self.suspicious_patterns),
            "snapshots": self.snapshots[-50:],  # Últimos 50 apenas
        }

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = self.log_dir / f"tracking_{ts}.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False, default=str)

    def reset(self):
        """Reseta dados para nova partida."""
        self.snapshots.clear()
        self.suspicious_patterns.clear()
        self.players.clear()
        self.match_start = time.time()


if __name__ == "__main__":
    print("Player Tracker - Execute via main.py")
