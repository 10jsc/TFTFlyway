#!/usr/bin/env python3
"""
API Key Manager - Gerencia a chave da API Riot automaticamente.
Se a chave expirar, usa Selenium para renovar via developer.riotgames.com.
"""
import json, os, time, re, requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional


class APIKeyManager:
    """Gerencia a chave da API Riot com renovacao automatica."""

    CONFIG_FILE = Path(__file__).parent.parent / "config.json"

    def __init__(self, env_file: str = None):
        self.env_file = Path(env_file or Path(__file__).parent.parent / ".env")
        self.config = self._load_config()
        self._key: Optional[str] = None

        # Tenta carregar de varias fontes
        self._key = (self.config.get("riot_key") or
                     self._load_env().get("riot_api_key") or
                     os.environ.get("RIOT_API_KEY"))

    # ----------------------------------------------------------------
    def _load_config(self) -> dict:
        if self.CONFIG_FILE.exists():
            try:
                return json.loads(self.CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_config(self):
        self.CONFIG_FILE.write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _load_env(self) -> dict:
        creds = {"username": "", "password": "", "riot_api_key": ""}
        if self.env_file.exists():
            for line in self.env_file.read_text().splitlines():
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    kl = k.lower()
                    creds[kl] = v
                    if kl == "riot_dev_user":
                        creds["username"] = v
                    elif kl == "riot_dev_pass":
                        creds["password"] = v
        return creds

    # ----------------------------------------------------------------
    @property
    def key(self) -> Optional[str]:
        return self._key

    @key.setter
    def key(self, value: str):
        self._key = value

    # ----------------------------------------------------------------
    def is_valid(self) -> bool:
        """Testa se a chave atual e valida contra a Riot API."""
        if not self._key or not self._key.startswith("RGAPI-"):
            return False
        try:
            h = {"X-Riot-Token": self._key}
            # Endpoint leve so pra testar a chave
            r = requests.get(
                "https://americas.api.riotgames.com/riot/account/v1/accounts/me",
                headers=h, timeout=5
            )
            return r.status_code == 200
        except Exception:
            return False

    def needs_renew(self) -> bool:
        """Verifica se a chave precisa ser renovada (expirada ou data antiga)."""
        if not self._key or not self._key.startswith("RGAPI-"):
            return True

        # Testa se a chave realmente funciona
        return not self.is_valid()

    # ----------------------------------------------------------------
    def renew(self, username: str = None, password: str = None) -> bool:
        """Renova a chave automaticamente via Selenium."""
        creds = self._load_env()
        username = username or creds.get("username") or os.environ.get("RIOT_DEV_USER")
        password = password or creds.get("password") or os.environ.get("RIOT_DEV_PASS")

        if not username or not password:
            print("  ⚠️ Credenciais do portal Riot nao encontradas no .env")
            return False

        print("  🔄 Renovando chave da API automaticamente...")
        new_key = self._renew_via_selenium(username, password)

        if new_key and new_key.startswith("RGAPI-"):
            self._key = new_key
            self.config["riot_key"] = new_key
            self.config["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            self._save_config()
            print(f"  ✅ Chave renovada: {new_key[:25]}...")
            return True

        print("  ❌ Nao foi possivel renovar a chave automaticamente.")
        return False

    def _renew_via_selenium(self, username: str, password: str) -> Optional[str]:
        """Usa Selenium para logar e gerar nova chave."""
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.chrome.service import Service as ChromeService
        except ImportError:
            print("  ⚠️ Selenium nao instalado. pip install selenium webdriver-manager")
            return None

        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver = webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()),
                options=self._chrome_options()
            )
        except Exception:
            try:
                driver = webdriver.Chrome(options=self._chrome_options())
            except Exception as e:
                print(f"  ⚠️ Erro ChromeDriver: {e}")
                return None

        try:
            wait = WebDriverWait(driver, 20)
            driver.get("https://developer.riotgames.com/")

            # Tenta fazer login
            try:
                btn = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(text(),'Sign In')] | //button[contains(text(),'Sign In')]")))
                btn.click()
            except Exception:
                pass
            time.sleep(2)

            try:
                wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(username)
                driver.find_element(By.ID, "password").send_keys(password)
                driver.find_element(By.XPATH, "//button[@type='submit']").click()
            except Exception:
                pass
            time.sleep(5)

            # Aguarda 2FA se necessario
            if "login" in driver.current_url.lower():
                print("  ⏳ Verificacao 2FA necessaria. Confirme no navegador...")
                wait.until(lambda d: "login" not in d.current_url.lower())
                print("  ✅ Login confirmado!")

            # Vai para pagina de API Keys
            driver.get("https://developer.riotgames.com/api-keys")
            time.sleep(3)

            # Tenta extrair a chave
            page_text = driver.find_element(By.TAG_NAME, "body").text
            match = re.search(r'RGAPI-[A-Za-z0-9_-]{20,}', page_text)
            if match:
                return match.group(0)

            # Tenta elemento especifico
            for sel in [".api-key", ".key-display", "[data-testid='api-key']"]:
                try:
                    text = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                    if text.startswith("RGAPI-"):
                        return text
                except Exception:
                    pass

            return None
        except Exception as e:
            print(f"  ⚠️ Erro no Selenium: {e}")
            return None
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    def _chrome_options(self):
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument("--start-maximized")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--headless=new")  # Modo invisivel
        return opts

    # ----------------------------------------------------------------
    def ensure_valid_key(self) -> bool:
        """Garante que temos uma chave valida. Renova se necessario."""
        if self._key and self.is_valid():
            return True
        if self.needs_renew():
            print("  🔑 API Key expirada. Tentando renovar...")
            return self.renew()
        return False


if __name__ == "__main__":
    mgr = APIKeyManager()
    print(f"Chave atual: {mgr.key[:25] if mgr.key else 'NENHUMA'}...")
    print(f"Valida: {mgr.is_valid()}")
    if not mgr.is_valid():
        print("Renovando...")
        mgr.renew()
