#!/usr/bin/env python3
"""
Analytics & Metrics - Gera relatórios, gráficos e métricas do sistema.
Alimenta o dashboard web com dados processados.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


class MetricsEngine:
    """Motor de métricas e relatórios do TFTFlyway."""

    def __init__(self, database=None):
        self.db = database
        self.reports_dir = Path("data/reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------
    def generate_daily_report(self) -> Dict:
        """Gera relatório diário com métricas resumidas."""
        if not self.db:
            return {"error": "Database not connected"}

        summary = self.db.get_summary()
        suspects = self.db.get_all_suspects("MÉDIO")
        hackers = self.db.get_hackers_only()
        encounters = self.db.get_encounters(limit=20)

        report = {
            "gerado_em": datetime.now().isoformat(),
            "periodo": "últimas 24h",
            "resumo": summary,
            "hackers_confirmados": len(hackers),
            "suspeitos_ativos": len(suspects),
            "top_suspeitos": suspects[:10],
            "ultimos_encontros": encounters[:10],
            "stats": self._calculate_stats(suspects, encounters)
        }

        # Salva relatório
        report_file = self.reports_dir / f"report_{datetime.now().strftime('%Y%m%d')}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return report

    def _calculate_stats(self, suspects: List, encounters: List) -> Dict:
        """Calcula estatísticas básicas."""
        scores = [s.get("max_score", 0) for s in suspects]
        return {
            "media_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "total_encontros_hoje": len(encounters),
            "taxa_hackers": round(
                (sum(1 for s in suspects if s.get("status") == "hacker") / len(suspects) * 100)
                if suspects else 0, 1
            )
        }

    # ----------------------------------------------------------------
    def get_chart_data(self) -> Dict:
        """Dados formatados para gráficos do dashboard."""
        if not self.db:
            return {}

        suspects = self.db.get_recent_suspects(2) if hasattr(self.db, "get_recent_suspects") else self.db.get_all_suspects()
        encounters = self.db.get_encounters(limit=100)
        metrics = self.db.get_metrics_history(30)

        # Distribuição por nível
        nivel_dist = {"BAIXO": 0, "MÉDIO": 0, "ALTO": 0, "CRÍTICO": 0}
        for s in suspects:
            nl = s.get("nivel_max", "BAIXO")
            if nl in nivel_dist:
                nivel_dist[nl] += 1

        # Encontros por dia (últimos 30)
        daily_encounters = {}
        for e in encounters:
            day = e.get("encounter_date", "")[:10]
            if day:
                daily_encounters[day] = daily_encounters.get(day, 0) + 1

        # Top suspeitos por score
        top_suspects = sorted(suspects, key=lambda x: x.get("max_score", 0), reverse=True)[:10]

        # Scores ao longo do tempo (dos encontros)
        score_timeline = [
            {"date": e.get("encounter_date", ""), "score": e.get("score", 0), "name": e.get("summoner_name", "?")}
            for e in encounters if e.get("score", 0) > 0
        ]

        return {
            "nivel_distribution": nivel_dist,
            "daily_encounters": [{"date": d, "count": c} for d, c in sorted(daily_encounters.items())],
            "top_suspects": [
                {"name": s.get("summoner_name", "?"), "score": s.get("max_score", 0),
                 "nivel": s.get("nivel_max", "?"), "meets": s.get("total_meets", 0)}
                for s in top_suspects
            ],
            "score_timeline": score_timeline[-50:],  # Últimos 50
            "metrics_history": [
                {"date": m.get("date", ""), "hackers": m.get("hackers_found", 0),
                 "suspects": m.get("suspects_found", 0), "matches": m.get("total_matches", 0)}
                for m in metrics
            ]
        }

    # ----------------------------------------------------------------
    def export_json(self, filepath: str = None) -> str:
        """Exporta dados completos para JSON."""
        if not filepath:
            filepath = self.reports_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        data = {
            "exportado_em": datetime.now().isoformat(),
            "chart_data": self.get_chart_data(),
            "suspeitos": self.db.get_recent_suspects(2) if self.db and hasattr(self.db, "get_recent_suspects") else (self.db.get_all_suspects() if self.db else []),
            "encontros": self.db.get_encounters(limit=500) if self.db else [],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return str(filepath)

    # ----------------------------------------------------------------
    def get_dashboard_json(self) -> str:
        """Gera JSON completo para o dashboard web."""
        data = {
            "summary": self.db.get_summary() if self.db else {},
            "chart_data": self.get_chart_data(),
            "hackers": self.db.get_hackers_only() if self.db else [],
            "suspeitos": self.db.get_recent_suspects(2) if self.db and hasattr(self.db, "get_recent_suspects") else (self.db.get_all_suspects() if self.db else []),
            "encontros": self.db.get_encounters(limit=100) if self.db else [],
            "last_update": datetime.now().isoformat()
        }
        return json.dumps(data, ensure_ascii=False)


if __name__ == "__main__":
    print("Metrics Engine - Execute via main.py")
