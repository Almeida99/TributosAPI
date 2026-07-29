"""Helpers para expandir catch-all /v1/executar/{nome} no OpenAPI."""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Union

# params.get('chave') / params.get("chave", default)
_PARAMS_GET_RE = re.compile(
    r"""params\.get\(\s*['"]([^'"]+)['"](?:\s*,\s*([^)]+))?\)""",
    re.IGNORECASE,
)

_DESC_FILTROS = (
    "O body JSON é um objeto livre de **filtros**. "
    "Cada campo enviado é repassado ao script da integração em `params` "
    "(ex.: `params.get('inscricao')`, `params.get('pagina')`). "
    "Campos não listados no exemplo também são aceitos, se o script os utilizar."
)


def _valor_exemplo_e_tipo(raw_default: str) -> tuple:
    """Retorna (exemplo, tipo_openapi) a partir do default do params.get."""
    raw_default = (raw_default or "").strip()
    if not raw_default:
        return "string", "string"
    if raw_default.lower() in ("true", "false"):
        return raw_default.lower() == "true", "boolean"
    if raw_default.isdigit():
        return int(raw_default), "integer"
    if (raw_default.startswith("'") and raw_default.endswith("'")) or (
        raw_default.startswith('"') and raw_default.endswith('"')
    ):
        return raw_default[1:-1], "string"
    if "int(" in raw_default or "isdigit" in raw_default:
        return 1, "integer"
    return "string", "string"


def campos_de_script(script: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Mapa campo → {exemplo, tipo, description} extraído do script."""
    if not script:
        return {
            "pagina": {
                "exemplo": 1,
                "tipo": "integer",
                "description": "Filtro/parâmetro enviado no JSON (params['pagina']).",
            }
        }

    campos: Dict[str, Dict[str, Any]] = {}
    for m in _PARAMS_GET_RE.finditer(script):
        chave = m.group(1).strip()
        if not chave or chave in campos:
            continue
        exemplo, tipo = _valor_exemplo_e_tipo(m.group(2) or "")
        campos[chave] = {
            "exemplo": exemplo,
            "tipo": tipo,
            "description": f"Filtro opcional. Disponível no script como params.get('{chave}').",
        }
    if not campos:
        campos["pagina"] = {
            "exemplo": 1,
            "tipo": "integer",
            "description": "Filtro/parâmetro enviado no JSON (params['pagina']).",
        }
    return campos


def exemplo_de_script(script: Optional[str]) -> Dict[str, Any]:
    """Extrai chaves de params.get(...) do script e monta um exemplo de body."""
    return {k: v["exemplo"] for k, v in campos_de_script(script).items()}


def _schema_filtros(exemplo: Dict[str, Any], script: Optional[str] = None) -> Dict[str, Any]:
    """Schema OpenAPI deixando explícito que o JSON são filtros livres."""
    campos = campos_de_script(script) if script is not None else {}
    properties: Dict[str, Any] = {}
    for chave, meta in campos.items():
        properties[chave] = {
            "type": meta["tipo"],
            "description": meta["description"],
            "example": meta["exemplo"],
        }
    for chave, val in (exemplo or {}).items():
        if chave in properties:
            continue
        t = "integer" if isinstance(val, int) else "boolean" if isinstance(val, bool) else "string"
        properties[chave] = {
            "type": t,
            "description": f"Filtro opcional (params['{chave}']).",
            "example": val,
        }
    return {
        "type": "object",
        "description": _DESC_FILTROS,
        "properties": properties,
        "additionalProperties": {
            "description": "Qualquer outro campo JSON também é aceito como filtro (params).",
        },
        "example": exemplo or {"pagina": 1},
    }


def expand_executar_paths(
    openapi: Dict[str, Any],
    catch_path: str,
    integracoes: List[Union[str, Dict[str, Any]]],
    *,
    keep_paths: Optional[List[str]] = None,
    default_example: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Substitui o path catch-all por um path concreto por integração.

    Cada item de `integracoes` pode ser:
    - str: só o nome técnico (NOME_INTEGRACAO)
    - dict: {nome_tecnico, nome, exemplo, descricao, script}
    """
    keep = set(keep_paths or [])
    original_paths = openapi.get("paths") or {}
    filtered: Dict[str, Any] = {}

    for path, methods in original_paths.items():
        if path in keep:
            filtered[path] = methods

    catch = original_paths.get(catch_path)
    items: List[Dict[str, Any]] = []
    for item in integracoes or []:
        if isinstance(item, str):
            nome_tec = item.strip()
            if nome_tec:
                items.append(
                    {
                        "nome_tecnico": nome_tec,
                        "nome": nome_tec,
                        "exemplo": default_example or {"pagina": 1},
                        "script": None,
                        "descricao": (
                            f"Executa a integração `{nome_tec}`.\n\n{_DESC_FILTROS}"
                        ),
                    }
                )
        elif isinstance(item, dict):
            nome_tec = str(item.get("nome_tecnico") or item.get("nome_integracao") or "").strip()
            if not nome_tec:
                continue
            nome = str(item.get("nome") or nome_tec).strip()
            script = item.get("script")
            exemplo = item.get("exemplo")
            if not isinstance(exemplo, dict) or not exemplo:
                exemplo = default_example or exemplo_de_script(script)
            base_desc = item.get("descricao") or f"Executa a integração **{nome}** (`{nome_tec}`)."
            items.append(
                {
                    "nome_tecnico": nome_tec,
                    "nome": nome,
                    "exemplo": exemplo,
                    "script": script,
                    "descricao": f"{base_desc}\n\n{_DESC_FILTROS}",
                }
            )

    if catch and items:
        for info in items:
            nome_tec = info["nome_tecnico"]
            methods = copy.deepcopy(catch)
            for m in methods.values():
                if not isinstance(m, dict):
                    continue
                m["summary"] = info["nome"]
                m["description"] = info["descricao"]
                m["operationId"] = f"executar_{re.sub(r'[^a-zA-Z0-9_]', '_', nome_tec)}"
                m["tags"] = ["Integrações"]
                params = [
                    p
                    for p in (m.get("parameters") or [])
                    if not (p.get("name") == "nome_int" and p.get("in") == "path")
                ]
                m["parameters"] = params

                schema_body = _schema_filtros(info["exemplo"], info.get("script"))
                m["requestBody"] = {
                    "required": False,
                    "description": (
                        "JSON de filtros. Envie no body os campos que deseja filtrar; "
                        "eles ficam disponíveis no script via `params`."
                    ),
                    "content": {
                        "application/json": {
                            "schema": schema_body,
                            "example": info["exemplo"],
                        }
                    },
                }
            filtered[f"/v1/executar/{nome_tec}"] = methods

    openapi["paths"] = filtered
    return openapi


def aplicar_base_banco(
    openapi: Dict[str, Any],
    *,
    path_prefix: str = "",
) -> Dict[str, Any]:
    """
    Faz a documentação refletir a URL real com o slug do banco.

    Ex.: path_prefix="" → /bonfim/v1/executar/HIPAC
         path_prefix="/api" → /bonfim/api/v1/executar/HIPAC
    """
    from src.core.database import get_current_tenant

    tenant = get_current_tenant()
    if not tenant or not tenant.get("slug"):
        openapi["servers"] = [
            {
                "url": "/",
                "description": "Sem banco no path — acesse /{slug}/docs",
            }
        ]
        return openapi

    slug = str(tenant["slug"]).strip("/")
    nome = tenant.get("nome") or slug
    base = f"/{slug}{path_prefix}".rstrip("/") or f"/{slug}"

    original = openapi.get("paths") or {}
    prefixed: Dict[str, Any] = {}
    for path, methods in original.items():
        p = path if path.startswith("/") else f"/{path}"
        prefixed[f"{base}{p}"] = methods
    openapi["paths"] = prefixed

    openapi["servers"] = [
        {
            "url": "/",
            "description": f"Banco: {nome} (/{slug})",
        }
    ]

    info = dict(openapi.get("info") or {})
    desc = (info.get("description") or "").rstrip()
    info["description"] = (
        f"{desc}\n\n"
        f"**Banco atual:** `{slug}` — as URLs incluem o prefixo `/{slug}`.\n\n"
        "**Filtros:** no `POST .../v1/executar/{{nome}}`, o body JSON é um objeto livre; "
        "cada campo é um filtro repassado ao script (`params`)."
    ).strip()
    openapi["info"] = info
    return openapi
