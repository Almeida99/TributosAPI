"""Catálogo multibanco — persistido em data/bancos.json."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.config import build_odbc_conn_str
from src.core.secrets import decrypt_password, encrypt_password, has_secret_key, is_encrypted

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_LOCK = threading.RLock()

# Segmentos de path reservados (não podem ser slug de banco)
RESERVED_SLUGS = frozenset({
    "config", "api", "docs", "static", "openapi.json", "favicon.ico",
    "health", "redoc",
})

DATA_DIR = Path(os.getenv("BANCOS_DATA_DIR", "data"))
BANCOS_FILE = Path(os.getenv("BANCOS_FILE", str(DATA_DIR / "bancos.json")))


def _ensure_store() -> None:
    """Garante data/bancos.json vazio — cadastro só pela interface /config/bancos."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not BANCOS_FILE.exists():
        BANCOS_FILE.write_text(
            json.dumps({"bancos": []}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Catálogo de bancos criado (vazio) em %s", BANCOS_FILE)


def _migrate_plaintext_passwords(data: Dict[str, Any]) -> bool:
    """Cifra senhas em texto puro quando BANCOS_SECRET_KEY está disponível."""
    if not has_secret_key():
        return False
    changed = False
    for b in data.get("bancos") or []:
        if not isinstance(b, dict):
            continue
        pwd = b.get("password") or ""
        if pwd and not is_encrypted(pwd):
            try:
                b["password"] = encrypt_password(pwd)
                changed = True
            except ValueError as e:
                logger.warning("Não foi possível cifrar senha do banco %s: %s", b.get("slug"), e)
    return changed


def _read_raw() -> Dict[str, Any]:
    _ensure_store()
    try:
        data = json.loads(BANCOS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Falha ao ler %s: %s", BANCOS_FILE, e)
        return {"bancos": []}
    if not isinstance(data, dict):
        return {"bancos": []}
    bancos = data.get("bancos")
    if not isinstance(bancos, list):
        data["bancos"] = []
    if _migrate_plaintext_passwords(data):
        try:
            _write_raw(data)
            logger.info("Senhas do catálogo migradas para formato cifrado.")
        except OSError as e:
            logger.error("Falha ao gravar migração de senhas: %s", e)
    return data


def _write_raw(data: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = BANCOS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(BANCOS_FILE)


def _with_decrypted_password(banco: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(banco)
    try:
        out["password"] = decrypt_password(out.get("password"))
    except ValueError as e:
        logger.error("Senha do banco %s: %s", out.get("slug"), e)
        out["password"] = ""
    return out


def validate_slug(slug: str) -> str:
    slug = (slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValueError(
            "Slug inválido. Use letras minúsculas, números, hífen ou underscore "
            "(máx. 63 caracteres, começando com letra/número)."
        )
    if slug in RESERVED_SLUGS:
        raise ValueError(f"Slug '{slug}' é reservado pelo sistema.")
    return slug


def list_bancos(apenas_ativos: bool = False) -> List[Dict[str, Any]]:
    with _LOCK:
        bancos = [_with_decrypted_password(b) for b in (_read_raw().get("bancos") or []) if isinstance(b, dict)]
    if apenas_ativos:
        bancos = [b for b in bancos if b.get("ativo", True)]
    return bancos


def get_banco(slug: str) -> Optional[Dict[str, Any]]:
    slug = (slug or "").strip().lower()
    for b in list_bancos():
        if str(b.get("slug", "")).lower() == slug:
            return dict(b)
    return None


def upsert_banco(dados: Dict[str, Any], slug_original: Optional[str] = None) -> Tuple[Dict[str, Any], bool]:
    """
    Cria ou atualiza um banco. `slug_original` identifica o registro ao renomear o slug.
    Retorna (banco_decifrado, criado: bool).
    """
    slug = validate_slug(dados.get("slug", ""))
    nome = (dados.get("nome") or slug).strip()
    server = (dados.get("server") or "").strip()
    database = (dados.get("database") or "").strip()
    username = (dados.get("username") or "").strip()
    password = dados.get("password")
    driver = (dados.get("driver") or "ODBC Driver 18 for SQL Server").strip()
    ativo = bool(dados.get("ativo", True))

    if not server or not database or not username:
        raise ValueError("Servidor, database e usuário são obrigatórios.")

    if not has_secret_key():
        raise ValueError(
            "BANCOS_SECRET_KEY é obrigatória para gravar bancos. "
            "Gere com: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    with _LOCK:
        raw = _read_raw()
        bancos: List[Dict[str, Any]] = list(raw.get("bancos") or [])
        key = (slug_original or slug).strip().lower()

        existing_idx = next(
            (i for i, b in enumerate(bancos) if str(b.get("slug", "")).lower() == key),
            None,
        )
        criado = existing_idx is None

        # Conflito de slug com outro registro
        for i, b in enumerate(bancos):
            if str(b.get("slug", "")).lower() == slug and i != existing_idx:
                raise ValueError(f"Já existe um banco com o slug '{slug}'.")

        if password is None or password == "":
            if existing_idx is None:
                raise ValueError("Senha é obrigatória para novo banco.")
            password_plain = decrypt_password(bancos[existing_idx].get("password", ""))
        else:
            password_plain = decrypt_password(password) if is_encrypted(str(password)) else str(password)

        entry = {
            "slug": slug,
            "nome": nome,
            "server": server,
            "database": database,
            "username": username,
            "password": encrypt_password(password_plain),
            "driver": driver,
            "ativo": ativo,
        }

        if existing_idx is None:
            bancos.append(entry)
        else:
            bancos[existing_idx] = entry

        raw["bancos"] = bancos
        _write_raw(raw)
        return _with_decrypted_password(entry), criado


def delete_banco(slug: str) -> bool:
    slug = (slug or "").strip().lower()
    with _LOCK:
        raw = _read_raw()
        bancos = list(raw.get("bancos") or [])
        novos = [b for b in bancos if str(b.get("slug", "")).lower() != slug]
        if len(novos) == len(bancos):
            return False
        raw["bancos"] = novos
        _write_raw(raw)
        return True


def banco_to_conn_dict(banco: Dict[str, Any]) -> Dict[str, str]:
    """Formato usado por Database / scripts de integração."""
    pwd = banco.get("password") or ""
    if is_encrypted(pwd):
        pwd = decrypt_password(pwd)
    return {
        "servidor": banco.get("server") or "",
        "banco": banco.get("database") or "",
        "usuario": banco.get("username") or "",
        "senha": pwd,
        "driver": banco.get("driver") or "ODBC Driver 18 for SQL Server",
        "nome": banco.get("nome") or banco.get("slug") or "",
        "slug": banco.get("slug") or "",
    }


def testar_conexao(banco: Dict[str, Any]) -> None:
    """Abre conexão ODBC e executa SELECT 1. Levanta Exception em falha."""
    import pyodbc

    cfg = banco_to_conn_dict(banco)
    conn_str = build_odbc_conn_str(
        server=cfg["servidor"],
        database=cfg["banco"],
        username=cfg["usuario"],
        password=cfg["senha"],
        driver=cfg["driver"],
        timeout=10,
    )
    conn = pyodbc.connect(conn_str, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
    finally:
        conn.close()
