import logging

from src.core.database import db

logger = logging.getLogger(__name__)


def is_fr_usuario_ativo(usr_cod: int) -> bool:
    if not usr_cod or usr_cod <= 0:
        return False
    try:
        res = db.integracao_query(
            "SELECT USR_CODIGO FROM fr_usuario WHERE USR_CODIGO = ? AND USR_BLOQUEIO_USUARIO = 'N'",
            (usr_cod,),
        )
        return len(res) > 0
    except Exception as e:
        logger.error("Erro ao validar usuário técnico %s: %s", usr_cod, e)
        return False
