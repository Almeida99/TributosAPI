"""Conexão ODBC e validação de usuário — sempre via tenant do path /{slug}/."""
import pyodbc
from fastapi import Header, HTTPException

from src.core.config import DB_DRIVER, build_odbc_conn_str


def get_db_connection():
    """Conexão ODBC usando o tenant atual (obrigatório)."""
    from src.core.database import get_current_tenant

    tenant = get_current_tenant()
    if not tenant:
        raise HTTPException(
            status_code=400,
            detail="Informe o banco no path: /{banco}/.... Configure em /config/bancos.",
        )

    server = tenant.get("server") or ""
    database = tenant.get("database") or ""
    username = tenant.get("username") or ""
    password = tenant.get("password") or ""
    driver = tenant.get("driver") or DB_DRIVER

    if not server or not database or not username:
        raise HTTPException(
            status_code=500,
            detail="Credenciais do banco incompletas. Edite em /config/bancos.",
        )

    conn_str = build_odbc_conn_str(
        server=server,
        database=database,
        username=username,
        password=password,
        driver=driver,
        timeout=30,
    )
    return pyodbc.connect(conn_str, timeout=30)


async def validate_user(x_user_code: int = Header(..., alias="X-User-Code")):
    """
    Valida se o usr_cod existe e está ativo na tabela FR_USUARIO do tenant.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT USR_CODIGO FROM FR_USUARIO WHERE USR_CODIGO = ? AND (USR_BLOQUEIO_USUARIO = 'N' OR USR_BLOQUEIO_USUARIO IS NULL)",
            (x_user_code,),
        )
        row = cursor.fetchone()

        cursor.close()
        conn.close()

        if not row:
            raise HTTPException(status_code=401, detail="Usuario invalido ou inativo.")

        return x_user_code
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro de banco de dados: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
