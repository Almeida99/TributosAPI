import logging
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.settings import ApiSettings, load_api_settings
from src.api import repository
from src.api.security import decodificar_token

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
_settings: Optional[ApiSettings] = None


def get_settings() -> ApiSettings:
    global _settings
    if _settings is None:
        _settings = load_api_settings()
    return _settings


def reset_settings_for_tests():
    global _settings
    _settings = None


def require_admin(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    settings: ApiSettings = Depends(get_settings),
):
    if not settings.admin_key or x_admin_key != settings.admin_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chave de administração inválida.")
    return True


def get_cadastro_jwt(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    settings: ApiSettings = Depends(get_settings),
) -> int:
    if not creds or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso necessário (Authorization: Bearer).",
        )
    try:
        data = decodificar_token(creds.credentials, settings.jwt_secret)
        sub = data.get("sub")
        if sub is None:
            raise ValueError("Token sem sub")
        id_cad = int(sub)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
        )
    c = repository.buscar_cadastro_por_id(id_cad)
    if not c:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cadastro inexistente.")
    ativo = c.get("ativo")
    if ativo in (0, False, "0"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cadastro inativo.")
    return id_cad
