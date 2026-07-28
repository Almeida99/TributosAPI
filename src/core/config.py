import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIG - Configurações do Sistema
# Bancos/municípios são cadastrados apenas em /config/bancos.
# ============================================================

# API
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Driver ODBC padrão (credenciais vêm do catálogo por tenant)
DB_DRIVER = (
    os.getenv("DB_INTEGRACAO_DRIVER")
    or os.getenv("DB_DRIVER")
    or "ODBC Driver 18 for SQL Server"
).strip()

# Autenticação da tela /config/bancos (HTTP Basic)
CONFIG_ADMIN_USER = (os.getenv("CONFIG_ADMIN_USER") or "").strip()
CONFIG_ADMIN_PASSWORD = (os.getenv("CONFIG_ADMIN_PASSWORD") or "").strip()


def _env_flag(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "y", "on"):
        return True
    if raw in ("0", "false", "no", "n", "off"):
        return False
    return default


# TLS ODBC — padrão seguro: Encrypt=yes; Trust=yes (certificados autoassinados comuns)
DB_ENCRYPT = _env_flag("DB_ENCRYPT", True)
DB_TRUST_SERVER_CERTIFICATE = _env_flag("DB_TRUST_SERVER_CERTIFICATE", True)


def odbc_tls_fragment() -> str:
    """Fragmento Encrypt/TrustServerCertificate para connection string ODBC."""
    enc = "yes" if DB_ENCRYPT else "no"
    trust = "yes" if DB_TRUST_SERVER_CERTIFICATE else "no"
    return f"TrustServerCertificate={trust};Encrypt={enc};"


def build_odbc_conn_str(
    server: str,
    database: str,
    username: str,
    password: str,
    driver: Optional[str] = None,
    timeout: int = 30,
) -> str:
    """Monta connection string ODBC com flags TLS do ambiente."""
    drv = (driver or DB_DRIVER or "ODBC Driver 18 for SQL Server").strip()
    if not drv.startswith("{"):
        drv = f"{{{drv}}}"
    return (
        f"DRIVER={drv};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        f"{odbc_tls_fragment()}"
        f"Connection Timeout={int(timeout)};"
    )


def get_conexao(id_conexao):
    """Busca conexão auxiliar do .env (CONEXAO_*), se usada por integrações legadas."""
    prefix = f"CONEXAO_{id_conexao.upper().replace('-', '_')}"
    server = os.getenv(f"{prefix}_SERVER")
    if not server:
        return None
    return {
        "servidor": server,
        "banco": os.getenv(f"{prefix}_DATABASE"),
        "usuario": os.getenv(f"{prefix}_USERNAME"),
        "senha": os.getenv(f"{prefix}_PASSWORD"),
        "driver": os.getenv(f"{prefix}_DRIVER", "ODBC Driver 18 for SQL Server"),
        "nome": os.getenv(f"{prefix}_NOME", id_conexao),
    }
