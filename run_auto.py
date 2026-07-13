#!/usr/bin/env python3
"""TFTFlyway - Modo Automatico. Escreve log em arquivo."""
import sys, os, io

# Redireciona stdout/stderr para arquivo de log
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_log.txt")

class LogWriter:
    def __init__(self, path):
        self.file = open(path, "w", encoding="utf-8", buffering=1)
        self.encoding = "UTF-8"
    def write(self, msg):
        self.file.write(msg)
        self.file.flush()
    def flush(self):
        self.file.flush()

sys.stdout = LogWriter(LOG_FILE)
sys.stderr = LogWriter(LOG_FILE + ".err")

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from main import TFTFlyway

app = TFTFlyway()
app.setup()

sys.stdout.write("=" * 50 + "\n")
sys.stdout.write("  TFTFlyway - Modo Automatico\n")
sys.stdout.write("  Aguardando partida...\n")
sys.stdout.write("=" * 50 + "\n")

try:
    app.cmd_auto("5")
except KeyboardInterrupt:
    sys.stdout.write("\nEncerrando...\n")
finally:
    app.shutdown()
    sys.stdout.write("Sistema encerrado.\n")
