import json
import logging
import re
import httpx
import time
from typing import Any

logger = logging.getLogger(__name__)

class AuthService:
    """Serviço de autenticação V3: Focado em flexibilidade via Scripts e Tokens."""

    async def obter_auth(self, integracao: dict) -> dict:
        """
        Em V3, a autenticação básica pode ser feita aqui, 
        mas a recomendação é usar o script_login_py para total controle.
        """
        # Por padrão, V3 foca em headers injetados via script ou básicos
        return {"headers": {}, "cookies": {}}

    def extrair_token(self, resposta: str, campo: str = "token") -> str:
        """Utilitário para extração de tokens de strings JSON ou XML"""
        if not resposta: return ""
        try:
            # Tentar JSON
            data = json.loads(resposta)
            return str(data.get(campo, ""))
        except:
            # Tentar Regex simples em XML
            match = re.search(rf"<{campo}>([^<]+)</{campo}>", resposta, re.IGNORECASE)
            if match: return match.group(1).strip()
        return ""

auth_service = AuthService()