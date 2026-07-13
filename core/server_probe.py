#!/usr/bin/env python3
"""
Server Probe - Sonda o servidor TFT diretamente.
Extrai IP/porta/token do processo do jogo e tenta comunicação direta.
Útil para rastrear comportamento anômalo em tempo real.
"""
import socket, struct, json, time, re, subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple


class ServerProbe:
    """Sonda o servidor TFT durante a partida."""

    TFT_SERVER = "45.7.37.3"

    def __init__(self, log_dir: str = "data/probes"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.server_info: Optional[Dict] = None
        self.probe_results: List[Dict] = []

    # ----------------------------------------------------------------
    def extract_game_info(self) -> Optional[Dict]:
        """Extrai IP, porta, token e PlayerID do processo do jogo."""
        ps = r'''
$p=Get-Process -Name "League of Legends" -ErrorAction SilentlyContinue
if(-not $p){exit 1}
$cmd=(Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)").CommandLine
if(-not $cmd){exit 1}
Write-Host $cmd
'''
        try:
            r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW)
            if r.returncode != 0 or not r.stdout.strip():
                return None

            cmdline = r.stdout.strip()
            m = re.search(r'"([\d.]+) (\d+) ([^\s"]+) (\d+)"', cmdline)
            if not m:
                return None

            info = {
                "server_ip": m.group(1),
                "server_port": int(m.group(2)),
                "auth_token": m.group(3),
                "player_id": m.group(4),
                "timestamp": datetime.now().isoformat()
            }

            # Extrai parâmetros adicionais
            for param in ["GameID", "Product", "RiotClientPort", "Region", "PlatformID"]:
                if param in cmdline:
                    idx = cmdline.find(param + "=")
                    if idx >= 0:
                        end = cmdline.find(" ", idx + len(param) + 1)
                        val = cmdline[idx + len(param) + 1:end] if end > idx else cmdline[idx + len(param) + 1:]
                        info[param] = val.strip('"')

            self.server_info = info
            return info
        except Exception as e:
            return None

    @property
    def in_game(self) -> bool:
        """Verifica se o jogo está rodando."""
        info = self.extract_game_info()
        return info is not None

    # ----------------------------------------------------------------
    def probe_server(self) -> List[Dict]:
        """Tenta vários formatos de comunicação com o servidor TFT."""
        if not self.server_info:
            self.extract_game_info()
        if not self.server_info:
            return []

        ip = self.server_info["server_ip"]
        port = self.server_info["server_port"]
        auth = self.server_info.get("auth_token", "")
        pid = self.server_info.get("player_id", "")

        results = []
        payloads = [
            ("Raw token", auth.encode()),
            ("JSON auth", json.dumps({"auth": auth, "playerId": pid}).encode()),
            ("JSON ping", json.dumps({"cmd": "ping", "playerId": pid}).encode()),
            ("Hex handshake", bytes.fromhex('0001000100000000')),
            ("Riot v1", b'\xbb\x01' + auth.encode()),
            ("Zero term", auth.encode() + b'\x00' + pid.encode()),
        ]

        # TCP probes
        for fmt_name, payload in payloads:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                if s.connect_ex((ip, port)) == 0:
                    s.send(payload)
                    time.sleep(0.2)
                    try:
                        data = s.recv(4096)
                        hex_str = data[:100].hex()
                        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[:100])
                        results.append({
                            "formato": fmt_name, "tipo": "TCP",
                            "resposta_hex": hex_str, "resposta_ascii": ascii_str,
                            "tamanho": len(data)
                        })
                    except socket.timeout:
                        pass
                s.close()
            except Exception:
                pass

        # UDP probes
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1.5)
            for fmt_name, payload in [
                ("UDP token", auth.encode()),
                ("UDP player+token", pid.encode() + b':' + auth.encode()),
            ]:
                try:
                    s.sendto(payload, (ip, port))
                    time.sleep(0.1)
                    data, addr = s.recvfrom(4096)
                    results.append({
                        "formato": fmt_name, "tipo": "UDP",
                        "resposta_hex": data[:100].hex(),
                        "tamanho": len(data)
                    })
                except socket.timeout:
                    pass
            s.close()
        except Exception:
            pass

        self.probe_results = results

        # Salva resultado
        report = {
            "timestamp": datetime.now().isoformat(),
            "server": f"{ip}:{port}",
            "game_id": self.server_info.get("GameID", "?"),
            "protocolos_responderam": results,
            "total_respostas": len(results)
        }
        probe_file = self.log_dir / f"probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(probe_file, "w") as f:
            json.dump(report, f, indent=2)

        return results

    # ----------------------------------------------------------------
    def get_latency(self) -> Optional[float]:
        """Mede latência aproximada até o servidor TFT."""
        if not self.server_info:
            self.extract_game_info()
        if not self.server_info:
            return None

        ip = self.server_info["server_ip"]
        port = self.server_info["server_port"]

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            start = time.time()
            if s.connect_ex((ip, port)) == 0:
                latency = (time.time() - start) * 1000  # ms
                s.close()
                return round(latency, 1)
        except Exception:
            pass
        return None


if __name__ == "__main__":
    probe = ServerProbe()
    info = probe.extract_game_info()
    if info:
        print(f"✅ Jogo rodando: {info.get('server_ip')}:{info.get('server_port')}")
        print(f"   PlayerID: {info.get('player_id')}")
        results = probe.probe_server()
        print(f"   Respostas: {len(results)}")
    else:
        print("❌ Jogo não está rodando")
