import httpx
import json
import logging
import re
import pyodbc
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class PythonIntegrationService:
    def _get_db_connection(self, dados_conexao: dict):
        """Retorna uma conexao ODBC baseada nos dados fornecidos ou no tenant atual."""
        from ..core.config import DB_DRIVER, build_odbc_conn_str
        from ..core.database import get_current_tenant
        try:
            tenant = get_current_tenant() or {}
            server = dados_conexao.get("servidor") or tenant.get("server") or ""
            database = dados_conexao.get("banco") or tenant.get("database") or ""
            username = dados_conexao.get("usuario") or tenant.get("username") or ""
            password = dados_conexao.get("senha") or tenant.get("password") or ""
            driver = dados_conexao.get("driver") or tenant.get("driver") or DB_DRIVER
            if not server or not database or not username:
                raise ValueError(
                    "Credenciais de banco incompletas. Cadastre o município em /config/bancos."
                )
            conn_str = build_odbc_conn_str(
                server=server,
                database=database,
                username=username,
                password=password or "",
                driver=driver,
                timeout=30,
            )
            return pyodbc.connect(conn_str)
        except Exception as e:
            logger.error(f"[PythonDB] Erro ao conectar: {e}")
            raise Exception(f"Erro de conexao: {str(e)}")

    async def executar_login(self, integracao: dict, dados_conexao: dict) -> dict:
        login_python = integracao.get("login_python", "")
        login_tipo = integracao.get("login_tipo", "TOKEN")
        if not login_python:
            return {"token": None, "login_tipo": login_tipo, "headers": {}, "cookies": {}, "extra": {}}
        try:
            result = await self._executar_codigo(login_python, dados_conexao, "login", login_tipo=login_tipo)
            if result:
                return {"token": result.get("token"), "cookies": result.get("cookies", {}), "headers": result.get("headers", {}), "login_tipo": login_tipo, "extra": result}
            return {"token": None, "login_tipo": login_tipo, "headers": {}, "cookies": {}, "extra": {}}
        except Exception as e:
            logger.error(f"[PythonLogin] Erro: {e}")
            return {"token": None, "login_tipo": login_tipo, "headers": {}, "cookies": {}, "extra": {}}
    
    async def executar_envio(self, integracao: dict, dados_conexao: dict, payload: str, auth_info: dict = None) -> dict:
        envio_python = integracao.get("envio_python", "")
        if not envio_python:
            return {"status": 400, "response": "Codigo nao configurado"}
        try:
            token = auth_info.get("token") if auth_info else None
            cookies = auth_info.get("cookies", {}) if auth_info else {}
            login_tipo = auth_info.get("login_tipo", "TOKEN") if auth_info else "TOKEN"
            result = await self._executar_codigo(envio_python, dados_conexao, "envio", payload=payload, token=token, cookies=cookies, login_tipo=login_tipo, input_params=auth_info.get("params") if auth_info else None)
            if result:
                return {"status": result.get("status", 200), "response": result.get("response", ""), "extra": result}
            return {"status": 500, "response": "Erro na execucao"}
        except Exception as e:
            logger.error(f"[PythonEnvio] Erro: {e}")
            return {"status": 500, "response": str(e)}
    
    async def _executar_codigo(self, codigo: str, dados_conexao: dict, modo: str, payload: str = None, token: str = None, cookies: dict = None, login_tipo: str = "TOKEN", input_params: dict = None) -> dict:
        def criar_conexao(): return self._get_db_connection(dados_conexao)
        def validate_sql(sql: str):
            sql_upper = (sql or "").upper().strip()
            forbidden = ["DROP ", "ALTER ", "CREATE ", "TRUNCATE ", "GRANT "]
            for cmd in forbidden:
                if cmd in sql_upper: raise Exception(f"SQL proibido: {cmd}")
            if sql_upper.startswith("UPDATE") or sql_upper.startswith("DELETE"):
                if "WHERE " not in sql_upper: raise Exception("UPDATE/DELETE exige WHERE.")

        def executar_consulta(sql: str, params: list = None) -> list:
            validate_sql(sql)
            conn = criar_conexao()
            try:
                cursor = conn.cursor()
                if params: cursor.execute(sql, params)
                else: cursor.execute(sql)
                cols = [col[0] for col in cursor.description] if cursor.description else []
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
            finally: conn.close()

        def executar_dml(sql: str, params: list = None) -> int:
            validate_sql(sql)
            conn = criar_conexao()
            try:
                cursor = conn.cursor()
                if params: cursor.execute(sql, params)
                else: cursor.execute(sql)
                rows = cursor.rowcount
                conn.commit()
                return rows
            finally: conn.close()

        def http_post(url: str, data: str = None, json_data: dict = None, headers: dict = None) -> dict:
            try:
                with httpx.Client(timeout=60) as client:
                    if data: resp = client.post(url, content=data.encode('utf-8'), headers=headers or {})
                    elif json_data: resp = client.post(url, json=json_data, headers=headers or {})
                    else: resp = client.post(url, headers=headers or {})
                    return {"status": resp.status_code, "text": resp.text}
            except Exception as e: return {"status": 500, "text": str(e)}

        def extrair_xml(xml: str, tag: str) -> str:
            match = re.search(f"<{tag}[^>]*>([^<]+)</{tag}>", xml, re.IGNORECASE)
            return match.group(1) if match else ""

        def extrair_json(texto: str, campo: str) -> Any:
            try:
                data = json.loads(texto)
                for p in campo.split('.'):
                    if isinstance(data, dict): data = data.get(p)
                    else: return None
                return data
            except: return None
        
        contexto = {
            "criar_conexao": criar_conexao, "executar_consulta": executar_consulta,
            "executar_update": executar_dml, "executar_insert": executar_dml,
            "executar_delete": executar_dml, "executar_sql": executar_dml,
            "http_post": http_post, "extrair_xml": extrair_xml, "extrair_json": extrair_json,
            "payload": payload, "token": token, "variaveis": input_params or {},
            "params": input_params or {}, "json": json, "re": re, "logger": logger
        }
        try:
            exec(codigo, contexto)
            return contexto.get("resultado", {"success": True})
        except Exception as e:
            logger.error(f"[PythonIntegration] Erro: {e}")
            raise

python_integration_service = PythonIntegrationService()
