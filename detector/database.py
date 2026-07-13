#!/usr/bin/env python3
"""
Database - Catálogo de jogadores suspeitos e histórico de encontros.
Usa SQLite para persistência local.
"""
import sqlite3, json, time
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime


class SuspectDatabase:
    """Banco de dados local de jogadores suspeitos/hackers."""

    def __init__(self, db_path: str = "data/suspects.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    # ----------------------------------------------------------------
    def _create_tables(self):
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS suspects (
                puuid       TEXT PRIMARY KEY,
                summoner_name TEXT NOT NULL,
                tagline     TEXT DEFAULT '',
                first_seen  TEXT NOT NULL,
                last_seen   TEXT NOT NULL,
                total_meets INTEGER DEFAULT 1,
                total_score REAL DEFAULT 0,
                max_score   REAL DEFAULT 0,
                nivel_max   TEXT DEFAULT 'BAIXO',
                status      TEXT DEFAULT 'observacao',
                notes       TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS encounters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                puuid       TEXT NOT NULL,
                match_id    TEXT NOT NULL,
                encounter_date TEXT NOT NULL,
                score       REAL DEFAULT 0,
                nivel       TEXT DEFAULT 'BAIXO',
                is_hacker   INTEGER DEFAULT 0,
                details     TEXT DEFAULT '{}',
                FOREIGN KEY (puuid) REFERENCES suspects(puuid)
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                total_matches   INTEGER DEFAULT 0,
                hackers_found   INTEGER DEFAULT 0,
                suspects_found  INTEGER DEFAULT 0,
                avg_score       REAL DEFAULT 0,
                details     TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS my_matches (
                match_id    TEXT PRIMARY KEY,
                date        TEXT NOT NULL,
                placement   INTEGER DEFAULT 0,
                players_count INTEGER DEFAULT 0,
                hackers_in_match INTEGER DEFAULT 0,
                details     TEXT DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_encounters_puuid ON encounters(puuid);
            CREATE INDEX IF NOT EXISTS idx_encounters_date ON encounters(encounter_date);
        """)
        self.conn.commit()

    # ----------------------------------------------------------------
    # SUSPEITOS
    # ----------------------------------------------------------------
    def add_or_update_suspect(self, puuid: str, name: str, tagline: str = "",
                               score: float = 0, nivel: str = "BAIXO",
                               is_hacker: bool = False) -> bool:
        """Adiciona ou atualiza um suspeito no banco."""
        now = datetime.now().isoformat()
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM suspects WHERE puuid = ?", (puuid,))
        existing = cur.fetchone()

        if existing:
            max_score = max(existing["max_score"], score)
            nivel_max = self._max_nivel(existing["nivel_max"], nivel)
            cur.execute("""
                UPDATE suspects SET
                    summoner_name = ?, last_seen = ?, total_meets = total_meets + 1,
                    total_score = total_score + ?, max_score = ?,
                    nivel_max = ?, status = ?
                WHERE puuid = ?
            """, (name, now, score, max_score, nivel_max,
                  "hacker" if is_hacker else "suspeito" if score > 30 else existing["status"],
                  puuid))
        else:
            cur.execute("""
                INSERT INTO suspects (puuid, summoner_name, tagline, first_seen, last_seen,
                                      total_meets, total_score, max_score, nivel_max, status)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """, (puuid, name, tagline, now, now, score, score, nivel,
                  "hacker" if is_hacker else "suspeito" if score > 30 else "observacao"))

        self.conn.commit()
        return True

    def get_suspect(self, puuid: str) -> Optional[Dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM suspects WHERE puuid = ?", (puuid,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_all_suspects(self, nivel_min: str = "BAIXO") -> List[Dict]:
        """Lista suspeitos acima de um nível mínimo."""
        niveis = {"BAIXO": 0, "MÉDIO": 1, "ALTO": 2, "CRÍTICO": 3}
        min_nivel = niveis.get(nivel_min, 0)
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM suspects ORDER BY max_score DESC")
        results = []
        for row in cur.fetchall():
            d = dict(row)
            if niveis.get(d.get("nivel_max", "BAIXO"), 0) >= min_nivel:
                results.append(d)
        return results

    def get_hackers_only(self) -> List[Dict]:
        """Retorna apenas jogadores marcados como hacker."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM suspects WHERE status = 'hacker' ORDER BY max_score DESC")
        return [dict(row) for row in cur.fetchall()]

    def get_suspect_count(self) -> Dict:
        cur = self.conn.cursor()
        cur.execute("SELECT status, COUNT(*) as count FROM suspects GROUP BY status")
        counts = {"hacker": 0, "suspeito": 0, "observacao": 0}
        for row in cur.fetchall():
            counts[row["status"]] = row["count"]
        return counts

    # ----------------------------------------------------------------
    # ENCONTROS
    # ----------------------------------------------------------------
    def register_encounter(self, puuid: str, match_id: str, score: float = 0,
                            nivel: str = "BAIXO", is_hacker: bool = False,
                            details: dict = None) -> bool:
        """Registra um encontro com um jogador suspeito."""
        now = datetime.now().isoformat()
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO encounters (puuid, match_id, encounter_date, score, nivel, is_hacker, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (puuid, match_id, now, score, nivel, 1 if is_hacker else 0,
              json.dumps(details or {}, ensure_ascii=False)))
        self.conn.commit()
        return True

    def get_encounters(self, puuid: str = None, limit: int = 50) -> List[Dict]:
        cur = self.conn.cursor()
        if puuid:
            cur.execute("""
                SELECT e.*, s.summoner_name FROM encounters e
                JOIN suspects s ON s.puuid = e.puuid
                WHERE e.puuid = ? ORDER BY e.encounter_date DESC LIMIT ?
            """, (puuid, limit))
        else:
            cur.execute("""
                SELECT e.*, s.summoner_name FROM encounters e
                JOIN suspects s ON s.puuid = e.puuid
                ORDER BY e.encounter_date DESC LIMIT ?
            """, (limit,))
        return [dict(row) for row in cur.fetchall()]

    # ----------------------------------------------------------------
    # MÉTRICAS
    # ----------------------------------------------------------------
    def register_metrics(self, total_matches: int, hackers_found: int,
                          suspects_found: int, avg_score: float,
                          details: dict = None):
        now = datetime.now().isoformat()
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO metrics (date, total_matches, hackers_found, suspects_found, avg_score, details)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (now, total_matches, hackers_found, suspects_found, avg_score,
              json.dumps(details or {}, ensure_ascii=False)))
        self.conn.commit()

    def get_metrics_history(self, days: int = 30) -> List[Dict]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM metrics ORDER BY date DESC LIMIT ?
        """, (days,))
        return [dict(row) for row in cur.fetchall()]

    def get_summary(self) -> Dict:
        """Resumo completo do banco."""
        cur = self.conn.cursor()
        suspects = self.get_suspect_count()
        cur.execute("SELECT COUNT(*) as c FROM encounters")
        total_encounters = cur.fetchone()["c"]
        cur.execute("SELECT AVG(total_score) as avg FROM suspects")
        avg_row = cur.fetchone()
        return {
            "total_suspects": sum(suspects.values()),
            "hackers": suspects.get("hacker", 0),
            "suspeitos": suspects.get("suspeito", 0),
            "observacao": suspects.get("observacao", 0),
            "total_encounters": total_encounters,
            "avg_score": round(avg_row["avg"], 1) if avg_row and avg_row["avg"] else 0,
        }

    # ----------------------------------------------------------------
    def _max_nivel(self, a: str, b: str) -> str:
        niveis = ["BAIXO", "MÉDIO", "ALTO", "CRÍTICO"]
        return max(a, b, key=lambda x: niveis.index(x) if x in niveis else 0)

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    db = SuspectDatabase()
    print(f"✅ Banco criado em: {db.db_path}")
    print(f"Resumo: {db.get_summary()}")
    db.close()
