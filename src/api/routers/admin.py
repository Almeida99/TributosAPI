import logging
from typing import List

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.deps import get_settings, require_admin
from src.api import repository
from src.api.security import hash_senha

router = APIRouter(prefix="/v1/admin", tags=["Terceiros — admin"])
logger = logging.getLogger(__name__)


class CriarCadastro(BaseModel):
    login: str = Field(..., min_length=1, max_length=255)
    senha: str = Field(..., min_length=6)


class IncluirEndpoint(BaseModel):
    nome_integracao: str = Field(..., min_length=1, max_length=255, description="Deve ser o NOME_INTEGRACAO em TRB_INTEGRACAO")


@router.get("/cadastros", response_model=List[dict])
async def listar_cadastros(_: bool = Depends(require_admin)):
    return repository.listar_cadastros()


@router.post("/cadastros", status_code=status.HTTP_201_CREATED)
async def criar_cadastro(corpo: CriarCadastro, _: bool = Depends(require_admin)):
    h = hash_senha(corpo.senha)
    try:
        nid = repository.inserir_cadastro(corpo.login, h)
    except pyodbc.Error as e:
        if "UNIQUE" in str(e).upper() or "2627" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Login já cadastrado.")
        raise
    return {"id_cadastro": nid, "login": corpo.login}


@router.get("/cadastros/{id_cadastro}/endpoints", response_model=List[dict])
async def listar_endpoints(id_cadastro: int, _: bool = Depends(require_admin)):
    if not repository.buscar_cadastro_por_id(id_cadastro):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cadastro não encontrado.")
    return repository.listar_endpoints_cadastro(id_cadastro)


@router.post("/cadastros/{id_cadastro}/endpoints", status_code=status.HTTP_201_CREATED)
async def incluir_endpoint(id_cadastro: int, corpo: IncluirEndpoint, _: bool = Depends(require_admin)):
    if not repository.buscar_cadastro_por_id(id_cadastro):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cadastro não encontrado.")
    try:
        eid = repository.inserir_endpoint_permitido(id_cadastro, corpo.nome_integracao)
        from src.core.refresher import trigger_refresh
        trigger_refresh()
    except pyodbc.Error as e:
        if "UNIQUE" in str(e).upper() or "2627" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Integração já permitida para este cadastro.",
            )
        raise
    return {"id_endpoint": eid, "nome_integracao": corpo.nome_integracao}
