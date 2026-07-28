import time
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_senha(plain: str) -> str:
    return _pwd.hash(plain)


def verificar_senha(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def criar_token_acesso(
    sub_id_cadastro: int, secret: str, expira_minutos: int, extra: Optional[dict[str, Any]] = None
) -> str:
    now = int(time.time())
    exp = now + expira_minutos * 60
    claims: dict = {
        "sub": str(sub_id_cadastro),
        "exp": exp,
        "iat": now,
    }
    if extra:
        claims.update(extra)
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decodificar_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=[ALGORITHM])


def extrair_id_cadastro(token: str, secret: str) -> Optional[int]:
    try:
        data = decodificar_token(token, secret)
        sub = data.get("sub")
        if sub is None:
            return None
        return int(sub)
    except (JWTError, ValueError, TypeError):
        return None
