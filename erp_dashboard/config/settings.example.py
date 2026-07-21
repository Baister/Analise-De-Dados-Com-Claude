# config/settings.py — MODELO. Copie para settings.py e preencha.
# O settings.py real NUNCA e versionado (.gitignore) — contem credenciais.
DB_CONFIG = {"dsn": "blue_penha", "user": "SEU_USUARIO", "password": "SUA_SENHA", "timeout": 10}
BOT_INTERVALS = {"dashboard": 300, "vendas": 600, "estoque": 900,
                 "financeiro": 1200, "crm": 1500, "imposto": 1800,
                 "cliente_comportamento": 1800}
ALERTAS = {"estoque_critico_dias_sem_vnd": 90, "cliente_inativo_dias": 90,
           "cliente_em_risco_dias": 60, "query_max_rows": 5000,
           "meta_faturamento_mensal": 2500000, "inadimplencia_dias": 30}
PLANOS_EXCLUIR_FAT = ["004", "012", "025", "027"]
APP_TITLE, APP_VERSION, THEME = "ERP Analytics Dashboard", "1.6.0", "dark"
CORES = {"bg": "#0d1117", "sidebar": "#161b22", "card": "#1c2128", "card_border": "#30363d",
         "accent_azul": "#1f6feb", "accent_verm": "#da3633", "success": "#238636",
         "warning": "#d29922", "text": "#e6edf3", "subtext": "#8b949e", "progress_bg": "#21262d"}
IS_HUB, HUB_URL, HUB_PORT = False, "", 8765
import pathlib as _p
CACHE_DB_PATH = str(_p.Path(__file__).parent.parent / "cache.db")
DASHBOARD_PASSWORD = "DEFINA_A_SENHA_ADMIN"
ACCESS_PROFILES = {DASHBOARD_PASSWORD: ["*"]}  # adicione os demais perfis aqui
