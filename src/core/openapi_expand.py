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


def exemplo_de_script(script: Optional[str]) -> Dict[str, Any]:
    """Extrai chaves de params.get(...) do script e monta um exemplo de body."""
    if not script:
        return {"pagina": 1}

    exemplo: Dict[str, Any] = {}
    for m in _PARAMS_GET_RE.finditer(script):
        chave = m.group(1).strip()
        if not chave or chave in exemplo:
            continue
        raw_default = (m.group(2) or "").strip()
        if not raw_default:
            exemplo[chave] = "string"
            continue
        # Literais simples
        if raw_default.lower() in ("true", "false"):
            exemplo[chave] = raw_default.lower() == "true"
        elif raw_default.isdigit():
            exemplo[chave] = int(raw_default)
        elif (raw_default.startswith("'") and raw_default.endswith("'")) or (
            raw_default.startswith('"') and raw_default.endswith('"')
        ):
            exemplo[chave] = raw_default[1:-1]
        else:
            # default complexo (ex.: expressão) — usa placeholder tipado
            if "int(" in raw_default or "isdigit" in raw_default:
                exemplo[chave] = 1
            else:
                exemplo[chave] = "string"

    return exemplo or {"pagina": 1}


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
    - dict: {nome_tecnico, nome, exemplo, descricao}
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
                        "descricao": f"Executa a integração `{nome_tec}`.",
                    }
                )
        elif isinstance(item, dict):
            nome_tec = str(item.get("nome_tecnico") or item.get("nome_integracao") or "").strip()
            if not nome_tec:
                continue
            nome = str(item.get("nome") or nome_tec).strip()
            exemplo = item.get("exemplo")
            if not isinstance(exemplo, dict) or not exemplo:
                exemplo = default_example or exemplo_de_script(item.get("script"))
            items.append(
                {
                    "nome_tecnico": nome_tec,
                    "nome": nome,
                    "exemplo": exemplo,
                    "descricao": item.get("descricao")
                    or f"Executa a integração **{nome}** (`{nome_tec}`).",
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
                # Remove path param nome_int (já está no path concreto)
                params = [
                    p
                    for p in (m.get("parameters") or [])
                    if not (p.get("name") == "nome_int" and p.get("in") == "path")
                ]
                m["parameters"] = params
                # Exemplo de body
                rb = m.get("requestBody")
                if isinstance(rb, dict):
                    content = rb.get("content") or {}
                    for _ctype, media in content.items():
                        if not isinstance(media, dict):
                            continue
                        media["example"] = info["exemplo"]
                        schema = media.get("schema")
                        if isinstance(schema, dict):
                            schema["example"] = info["exemplo"]
                            # Prefer object livre com exemplo
                            if schema.get("type") != "object":
                                media["schema"] = {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "example": info["exemplo"],
                                }
                else:
                    m["requestBody"] = {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "example": info["exemplo"],
                                },
                                "example": info["exemplo"],
                            }
                        },
                    }
            filtered[f"/v1/executar/{nome_tec}"] = methods
    # Sem integrações: não expõe o catch-all genérico {nome_int}

    openapi["paths"] = filtered
    return openapi
