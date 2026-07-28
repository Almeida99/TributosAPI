import os
from dataclasses import dataclass


@dataclass
class ApiSettings:
    jwt_secret: str
    token_expire_minutes: int
    orchestrator_usr_cod: int
    admin_key: str


def load_api_settings() -> ApiSettings:
    secret = (os.getenv("API_JWT_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("API_JWT_SECRET é obrigatório para a API de terceiros.")
    return ApiSettings(
        jwt_secret=secret,
        token_expire_minutes=int(os.getenv("API_TOKEN_EXPIRE_MINUTES", "60")),
        orchestrator_usr_cod=int(os.getenv("API_ORCHESTRATOR_USR_COD", "0")),
        admin_key=(os.getenv("API_ADMIN_KEY") or "").strip(),
    )
