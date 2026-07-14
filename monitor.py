#!/usr/bin/env python3
"""Monitor wrapper - log to file, no console window."""
import sys, os, io
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_log.txt")

# Redireciona stdout/stderr para arquivo
class Log:
    def __init__(self, path):
        self.file = open(path, "w", encoding="utf-8", buffering=1)
        self.encoding = "UTF-8"
    def write(self, msg):
        self.file.write(msg); self.file.flush()
    def flush(self): self.file.flush()

sys.stdout = Log(LOG)
sys.stderr = Log(LOG + ".err")

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from main import TFTFlyway

app = TFTFlyway()
app.setup()
sys.stdout.write("="*50 + "\n  TFTFlyway - Monitor\n  Aguardando partida...\n" + "="*50 + "\n")

try: app.cmd_auto("5")
except KeyboardInterrupt: pass
finally: app.shutdown()
