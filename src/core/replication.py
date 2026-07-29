"""Replicação de integrações e permissões entre todos os bancos ativos."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.core.database import clear_current_tenant, db, get_current_tenant, set_current_tenant
from src.core.tenants import list_bancos

logger = logging.getLogger(__name__)


def _outros_bancos(slug_atual: Optional[str]) -> List[Dict[str, Any]]:
    slug = (slug_atual or "").strip().lower()
    return [
        b
        for b in list_bancos(apenas_ativos=True)
        if str(b.get("slug", "")).lower() != slug
    ]


def upsert_integracao_em_banco(
    banco: Dict[str, Any],
    nome: str,
    nome_integracao: str,
    ativo: int,
    script_python: str,
) -> None:
    """Cria ou atualiza integração pelo NOME_INTEGRACAO no banco informado."""
    existentes = db.integracao_query(
        "SELECT ID_INTEGRACAO FROM TRB_INTEGRACAO WHERE NOME_INTEGRACAO = ?",
        (nome_integracao,),
    )
    if existentes:
        db.integracao_query(
            """
            UPDATE TRB_INTEGRACAO SET
                NOME=?, ATIVO=?, SCRIPT_PYTHON=?, DATA_ATUALIZACAO=GETDATE()
            WHERE NOME_INTEGRACAO=?
            """,
            (nome, ativo, script_python, nome_integracao),
        )
    else:
        db.integracao_query(
            """
            INSERT INTO TRB_INTEGRACAO (NOME, NOME_INTEGRACAO, ATIVO, SCRIPT_PYTHON)
            VALUES (?, ?, ?, ?)
            """,
            (nome, nome_integracao, ativo, script_python),
        )


def replicar_integracao(
    nome: str,
    nome_integracao: str,
    ativo: int,
    script_python: str,
    slug_origem: Optional[str] = None,
) -> List[str]:
    """
    Propaga a integração para todos os demais bancos ativos.
    Retorna lista de slugs onde falhou (para log).
    Preserva o tenant da requisição atual.
    """
    if not (nome_integracao or "").strip():
        logger.warning("Replicação ignorada: NOME_INTEGRACAO vazio.")
        return []

    tenant_atual = get_current_tenant()
    origem = slug_origem
    if origem is None and tenant_atual:
        origem = tenant_atual.get("slug")

    falhas: List[str] = []
    try:
        for banco in _outros_bancos(origem):
            slug = banco.get("slug") or "?"
            try:
                set_current_tenant(banco)
                upsert_integracao_em_banco(banco, nome, nome_integracao, ativo, script_python)
                logger.info("Integração '%s' replicada em [%s]", nome_integracao, slug)
            except Exception as e:
                logger.error("Falha ao replicar '%s' em [%s]: %s", nome_integracao, slug, e)
                falhas.append(str(slug))
    finally:
        if tenant_atual:
            set_current_tenant(tenant_atual)
        else:
            clear_current_tenant()
    return falhas


def excluir_integracao_em_todos(nome_integracao: str) -> List[str]:
    """Remove a integração (e permissões de terceiro) em todos os bancos ativos."""
    if not (nome_integracao or "").strip():
        return []

    tenant_atual = get_current_tenant()
    falhas: List[str] = []
    try:
        for banco in list_bancos(apenas_ativos=True):
            slug = banco.get("slug") or "?"
            set_current_tenant(banco)
            try:
                try:
                    db.integracao_query(
                        "DELETE FROM TRB_INTEGRACAO_TERCEIROS_ENDPOINT WHERE nome_integracao = ?",
                        (nome_integracao,),
                    )
                except Exception as e:
                    logger.warning("[%s] Limpeza de endpoints terceiros: %s", slug, e)
                db.integracao_query(
                    "DELETE FROM TRB_INTEGRACAO WHERE NOME_INTEGRACAO = ?",
                    (nome_integracao,),
                )
                logger.info("Integração '%s' excluída em [%s]", nome_integracao, slug)
            except Exception as e:
                logger.error("Falha ao excluir '%s' em [%s]: %s", nome_integracao, slug, e)
                falhas.append(str(slug))
    finally:
        if tenant_atual:
            set_current_tenant(tenant_atual)
        else:
            clear_current_tenant()
    return falhas


def conceder_endpoint_terceiro_em_banco(
    banco: Dict[str, Any],
    login: str,
    nome_integracao: str,
) -> bool:
    """
    Concede permissão ao cadastro com o mesmo login no banco.
    Assume que o tenant já está setado para `banco`.
    Retorna False se o login não existir nesse banco.
    """
    rows = db.integracao_query(
        "SELECT id_cadastro FROM TRB_INTEGRACAO_TERCEIROS_CADASTRO WHERE login = ? AND ativo = 1",
        (login,),
    )
    if not rows:
        return False
    id_cadastro = rows[0]["id_cadastro"]
    ja = db.integracao_query(
        """
        SELECT id_endpoint FROM TRB_INTEGRACAO_TERCEIROS_ENDPOINT
        WHERE id_cadastro = ? AND nome_integracao = ? AND ativo = 1
        """,
        (id_cadastro, nome_integracao),
    )
    if ja:
        return True
    db.integracao_query(
        """
        INSERT INTO TRB_INTEGRACAO_TERCEIROS_ENDPOINT (id_cadastro, nome_integracao, ativo)
        VALUES (?, ?, 1)
        """,
        (id_cadastro, nome_integracao),
    )
    return True


def replicar_endpoint_terceiro(
    login: str,
    nome_integracao: str,
    slug_origem: Optional[str] = None,
) -> List[str]:
    """Propaga permissão de endpoint para o mesmo login nos demais bancos."""
    if not login or not nome_integracao:
        return []

    tenant_atual = get_current_tenant()
    origem = slug_origem
    if origem is None and tenant_atual:
        origem = tenant_atual.get("slug")

    sem_login: List[str] = []
    try:
        for banco in _outros_bancos(origem):
            slug = banco.get("slug") or "?"
            try:
                set_current_tenant(banco)
                ok = conceder_endpoint_terceiro_em_banco(banco, login, nome_integracao)
                if ok:
                    logger.info(
                        "Endpoint '%s' concedido ao login '%s' em [%s]",
                        nome_integracao,
                        login,
                        slug,
                    )
                else:
                    logger.info(
                        "Login '%s' inexistente em [%s] — permissão não replicada",
                        login,
                        slug,
                    )
                    sem_login.append(str(slug))
            except Exception as e:
                logger.error(
                    "Falha ao replicar endpoint '%s' para '%s' em [%s]: %s",
                    nome_integracao,
                    login,
                    slug,
                    e,
                )
                sem_login.append(str(slug))
    finally:
        if tenant_atual:
            set_current_tenant(tenant_atual)
        else:
            clear_current_tenant()
    return sem_login


def revogar_endpoint_terceiro_em_todos(login: str, nome_integracao: str) -> None:
    """Remove a permissão do login em todos os bancos ativos."""
    if not login or not nome_integracao:
        return
    tenant_atual = get_current_tenant()
    try:
        for banco in list_bancos(apenas_ativos=True):
            set_current_tenant(banco)
            try:
                rows = db.integracao_query(
                    "SELECT id_cadastro FROM TRB_INTEGRACAO_TERCEIROS_CADASTRO WHERE login = ?",
                    (login,),
                )
                if not rows:
                    continue
                db.integracao_query(
                    """
                    DELETE FROM TRB_INTEGRACAO_TERCEIROS_ENDPOINT
                    WHERE id_cadastro = ? AND nome_integracao = ?
                    """,
                    (rows[0]["id_cadastro"], nome_integracao),
                )
            except Exception as e:
                logger.error(
                    "Falha ao revogar '%s' de '%s' em [%s]: %s",
                    nome_integracao,
                    login,
                    banco.get("slug"),
                    e,
                )
    finally:
        if tenant_atual:
            set_current_tenant(tenant_atual)
        else:
            clear_current_tenant()


def listar_nomes_integracoes_ativas() -> List[str]:
    """NOMES_INTEGRACAO ativos no tenant atual (para OpenAPI)."""
    return [i["nome_tecnico"] for i in listar_integracoes_para_openapi()]


def listar_integracoes_para_openapi(apenas_nomes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Metadados das integrações ativas para documentação:
    nome amigável, nome técnico, exemplo de body.
    """
    from src.core.openapi_expand import exemplo_de_script

    try:
        rows = db.integracao_query(
            """
            SELECT NOME, NOME_INTEGRACAO, SCRIPT_PYTHON
            FROM TRB_INTEGRACAO
            WHERE ATIVO = 1 AND NOME_INTEGRACAO IS NOT NULL AND LTRIM(RTRIM(NOME_INTEGRACAO)) <> ''
            ORDER BY NOME
            """
        )
    except Exception as e:
        logger.warning("Não foi possível listar integrações para OpenAPI: %s", e)
        return []

    filtro = None
    if apenas_nomes is not None:
        filtro = {str(n).strip() for n in apenas_nomes if n}

    out: List[Dict[str, Any]] = []
    vistos = set()
    for r in rows:
        nome_tec = str(r.get("NOME_INTEGRACAO") or "").strip()
        if not nome_tec or nome_tec in vistos:
            continue
        if filtro is not None and nome_tec not in filtro:
            continue
        vistos.add(nome_tec)
        nome = str(r.get("NOME") or nome_tec).strip()
        script = r.get("SCRIPT_PYTHON") or ""
        out.append(
            {
                "nome_tecnico": nome_tec,
                "nome": nome,
                "script": script,
                "exemplo": exemplo_de_script(script if isinstance(script, str) else str(script)),
                "descricao": f"Executa a integração **{nome}** (`{nome_tec}`).",
            }
        )
    return out
