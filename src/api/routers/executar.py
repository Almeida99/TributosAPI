import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from src.services.orchestrator import orchestrator
from src.api.deps import get_cadastro_jwt, get_settings
from src.api import repository
from src.api.validators import is_fr_usuario_ativo

router = APIRouter(prefix="/v1", tags=["Terceiros Integracoes"])
logger = logging.getLogger(__name__)


# Modelo genérico para múltiplos filtros
PayloadTerceiro = Dict[str, Any]


# Os endpoints são registrados dinamicamente no main.py para cada integração ativa.
