"""Teste ad-hoc de conexão ODBC (credenciais manuais via env — não é o fluxo de produção)."""
import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

from src.core.config import build_odbc_conn_str

server = os.getenv("TEST_DB_SERVER")
database = os.getenv("TEST_DB_DATABASE")
username = os.getenv("TEST_DB_USERNAME")
password = os.getenv("TEST_DB_PASSWORD")
driver = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")

if not server or not database or not username:
    raise SystemExit(
        "Defina TEST_DB_SERVER, TEST_DB_DATABASE e TEST_DB_USERNAME "
        "(teste manual). Em produção, cadastre bancos em /config/bancos."
    )

conn_str = build_odbc_conn_str(
    server=server,
    database=database,
    username=username,
    password=password or "",
    driver=driver,
    timeout=10,
)

print(f"Tentando conectar a {server} usando {driver}...")
try:
    conn = pyodbc.connect(conn_str, timeout=10)
    print("Sucesso!")
    conn.close()
except Exception as e:
    print(f"Erro: {e}")
