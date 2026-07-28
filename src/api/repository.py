import logging
from typing import Any, List, Optional

import pyodbc

from src.core.database import db

logger = logging.getLogger(__name__)


def _row(d: Optional[dict]) -> Optional[dict[str, Any]]:
    if d is None:
        return None
    return {str(k).lower(): v for k, v in d.items()}


def _rows(rows: List[dict]) -> List[dict[str, Any]]:
    return [_row(r) or {} for r in rows] if rows else []


def _integracao_command(sql: str, params: Optional[tuple] = None) -> int:
    """Executa INSERT/UPDATE/DELETE (sem result set de linhas de dados)."""
    conn = db.integracao_conn()
    cur = conn.cursor()
    n = 0
    try:
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        n = cur.rowcount
        return n
    finally:
        cur.close()
        conn.close()


def buscar_cadastro_por_login(login: str) -> Optional[dict[str, Any]]:
    sql = """
    SELECT id_cadastro, login, senha_hash, ativo
    FROM dbo.TRB_INTEGRACAO_TERCEIROS_CADASTRO
    WHERE login = ?
    """
    row = db.integracao_query(sql, (login.strip(),))
    return _row(row[0]) if row else None


def buscar_cadastro_por_id(id_cadastro: int) -> Optional[dict[str, Any]]:
    sql = """
    SELECT id_cadastro, login, ativo, data_criacao
    FROM dbo.TRB_INTEGRACAO_TERCEIROS_CADASTRO
    WHERE id_cadastro = ?
    """
    row = db.integracao_query(sql, (id_cadastro,))
    return _row(row[0]) if row else None


def listar_cadastros() -> List[dict[str, Any]]:
    sql = """
    SELECT id_cadastro, login, ativo, data_criacao, data_atualizacao
    FROM dbo.TRB_INTEGRACAO_TERCEIROS_CADASTRO
    ORDER BY id_cadastro
    """
    return _rows(db.integracao_query(sql) or [])


def inserir_cadastro(login: str, senha_hash: str) -> int:
    sql = """
    INSERT INTO dbo.TRB_INTEGRACAO_TERCEIROS_CADASTRO (login, senha_hash, ativo)
    OUTPUT INSERTED.id_cadastro
    VALUES (?, ?, 1)
    """
    conn = db.integracao_conn()
    cur = conn.cursor()
    try:
        cur.execute(sql, (login.strip(), senha_hash))
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Falha ao inserir cadastro terceiro.")
        return int(row[0])
    finally:
        cur.close()
        conn.close()


def tem_permissao_endpoint(id_cadastro: int, nome_integracao: str) -> bool:
    sql = """
    SELECT 1 AS x
    FROM dbo.TRB_INTEGRACAO_TERCEIROS_ENDPOINT e
    INNER JOIN dbo.TRB_INTEGRACAO_TERCEIROS_CADASTRO c ON c.id_cadastro = e.id_cadastro
    WHERE e.id_cadastro = ?
      AND e.nome_integracao = ?
      AND e.ativo = 1
      AND c.ativo = 1
    """
    r = db.integracao_query(sql, (id_cadastro, nome_integracao))
    return len(r) > 0 if r else False


def inserir_endpoint_permitido(id_cadastro: int, nome_integracao: str) -> int:
    sql = """
    INSERT INTO dbo.TRB_INTEGRACAO_TERCEIROS_ENDPOINT (id_cadastro, nome_integracao, ativo)
    OUTPUT INSERTED.id_endpoint
    VALUES (?, ?, 1)
    """
    conn = db.integracao_conn()
    cur = conn.cursor()
    try:
        cur.execute(sql, (id_cadastro, nome_integracao.strip()))
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Falha ao inserir endpoint.")
        return int(row[0])
    finally:
        cur.close()
        conn.close()


def listar_endpoints_cadastro(id_cadastro: int) -> List[dict[str, Any]]:
    sql = """
    SELECT id_endpoint, id_cadastro, nome_integracao, ativo, data_criacao
    FROM dbo.TRB_INTEGRACAO_TERCEIROS_ENDPOINT
    WHERE id_cadastro = ?
    ORDER BY nome_integracao
    """
    return _rows(db.integracao_query(sql, (id_cadastro,)) or [])


def registrar_auditoria(
    id_cadastro: Optional[int],
    tipo_evento: str,
    metodo_http: Optional[str] = None,
    rota: Optional[str] = None,
    status_http: Optional[int] = None,
    duracao_ms: Optional[int] = None,
    endereco_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    login_tentativa: Optional[str] = None,
    sucesso: Optional[bool] = None,
    detalhe_erro: Optional[str] = None,
    json_requisicao: Optional[str] = None,
    json_retorno: Optional[str] = None,
) -> None:
    sql = """
    INSERT INTO dbo.TRB_INTEGRACAO_TERCEIROS_AUDITORIA (
        id_cadastro, tipo_evento, metodo_http, rota, status_http, duracao_ms,
        endereco_ip, user_agent, login_tentativa, sucesso, detalhe_erro,
        json_requisicao, json_retorno
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    try:
        _integracao_command(
            sql,
            (
                id_cadastro,
                tipo_evento,
                metodo_http,
                rota[:1024] if rota and len(rota) > 1024 else rota,
                status_http,
                duracao_ms,
                (endereco_ip or "")[:128] if endereco_ip else None,
                (user_agent or "")[:512] if user_agent else None,
                (login_tentativa or "")[:255] if login_tentativa else None,
                1 if sucesso is True else (0 if sucesso is False else None),
                (detalhe_erro or "")[:500] if detalhe_erro else None,
                json_requisicao,
                json_retorno,
            ),
        )
    except Exception as e:
        logger.error("Falha ao gravar TRB_INTEGRACAO_TERCEIROS_AUDITORIA: %s", e)
