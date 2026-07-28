"""Aplicação do schema V3 (database/init.sql) em um banco do catálogo."""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict

from src.core.config import build_odbc_conn_str

logger = logging.getLogger(__name__)

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INIT_SQL_PATH = os.path.join(_ROOT, "database", "init.sql")


def apply_init_sql_to_banco(banco: Dict[str, Any]) -> None:
    """
    Executa database/init.sql (batches separados por GO) no banco informado.
    Levanta Exception em falha de conexão ou se o arquivo não existir.
    """
    import pyodbc

    if not os.path.isfile(INIT_SQL_PATH):
        raise FileNotFoundError(f"Arquivo de schema não encontrado: {INIT_SQL_PATH}")

    with open(INIT_SQL_PATH, "r", encoding="utf-8") as f:
        raw = f.read()

    batches = [b.strip() for b in re.split(r"(?im)^\s*GO\s*$", raw) if b.strip()]
    label = banco.get("slug") or banco.get("nome") or banco.get("database") or "?"

    conn_str = build_odbc_conn_str(
        server=banco["server"],
        database=banco["database"],
        username=banco["username"],
        password=banco.get("password") or "",
        driver=banco.get("driver") or "ODBC Driver 18 for SQL Server",
        timeout=30,
    )

    conn = pyodbc.connect(conn_str, autocommit=True, timeout=30)
    try:
        cur = conn.cursor()
        for batch in batches:
            try:
                cur.execute(batch)
                while cur.nextset():
                    pass
            except Exception as batch_err:
                logger.warning("[%s] Erro em batch do init.sql: %s", label, batch_err)
        cur.close()
        logger.info("Schema aplicado em [%s] (%s)", label, banco.get("database"))
    finally:
        conn.close()
