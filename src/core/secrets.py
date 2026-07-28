"""Criptografia de senhas do catálogo multibanco (Fernet)."""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

_ENC_PREFIX = "enc:v1:"


@lru_cache(maxsize=1)
def _fernet():
    from cryptography.fernet import Fernet

    key = (os.getenv("BANCOS_SECRET_KEY") or "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except Exception as e:
        logger.error("BANCOS_SECRET_KEY inválida (use Fernet.generate_key()): %s", e)
        return None


def has_secret_key() -> bool:
    return _fernet() is not None


def is_encrypted(value: Optional[str]) -> bool:
    return bool(value) and str(value).startswith(_ENC_PREFIX)


def encrypt_password(plain: str) -> str:
    """Cifra senha para persistência. Exige BANCOS_SECRET_KEY."""
    if plain is None:
        plain = ""
    if is_encrypted(plain):
        return plain
    f = _fernet()
    if f is None:
        raise ValueError(
            "BANCOS_SECRET_KEY não configurada. "
            "Gere com: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    token = f.encrypt(plain.encode("utf-8")).decode("utf-8")
    return f"{_ENC_PREFIX}{token}"


def decrypt_password(value: Optional[str]) -> str:
    """
    Descriptografa senha do catálogo.
    Valores sem prefixo enc:v1: são tratados como texto puro (legado).
    """
    if not value:
        return ""
    raw = str(value)
    if not is_encrypted(raw):
        return raw
    f = _fernet()
    if f is None:
        raise ValueError(
            "Há senhas cifradas em bancos.json, mas BANCOS_SECRET_KEY não está definida."
        )
    token = raw[len(_ENC_PREFIX) :]
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Falha ao descriptografar senha do catálogo: {e}") from e
