import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.api import repository
from src.api.deps import get_settings
from src.api.security import criar_token_acesso, verificar_senha

router = APIRouter(prefix="/v1/auth", tags=["Terceiros - autenticacao"])
logger = logging.getLogger(__name__)


class CorpoLogin(BaseModel):
    login: str = Field(..., min_length=1, max_length=255)
    senha: str = Field(..., min_length=1)


@router.post("/token")
async def obter_token(corpo: CorpoLogin, request: Request):
    """
    Gera access_token JWT (expira em 1 hora, configurável).
    """
    settings = get_settings()
    ip = None
    if request.client:
        ip = request.client.host
    xff = request.headers.get("x-forwarded-for")
    if xff:
        ip = xff.split(",")[0].strip()
    ua = (request.headers.get("user-agent") or "")[:512]

    req_json = corpo.json()
    row = repository.buscar_cadastro_por_login(corpo.login)
    if not row or not row.get("ativo"):
        repository.registrar_auditoria(
            None,
            "login",
            metodo_http="POST",
            rota="/v1/auth/token",
            status_http=401,
            endereco_ip=ip,
            user_agent=ua,
            login_tentativa=corpo.login,
            sucesso=False,
            detalhe_erro="Login ou senha inválidos",
            json_requisicao=req_json
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login ou senha inválidos.")

    if not verificar_senha(corpo.senha, row["senha_hash"]):
        repository.registrar_auditoria(
            int(row["id_cadastro"]),
            "login",
            metodo_http="POST",
            rota="/v1/auth/token",
            status_http=401,
            endereco_ip=ip,
            user_agent=ua,
            login_tentativa=corpo.login,
            sucesso=False,
            detalhe_erro="Login ou senha inválidos",
            json_requisicao=req_json
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login ou senha inválidos.")

    exp_min = settings.token_expire_minutes
    token = criar_token_acesso(int(row["id_cadastro"]), settings.jwt_secret, exp_min)
    
    resp_data = {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": exp_min * 60,
    }
    
    repository.registrar_auditoria(
        int(row["id_cadastro"]),
        "login",
        metodo_http="POST",
        rota="/v1/auth/token",
        status_http=200,
        endereco_ip=ip,
        user_agent=ua,
        login_tentativa=corpo.login,
        sucesso=True,
        json_requisicao=req_json,
        json_retorno="{\"access_token\": \"***\", \"token_type\": \"bearer\", \"expires_in\": " + str(exp_min * 60) + "}"
    )
    return resp_data
