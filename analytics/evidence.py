#!/usr/bin/env python3
"""
Evidence Report - Gera relatorios detalhados de hackers para report a Riot.
Salva tudo que o detector encontrou + dados de partida para anexar no ticket.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class EvidenceReport:
    """Gera relatorios de evidencias anti-cheat."""

    def __init__(self, database=None, output_dir: str = "data/evidence"):
        self.db = database
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------
    def generate(self, hacker_data: Dict, match_info: Dict = None) -> str:
        """Gera relatorio completo de evidencias para um hacker."""
        now = datetime.now()
        player = hacker_data.get("player", "desconhecido")
        puuid = hacker_data.get("puuid", "N/A")
        score = hacker_data.get("score_total", 0)
        nivel = hacker_data.get("nivel", "N/A")

        # Busca dados extras do banco
        db_extra = {}
        if self.db and puuid and puuid != "N/A":
            suspect = self.db.get_suspect(puuid)
            if suspect:
                db_extra = suspect
                encounters = self.db.get_encounters(puuid, limit=10)

        report = {
            "meta": {
                "gerado_em": now.isoformat(),
                "sistema": "TFTFlyway v1.0",
                "tipo": "Relatorio de Evidencias Anti-Cheat"
            },
            "jogador": {
                "nome": player,
                "puuid": puuid,
                "score": score,
                "nivel": nivel,
                "is_hacker": hacker_data.get("is_hacker", False),
                "razoes": hacker_data.get("razoes", []),
                "total_encontros": db_extra.get("total_meets", 0) if db_extra else 0,
                "primeira_vez": db_extra.get("first_seen", "N/A") if db_extra else "N/A",
                "ultima_vez": db_extra.get("last_seen", "N/A") if db_extra else "N/A"
            },
            "metricas_deteccao": {
                "score_total": score,
                "nivel_suspeita": nivel,
                "media_3star": hacker_data.get("metricas", {}).get("media_3star", 0),
                "max_3star": hacker_data.get("metricas", {}).get("max_3star", 0),
                "win_rate": hacker_data.get("metricas", {}).get("win_rate", 0),
                "top4_rate": hacker_data.get("metricas", {}).get("top4_rate", 0),
                "apm": hacker_data.get("detalhes_comportamento", {}).get("apm", 0),
                "tempo_reacao_ms": hacker_data.get("detalhes_comportamento", {}).get("tempo_reacao", 0),
                "consistencia_ms": hacker_data.get("detalhes_comportamento", {}).get("consistencia", 0),
            },
            "historico_partidas": hacker_data.get("historico", {}),
            "encontros_anteriores": [],
            "instrucoes_report": {
                "passo_1": "Acesse: https://support.riotgames.com/hc/pt-br",
                "passo_2": "Selecione: Reportar um Jogador",
                "passo_3": f"Informe o Riot ID: {player}",
                "passo_4": f"Informe o PUUID: {puuid}",
                "passo_5": "Anexe este arquivo como evidencia",
                "categoria": "Cheating / Scripting / Botting",
                "detalhes_sugeridos": (
                    f"Jogador detectado pelo TFTFlyway Anti-Cheat.\n"
                    f"Score de suspeicao: {score}/100 (nivel {nivel}).\n"
                    f"Razoes: {'; '.join(hacker_data.get('razoes', []))}\n"
                    f"3 estrelas por partida: {hacker_data.get('metricas', {}).get('media_3star', 0):.1f}\n"
                    f"Max 3★ em uma partida: {hacker_data.get('metricas', {}).get('max_3star', 0)}\n"
                    f"APM detectado: {hacker_data.get('detalhes_comportamento', {}).get('apm', 0)}"
                )
            }
        }

        # Adiciona encontros anteriores se houver
        if db_extra and 'encounters' in locals():
            for enc in encounters:
                report["encontros_anteriores"].append({
                    "data": enc.get("encounter_date", ""),
                    "score": enc.get("score", 0),
                    "nivel": enc.get("nivel", ""),
                    "match_id": enc.get("match_id", "")
                })

        # Salva arquivo
        nome_arquivo = f"evidencia_{player}_{now.strftime('%Y%m%d_%H%M%S')}.json"
        caminho = self.output_dir / nome_arquivo
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # Gera versao TXT legivel
        txt_path = self.output_dir / nome_arquivo.replace(".json", ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(self._format_txt(report))

        return str(caminho)

    # ----------------------------------------------------------------
    def generate_for_suspect(self, puuid: str, player_name: str) -> Optional[str]:
        """Gera relatorio de evidencias para um suspeito ja no banco."""
        if not self.db:
            return None
        sus = self.db.get_suspect(puuid)
        if not sus:
            return None
        hacker_data = {
            "player": player_name or sus.get("summoner_name", "?"),
            "puuid": puuid,
            "score_total": sus.get("max_score", 0),
            "nivel": sus.get("nivel_max", "BAIXO"),
            "is_hacker": sus.get("status") == "hacker",
            "razoes": [f"Score maximo: {sus.get('max_score', 0)}"],
            "metricas": {},
            "detalhes_comportamento": {},
            "historico": {}
        }
        return self.generate(hacker_data)

    # ----------------------------------------------------------------
    def _format_txt(self, report: Dict) -> str:
        """Formata o relatorio em TXT legivel."""
        j = report["jogador"]
        m = report["metricas_deteccao"]
        inst = report["instrucoes_report"]

        txt = f"""
{'='*60}
   🛡️ TFTFLYWAY - RELATORIO DE EVIDENCIAS ANTI-CHEAT
{'='*60}

GERADO EM: {report['meta']['gerado_em']}
SISTEMA:   {report['meta']['sistema']}

{'='*60}
DADOS DO JOGADOR SUSPEITO
{'='*60}

  Nome:        {j['nome']}
  PUUID:       {j['puuid']}
  Score:       {j['score']}/100
  Nivel:       {j['nivel']}
  Hacker:      {'SIM 🚨' if j['is_hacker'] else 'NAO'}
  Encontros:   {j['total_encontros']}
  1a vez:      {j['primeira_vez']}
  Ultima vez:  {j['ultima_vez']}

RAZOES DA DETECCAO:
"""
        for r in j.get("razoes", []):
            txt += f"  • {r}\n"

        txt += f"""
{'='*60}
METRICAS DE DETECCAO
{'='*60}

  Score total:           {m['score_total']}/100
  Nivel de suspeita:     {m['nivel_suspeita']}
  Media 3★ por partida: {m['media_3star']}
  Max 3★ em 1 partida:  {m['max_3star']}
  Win rate:              {m['win_rate']}%
  Top 4 rate:            {m['top4_rate']}%
  APM (acoes/min):       {m['apm']}
  Tempo reacao (ms):    {m['tempo_reacao_ms']}
  Consistencia (ms):    {m['consistencia_ms']}

{'='*60}
INSTRUCOES PARA REPORT A RIOT
{'='*60}

  1. {inst['passo_1']}
  2. {inst['passo_2']}
  3. {inst['passo_3']}
  4. {inst['passo_4']}
  5. {inst['passo_5']}

  Categoria: {inst['categoria']}

  DETALHES SUGERIDOS:
  {inst['detalhes_sugeridos']}

{'='*60}
   RELATORIO GERADO AUTOMATICAMENTE PELO TFTFLYWAY
   https://github.com/10jsc/TFTFlyway
{'='*60}
"""
        return txt

    # ----------------------------------------------------------------
    def list_evidence(self) -> List[Dict]:
        """Lista todos os relatorios de evidencias gerados."""
        files = []
        for f in sorted(self.output_dir.glob("evidencia_*.json")):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
                files.append({
                    "arquivo": f.name,
                    "jogador": data.get("jogador", {}).get("nome", "?"),
                    "score": data.get("jogador", {}).get("score", 0),
                    "data": data.get("meta", {}).get("gerado_em", "?"),
                })
            except Exception:
                pass
        return files


if __name__ == "__main__":
    ev = EvidenceReport()
    print(f"Pasta de evidencias: {ev.output_dir}")
    print(f"Relatorios existentes: {len(ev.list_evidence())}")
