import logging
import re
from ..core.database import db

logger = logging.getLogger(__name__)

class ConsultaService:
    """Serviço para executar consultas SQL e gerar dados (V3)"""

    def obter_integracao(self, id_integracao: int):
        """Busca integração por ID"""
        result = db.integracao_query(
            "SELECT * FROM TRB_integracao WHERE id_integracao = ? AND ativo = 1",
            (id_integracao,)
        )
        return result[0] if result else None

    def listar_integracoes(self):
        """Lista todas as integrações ativas (Schema V3)"""
        return db.integracao_query(
            "SELECT id_integracao, nome, descricao, ativo FROM TRB_integracao WHERE ativo = 1 ORDER BY id_integracao"
        )

    def executar_consulta(self, target_db: dict, sql: str, params: dict):
        """Executa consulta no banco de origem com substituição de placeholders."""
        sql_final = sql
        for k, v in params.items():
            sql_final = sql_final.replace("{" + str(k) + "}", str(v))
        
        logger.info(f"[Consulta V3] Executando: {sql_final[:100]}...")
        return db.origem_sp(target_db, sql_final, [])

consulta_service = ConsultaService()