#!/usr/bin/env python3
"""
TFT Suspect Detector v2 - Motor de detecção híbrido.
Combina análise histórica (API Riot) + comportamento em tempo real (Live API / LCU).
Gera score de suspeição e alimenta o banco de dados.
"""
import time, json, threading, urllib.parse
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable
from datetime import datetime
from collections import defaultdict, deque
import statistics
import winsound


class SuspectDetector:
    """Detecta jogadores suspeitos usando análise híbrida."""

    def __init__(self, riot_api=None, lcu_bridge=None, live_api=None, database=None):
        self.riot = riot_api
        self.lcu = lcu_bridge
        self.live = live_api
        self.db = database

        # Configurações
        self.MATCHES_TO_ANALYZE = 15
        self.THRESHOLD_3STAR = 4.0
        self.THRESHOLD_TOP4 = 80
        self.THRESHOLD_WIN_RATE = 60       # Vitórias em 1º lugar
        self.THRESHOLD_APM = 250
        self.THRESHOLD_REACTION = 60
        self.THRESHOLD_CONSISTENCY = 15
        self.THRESHOLD_DANO_MEDIO = 8000   # Dano médio por partida suspeito
        self.THRESHOLD_LEVEL_SPEED = 6     # Level médio muito alto
        self.THRESHOLD_STREAK = 8          # Vitórias consecutivas suspeitas

        # Anti-smurf: contas novas com performance anormal
        self.SMURF_MATCH_THRESHOLD = 30    # Menos que 30 partidas = conta nova
        self.SMURF_WIN_THRESHOLD = 65      # Win rate > 65% em conta nova = smurf/hacker

        self.PESOS = {
            "media_3star": 20,
            "top4_rate": 10,
            "win_rate": 15,
            "apm": 25,
            "tempo_reacao": 10,
            "consistencia": 5,
            "dano_medio": 10,
            "level_speed": 5
        }

        # Cache de histórico
        self.historico_cache = {}
        self.CACHE_MINUTOS = 30

        # Comportamento em tempo real
        self.player_actions = defaultdict(lambda: deque(maxlen=200))

        # Detecções da sessão
        self.detected_hackers: Dict[str, Dict] = {}
        self._meu_puuid: Optional[str] = None
        self._meu_nome: str = ""

        # Callbacks
        self._on_hacker_callbacks: List[Callable] = []

        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None

        # Cache de scan (evita re-escanear mesmos jogadores)
        self._scan_cache: Dict[str, float] = {}
        self._scan_cache_ttl = 120  # segundos antes de re-escanear

    # ----------------------------------------------------------------
    def on_hacker_detected(self, callback: Callable):
        """Callback quando um hacker é detectado."""
        self._on_hacker_callbacks.append(callback)

    def set_me(self, nome: str, puuid: str):
        self._meu_nome = nome
        self._meu_puuid = puuid

    # ----------------------------------------------------------------
    # UTILITÁRIOS
    # ----------------------------------------------------------------
    def _limpar_nome(self, nome: str) -> str:
        if "#" in nome:
            nome = nome.split("#")[0]
        return nome.strip()

    def _alertar(self, tipo: str = "suspeito"):
        try:
            if tipo == "hacker":
                for _ in range(3):
                    winsound.Beep(1000, 200)
                    time.sleep(0.05)
                    winsound.Beep(800, 200)
                    time.sleep(0.1)
            elif tipo == "suspeito":
                for freq, dur in [(400, 300), (300, 500), (200, 700), (800, 400)]:
                    winsound.Beep(freq, dur)
                    time.sleep(0.1)
        except Exception:
            pass

    # ----------------------------------------------------------------
    # ANÁLISE HISTÓRICA (via Riot API)
    # ----------------------------------------------------------------
    def analisar_historico(self, nome: str, puuid: str) -> Optional[Dict]:
        """Analisa histórico de partidas TFT do jogador."""
        if not self.riot or not puuid:
            return None

        # Verifica cache
        if puuid in self.historico_cache:
            cache_time = self.historico_cache[puuid]["timestamp"]
            if (time.time() - cache_time) < (self.CACHE_MINUTOS * 60):
                return self.historico_cache[puuid]["dados"]

        match_ids = self.riot.get_match_ids(puuid, self.MATCHES_TO_ANALYZE)
        if not match_ids:
            return None

        resultados = []
        total_3star = 0
        total_top4 = 0
        total_win = 0
        total_dano = 0
        total_level = 0
        streak_atual = 0
        max_streak = 0
        colocacoes = []

        for mid in match_ids:
            match = self.riot.get_match(mid)
            stats = self.riot.analyze_match_participant(match, puuid)
            if stats:
                resultados.append(stats)
                total_3star += stats["tres_star"]
                if stats["placement"] <= 4:
                    total_top4 += 1
                if stats["placement"] == 1:
                    total_win += 1
                    streak_atual += 1
                    max_streak = max(max_streak, streak_atual)
                else:
                    streak_atual = 0
                total_dano += stats.get("total_damage_to_players", 0)
                total_level += stats.get("level", 0)
                colocacoes.append(stats["placement"])
            time.sleep(0.2)

        if not resultados:
            return None

        n = len(resultados)
        dados = {
            "nome": nome,
            "puuid": puuid,
            "partidas": n,
            "media_3star": round(total_3star / n, 2),
            "top4_rate": round((total_top4 / n) * 100, 1),
            "win_rate": round((total_win / n) * 100, 1),
            "max_3star": max(r["tres_star"] for r in resultados),
            "media_dano": round(total_dano / n, 1) if n > 0 else 0,
            "media_level": round(total_level / n, 1) if n > 0 else 0,
            "max_streak": max_streak,
            "melhor_coloc": min(colocacoes),
            "pior_coloc": max(colocacoes),
            "colocacoes": colocacoes,
            "analisado_em": datetime.now().isoformat()
        }

        # Detecta possível smurf (conta nova com performance alta)
        try:
            summ = self.riot.get_summoner_by_puuid(puuid)
            if summ:
                dados["summoner_level"] = summ.get("summonerLevel", 0)
                dados["revision_date"] = summ.get("revisionDate", 0)
        except Exception:
            pass

        # Salva no cache
        self.historico_cache[puuid] = {"dados": dados, "timestamp": time.time()}
        return dados

    # ----------------------------------------------------------------
    # ANÁLISE DE COMPORTAMENTO (tempo real)
    # ----------------------------------------------------------------
    def registrar_acao(self, player_name: str):
        """Registra uma ação do jogador para análise de APM."""
        self.player_actions[player_name].append(time.time() * 1000)

    def calcular_apm(self, player_name: str, window_seconds: int = 60) -> float:
        if player_name not in self.player_actions:
            return 0
        now = time.time() * 1000
        cutoff = now - (window_seconds * 1000)
        recent = [t for t in self.player_actions[player_name] if t > cutoff]
        return (len(recent) / window_seconds) * 60 if recent else 0

    def calcular_tempo_reacao(self, player_name: str) -> Optional[float]:
        if player_name not in self.player_actions:
            return None
        actions = list(self.player_actions[player_name])
        if len(actions) < 10:
            return None
        diffs = [actions[i] - actions[i-1] for i in range(1, len(actions))
                 if 10 < (actions[i] - actions[i-1]) < 5000]
        return statistics.mean(diffs) if len(diffs) >= 5 else None

    def calcular_consistencia(self, player_name: str) -> Optional[float]:
        if player_name not in self.player_actions:
            return None
        actions = list(self.player_actions[player_name])
        if len(actions) < 15:
            return None
        diffs = [actions[i] - actions[i-1] for i in range(1, len(actions))
                 if 10 < (actions[i] - actions[i-1]) < 5000]
        return statistics.stdev(diffs) if len(diffs) >= 10 else None

    def analisar_comportamento(self, player_name: str) -> Dict:
        apm = self.calcular_apm(player_name)
        tempo_reacao = self.calcular_tempo_reacao(player_name)
        consistencia = self.calcular_consistencia(player_name)

        score_apm = min(100, (apm - self.THRESHOLD_APM) * 2) if apm > self.THRESHOLD_APM else 0
        score_reacao = min(100, (self.THRESHOLD_REACTION - tempo_reacao) * 3) if tempo_reacao and tempo_reacao < self.THRESHOLD_REACTION else 0
        score_consist = min(100, (self.THRESHOLD_CONSISTENCY - consistencia) * 5) if consistencia and consistencia < self.THRESHOLD_CONSISTENCY else 0

        return {
            "apm": round(apm, 1),
            "tempo_reacao": round(tempo_reacao, 1) if tempo_reacao else None,
            "consistencia": round(consistencia, 1) if consistencia else None,
            "scores": {"apm": round(score_apm, 1), "reacao": round(score_reacao, 1),
                       "consistencia": round(score_consist, 1)}
        }

    # ----------------------------------------------------------------
    # SCORE HÍBRIDO
    # ----------------------------------------------------------------
    def calcular_score(self, historico: Optional[Dict], comportamento: Dict) -> Dict:
        """Combina histórico + comportamento em score final.
        Quanto maior o score, mais suspeito o jogador."""
        score_total = 0.0
        metricas = {}
        razoes = []

        if historico:
            # 1. Média de 3★
            ms = historico["media_3star"]
            if ms >= self.THRESHOLD_3STAR:
                s = min(100, (ms - self.THRESHOLD_3STAR) * 20)
                score_total += s * (self.PESOS["media_3star"] / 100)
                metricas["media_3star"] = s
                razoes.append(f"📊 Média 3★: {ms:.1f} (limite: {self.THRESHOLD_3STAR})")

            # 1b. 3★ MAXIMO em UMA partida (>3 = HACKER)
            max_3 = historico.get("max_3star", 0)
            if max_3 >= 3:
                s = min(100, 60 + (max_3 - 3) * 15)
                score_total += s * (self.PESOS["media_3star"] / 100)
                metricas["max_3star"] = s
                razoes.append(f"🚨 {max_3} campeoes 3★ em UMA partida! (HACKER)")

            # 2. Top4 rate
            top4 = historico["top4_rate"]
            if top4 >= self.THRESHOLD_TOP4:
                s = min(100, (top4 - self.THRESHOLD_TOP4) * 3)
                score_total += s * (self.PESOS["top4_rate"] / 100)
                metricas["top4_rate"] = s
                razoes.append(f"🏆 Top4: {top4:.1f}% (limite: {self.THRESHOLD_TOP4}%)")

            # 3. Win rate (1º lugar) - NOVO
            wr = historico.get("win_rate", 0)
            if wr >= self.THRESHOLD_WIN_RATE:
                s = min(100, (wr - self.THRESHOLD_WIN_RATE) * 4)
                score_total += s * (self.PESOS["win_rate"] / 100)
                metricas["win_rate"] = s
                razoes.append(f"🥇 Win rate: {wr:.1f}% (limite: {self.THRESHOLD_WIN_RATE}%)")

            # 4. Dano médio - NOVO
            dano = historico.get("media_dano", 0)
            if dano >= self.THRESHOLD_DANO_MEDIO:
                s = min(100, (dano - self.THRESHOLD_DANO_MEDIO) / 100)
                score_total += s * (self.PESOS["dano_medio"] / 100)
                metricas["dano_medio"] = s
                razoes.append(f"💥 Dano médio: {dano:.0f} (limite: {self.THRESHOLD_DANO_MEDIO})")

            # 5. Velocidade de level - NOVO
            lvl = historico.get("media_level", 0)
            if lvl >= self.THRESHOLD_LEVEL_SPEED:
                s = min(100, (lvl - self.THRESHOLD_LEVEL_SPEED) * 25)
                score_total += s * (self.PESOS["level_speed"] / 100)
                metricas["level_speed"] = s
                razoes.append(f"⬆️ Level médio: {lvl:.1f} (limite: {self.THRESHOLD_LEVEL_SPEED})")

            # 6. Streak de vitórias - NOVO
            streak = historico.get("max_streak", 0)
            if streak >= self.THRESHOLD_STREAK:
                s = min(100, (streak - self.THRESHOLD_STREAK) * 15)
                score_total += s * (self.PESOS["win_rate"] / 100)  # reusa peso win
                metricas["streak"] = s
                razoes.append(f"🔥 Sequência de {streak} vitórias consecutivas")

            # 7. Detecção de Smurf - NOVO
            partidas = historico.get("partidas", 0)
            if partidas < self.SMURF_MATCH_THRESHOLD and wr >= self.SMURF_WIN_THRESHOLD:
                s = 80  # Smurf forte
                score_total += s * 0.10  # peso extra
                metricas["smurf"] = s
                razoes.append(f"🎭 Possível smurf: {partidas} partidas, {wr:.1f}% win rate")

        scores_c = comportamento.get("scores", {})
        if scores_c.get("apm", 0) > 0:
            score_total += scores_c["apm"] * (self.PESOS["apm"] / 100)
            metricas["apm"] = scores_c["apm"]
            if scores_c["apm"] > 30:
                razoes.append(f"⚡ APM: {comportamento['apm']} (limite: {self.THRESHOLD_APM})")

        if scores_c.get("reacao", 0) > 0:
            score_total += scores_c["reacao"] * (self.PESOS["tempo_reacao"] / 100)
            metricas["tempo_reacao"] = scores_c["reacao"]
            if scores_c["reacao"] > 20:
                razoes.append(f"🎯 Reação: {comportamento['tempo_reacao']}ms (limite: {self.THRESHOLD_REACTION}ms)")

        if scores_c.get("consistencia", 0) > 0:
            score_total += scores_c["consistencia"] * (self.PESOS["consistencia"] / 100)
            metricas["consistencia"] = scores_c["consistencia"]
            if scores_c["consistencia"] > 30:
                razoes.append(f"🤖 Consistência robótica: {comportamento['consistencia']:.1f}ms desvio")

        nivel = "BAIXO"
        is_hacker = False
        if score_total >= 80:
            nivel = "CRÍTICO"; is_hacker = True
        elif score_total >= 60:
            nivel = "ALTO"; is_hacker = True
        elif score_total >= 40:
            nivel = "MÉDIO"

        return {
            "score_total": round(score_total, 1),
            "nivel": nivel,
            "is_hacker": is_hacker,
            "metricas": metricas,
            "razoes": razoes,
            "detalhes_comportamento": comportamento
        }

    # ----------------------------------------------------------------
    # ESCANEAMENTO
    # ----------------------------------------------------------------
    def escanear_jogador(self, nome: str, match_id: str = None) -> Dict:
        """Escaneia UM jogador usando método híbrido completo."""
        resultado_padrao = {
            "player": nome, "error": True, "score_total": 0,
            "nivel": "ERRO", "is_hacker": False,
            "razoes": ["Não foi possível analisar"], "metricas": {}
        }

        nome_limpo = self._limpar_nome(nome)

        # Pula próprio jogador
        if nome_limpo.lower() == self._meu_nome.lower():
            resultado_padrao["razoes"] = ["Próprio jogador"]
            return resultado_padrao

        # Busca PUUID via API
        puuid = None
        if self.riot:
            nome_encoded = urllib.parse.quote(nome_limpo)
            summ = self.riot.get_summoner_by_name(nome_encoded)
            if summ:
                puuid = summ.get("puuid")

        if not puuid:
            return resultado_padrao

        # Análise histórica
        historico = self.analisar_historico(nome_limpo, puuid)

        # Comportamento
        comportamento = self.analisar_comportamento(nome_limpo)

        # Score final
        resultado = self.calcular_score(historico, comportamento)
        resultado["player"] = nome_limpo
        resultado["puuid"] = puuid
        resultado["error"] = False
        if historico:
            resultado["historico"] = historico

        # Persiste no banco
        if self.db:
            self.db.add_or_update_suspect(
                puuid, nome_limpo, "",
                resultado["score_total"], resultado["nivel"],
                resultado["is_hacker"]
            )
            if match_id:
                self.db.register_encounter(
                    puuid, match_id,
                    resultado["score_total"], resultado["nivel"],
                    resultado["is_hacker"], resultado
                )

        # Alerta
        if resultado["is_hacker"]:
            self.detected_hackers[nome_limpo] = resultado
            self._alertar("hacker" if resultado["nivel"] == "CRÍTICO" else "suspeito")
            for cb in self._on_hacker_callbacks:
                cb(resultado)

        return resultado

    def escanear_sala(self, jogadores: List[str], match_id: str = None) -> List[Dict]:
        """Escaneia múltiplos jogadores."""
        resultados = []
        for j in jogadores:
            print(f"  🔍 Escaneando: {j}")
            res = self.escanear_jogador(j, match_id)
            resultados.append(res)
            time.sleep(0.5)
        return resultados

    # ================================================================
    # PRÉ-SCAN (LOBBY, ANTES DA PARTIDA)
    # ================================================================
    def prescan_lobby(self, jogadores: List[str]) -> Dict:
        """PRÉ-SCAN rápido do lobby (antes da partida).
        Usa cache do banco + scan limitado a 5 partidas."""
        from datetime import datetime
        resultados = []
        total_risco = 0.0
        alertas = []

        for nome_raw in jogadores:
            nome = self._limpar_nome(nome_raw)
            if nome.lower() == self._meu_nome.lower():
                continue

            puuid = None
            if self.riot:
                try:
                    summ = self.riot.get_summoner_by_name(urllib.parse.quote(nome))
                    puuid = summ.get("puuid") if summ else None
                except:
                    pass

            score = 0
            nivel = "BAIXO"
            is_hacker = False
            fonte = ""

            # 1. Verifica banco local primeiro
            if puuid and self.db:
                sus = self.db.get_suspect(puuid)
                if sus:
                    score = sus.get("max_score", 0)
                    nivel = sus.get("nivel_max", "BAIXO")
                    is_hacker = sus.get("status") == "hacker"
                    fonte = f"banco ({sus.get('total_meets', 1)} encontros)"

            # 2. Se não tem no banco, scan rápido (5 partidas)
            if not fonte and puuid and self.riot:
                old = self.MATCHES_TO_ANALYZE
                self.MATCHES_TO_ANALYZE = 5
                historico = self.analisar_historico(nome, puuid)
                self.MATCHES_TO_ANALYZE = old
                if historico:
                    comp = self.analisar_comportamento(nome)
                    res = self.calcular_score(historico, comp)
                    score = res["score_total"]
                    nivel = res["nivel"]
                    is_hacker = res["is_hacker"]
                    fonte = "scan (5 partidas)"
                    if self.db:
                        self.db.add_or_update_suspect(puuid, nome, "", score, nivel, is_hacker)
                else:
                    fonte = "sem dados"

            resultados.append({
                "player": nome, "puuid": puuid,
                "score": round(score, 1), "nivel": nivel,
                "is_hacker": is_hacker, "fonte": fonte
            })
            total_risco += score

            if is_hacker:
                alertas.append(f"🔴 {nome} — HACKER CONHECIDO (score: {score})")
            elif nivel in ("ALTO", "CRÍTICO"):
                alertas.append(f"🟠 {nome} — Score alto: {score} ({nivel})")

            time.sleep(0.3)

        n = len([r for r in resultados if r["puuid"]])
        return {
            "jogadores": resultados,
            "total_analisados": n,
            "risco_medio": round(total_risco / n, 1) if n > 0 else 0,
            "hacker_encontrado": any(r["is_hacker"] for r in resultados),
            "alertas": alertas,
            "timestamp": datetime.now().isoformat()
        }

    # ----------------------------------------------------------------
    # MONITORAMENTO CONTÍNUO
    # ----------------------------------------------------------------
    def iniciar_monitoramento(self, interval: int = 10):
        """Inicia monitoramento contínuo da sala."""
        if self._monitoring:
            return
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop,
                                                 args=(interval,), daemon=True)
        self._monitor_thread.start()
        print(f"  🤖 Monitoramento contínuo iniciado (a cada {interval}s)")

    def parar_monitoramento(self):
        self._monitoring = False

    def _monitor_loop(self, interval: int):
        while self._monitoring:
            try:
                jogadores = []
                # Tenta Live API primeiro (re-check a cada ciclo)
                if self.live:
                    if not self.live.available:
                        self.live.check()  # Tenta reconectar
                    if self.live.available:
                        players = self.live.get_player_list()
                        jogadores = [p.get("summonerName", "") for p in players
                                     if p.get("summonerName", "").lower() != self._meu_nome.lower()]

                # Fallback: LCU (dados do lobby/pre-jogo)
                if not jogadores and self.lcu and self.lcu.connected:
                    jogadores = [m.get("summonerName", "") for m in self.lcu.get_player_list()]

                if jogadores:
                    agora = time.time()
                    novos = [j for j in jogadores
                             if (agora - self._scan_cache.get(
                                 self._limpar_nome(j), 0))
                             > self._scan_cache_ttl]
                    if novos:
                        res = self.escanear_sala(novos)
                        for j in novos:
                            self._scan_cache[self._limpar_nome(j)] = agora
                        hackers = [r for r in res if r and r.get("is_hacker")]
                        for h in hackers:
                            print(f"  🚨 HACKER: {h['player']} (score: {h['score_total']})")
            except Exception as e:
                print(f"  ⚠️ Erro no monitoramento: {e}")
            time.sleep(interval)

    # ----------------------------------------------------------------
    # RELATÓRIOS
    # ----------------------------------------------------------------
    def get_relatorio(self) -> Dict:
        return {
            "sessao": {
                "hackers_detectados": len(self.detected_hackers),
                "jogadores_observados": len(self.player_actions),
            },
            "banco": self.db.get_summary() if self.db else {},
            "hackers": list(self.detected_hackers.keys())
        }


if __name__ == "__main__":
    print("Suspect Detector - Execute via main.py")
