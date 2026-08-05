"""Autenticação HTTP Basic compartilhada para superfícies administrativas."""
from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from src.core.config import CONFIG_ADMIN_PASSWORD, CONFIG_ADMIN_USER

ADMIN_BASIC_REALM = "TributosAPI Admin"

_basic = HTTPBasic(auto_error=False)


def require_admin_basic(
    credentials: Optional[HTTPBasicCredentials] = Depends(_basic),
) -> str:
    """Exige as credenciais administrativas configuradas no ambiente."""
    if not CONFIG_ADMIN_USER or not CONFIG_ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Administração desabilitada: defina CONFIG_ADMIN_USER e "
                "CONFIG_ADMIN_PASSWORD no .env."
            ),
        )

    authenticate_header = {"WWW-Authenticate": f'Basic realm="{ADMIN_BASIC_REALM}"'}
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
            headers=authenticate_header,
        )

    user_ok = secrets.compare_digest(credentials.username, CONFIG_ADMIN_USER)
    password_ok = secrets.compare_digest(credentials.password, CONFIG_ADMIN_PASSWORD)
    if not (user_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha inválidos.",
            headers=authenticate_header,
        )

    return credentials.username
