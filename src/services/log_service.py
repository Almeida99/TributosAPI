import logging
from ..core.database import db

logger = logging.getLogger(__name__)


class LogService:
    """Serviço para registro de logs de envio"""

    def registrar(self, id_integracao: int, usr_cod: int, valor_where: str, consulta_sql: str,
                  payload: str, status_http: int, resposta_api: str,
                  sucesso: bool, mensagem_erro: str = None,
                  solicitado_por: str = "Sistema", duracao_ms: int = 0) -> int:
        """
        Registra log de envio no banco
        Retorna o ID do log criado
        """
        try:
            sql = """
                INSERT INTO TRB_log_envio
                (id_integracao, usr_cod, valor_where, consulta_sql, payload_enviado,
                 status_http, resposta_api, sucesso, mensagem_erro,
                 solicitado_por, data_hora_envio, duracao_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?)
            """

            params = (
                id_integracao, usr_cod, valor_where, consulta_sql, payload,
                status_http, resposta_api, sucesso, mensagem_erro or "",
                solicitado_por, duracao_ms
            )
            
            db.integracao_query(sql, params)
            
            # Obter ID do log inserido
            result = db.integracao_query("SELECT SCOPE_IDENTITY() AS id")
            return result[0]["id"] if result else 0
            
        except Exception as e:
            logger.error(f"Erro ao registrar log: {e}")
            return 0

    def obter_log(self, id_log_envio: int):
        """Obter log por ID"""
        result = db.integracao_query(
            "SELECT * FROM TRB_log_envio WHERE id_log_envio = ?",
            (id_log_envio,)
        )
        return result[0] if result else None

    def listar_logs(self, id_integracao: int = None, limite: int = 100):
        """Listar logs, opcionalmente filtrados por integração"""
        if id_integracao:
            sql = """
                SELECT TOP (?) * FROM TRB_log_envio 
                WHERE id_integracao = ? 
                ORDER BY data_hora_envio DESC
            """
            params = (limite, id_integracao)
        else:
            sql = """
                SELECT TOP (?) * FROM TRB_log_envio 
                ORDER BY data_hora_envio DESC
            """
            params = (limite,)
        
        return db.integracao_query(sql, params)


log_service = LogService()