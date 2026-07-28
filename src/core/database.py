"""Conexões SQL Server por tenant (multibanco)."""
import logging
from contextvars import ContextVar
from typing import Any, Dict, Optional

import pyodbc

from ..core.config import DB_DRIVER, build_odbc_conn_str

logger = logging.getLogger(__name__)

# Tenant atual da requisição (slug + dados de conexão)
_current_tenant: ContextVar[Optional[Dict[str, Any]]] = ContextVar("current_tenant", default=None)


def set_current_tenant(banco: Optional[Dict[str, Any]]) -> None:
    _current_tenant.set(banco)


def get_current_tenant() -> Optional[Dict[str, Any]]:
    return _current_tenant.get()


def clear_current_tenant() -> None:
    _current_tenant.set(None)


class Database:
    def __init__(self):
        self.driver = DB_DRIVER

    def _resolve_creds(self):
        """Credenciais do tenant atual (obrigatório — cadastro em /config/bancos)."""
        tenant = get_current_tenant()
        if not tenant:
            raise ValueError(
                "Nenhum banco selecionado. Use o path /{slug}/... após cadastrar em /config/bancos."
            )
        server = tenant.get("server") or ""
        database = tenant.get("database") or ""
        user = tenant.get("username") or ""
        password = tenant.get("password") or ""
        driver = tenant.get("driver") or self.driver
        return server, database, user, password, driver

    def _get_conn_str(self, server=None, database=None, user=None, password=None, driver=None):
        if server is None:
            server, database, user, password, driver = self._resolve_creds()
        else:
            database = database or ""
            user = user or ""
            password = password or ""
            driver = driver or self.driver

        if not server or not database or not user:
            raise ValueError(
                "Credenciais de banco incompletas. Configure o tenant em /config/bancos."
            )

        return build_odbc_conn_str(
            server=server,
            database=database,
            username=user,
            password=password or "",
            driver=driver,
            timeout=30,
        )

    def integracao_conn(self):
        """Conexão com o banco de integração do tenant atual."""
        return pyodbc.connect(self._get_conn_str(), autocommit=True, timeout=30)

    def integracao_query(self, sql, params=None):
        """Executar query no banco de integração."""
        conn = self.integracao_conn()
        cursor = conn.cursor()
        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            if cursor.description:
                cols = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(cols, row)) for row in rows]
            return []
        except Exception as e:
            logger.error(f"Erro na query de integração: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def origem_query(self, conexao, sql, params=None):
        """Executar query no banco de origem."""
        if not conexao:
            raise ValueError("Configuração de conexão não fornecida")

        conn_str = self._get_conn_str(
            server=conexao["servidor"],
            database=conexao["banco"],
            user=conexao["usuario"],
            password=conexao["senha"],
            driver=conexao.get("driver"),
        )

        try:
            conn = pyodbc.connect(conn_str, autocommit=True, timeout=30)
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            if cursor.description:
                cols = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(cols, row)) for row in rows]
            return []
        except Exception as e:
            logger.error(f"Erro na query de origem: {e}")
            raise
        finally:
            if "cursor" in locals():
                cursor.close()
            if "conn" in locals():
                conn.close()

    def origem_sp(self, conexao, sp_sql, params=None):
        """Executar stored procedure no banco de origem."""
        if not conexao:
            raise ValueError("Configuração de conexão não fornecida")

        conn_str = self._get_conn_str(
            server=conexao["servidor"],
            database=conexao["banco"],
            user=conexao["usuario"],
            password=conexao["senha"],
            driver=conexao.get("driver"),
        )

        try:
            conn = pyodbc.connect(conn_str, autocommit=True, timeout=30)
            cursor = conn.cursor()
            if params:
                cursor.execute(sp_sql, params)
            else:
                cursor.execute(sp_sql)

            results = []
            while True:
                if cursor.description:
                    cols = [d[0] for d in cursor.description]
                    rows = cursor.fetchall()
                    results.extend([dict(zip(cols, row)) for row in rows])
                if not cursor.nextset():
                    break
            return results
        except Exception as e:
            logger.error(f"Erro na stored procedure: {e}")
            raise
        finally:
            if "cursor" in locals():
                cursor.close()
            if "conn" in locals():
                conn.close()

    def validar_usuario(self, usr_cod):
        """Validar usuário na tabela FR_usuario."""
        try:
            sql = """
                SELECT USR_CODIGO as USR_COD, USR_NOME, USR_BLOQUEIO_USUARIO 
                FROM FR_USUARIO 
                WHERE USR_CODIGO = ? AND (USR_BLOQUEIO_USUARIO = 'N' OR USR_BLOQUEIO_USUARIO IS NULL)
            """
            result = self.integracao_query(sql, (usr_cod,))
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Erro ao validar usuário {usr_cod}: {e}")
            return None


db = Database()
