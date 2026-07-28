"""Helpers para expandir catch-all /v1/executar/{nome} no OpenAPI."""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


def expand_executar_paths(
    openapi: Dict[str, Any],
    catch_path: str,
    nomes: List[str],
    *,
    keep_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Substitui o path catch-all por um path concreto por integração.
    keep_paths: paths que devem permanecer (ex.: /v1/auth/token).
    """
    keep = set(keep_paths or [])
    original_paths = openapi.get("paths") or {}
    filtered: Dict[str, Any] = {}

    for path, methods in original_paths.items():
        if path in keep:
            filtered[path] = methods

    catch = original_paths.get(catch_path)
    if catch and nomes:
        for nome in nomes:
            methods = copy.deepcopy(catch)
            for m in methods.values():
                if not isinstance(m, dict):
                    continue
                m["summary"] = nome
                m["operationId"] = f"executar_{nome}"
                params = [
                    p
                    for p in (m.get("parameters") or [])
                    if not (p.get("name") == "nome_int" and p.get("in") == "path")
                ]
                m["parameters"] = params
            filtered[f"/v1/executar/{nome}"] = methods
    elif catch and not nomes:
        # Sem integrações: mantém o catch-all visível para documentação genérica
        filtered[catch_path] = catch

    openapi["paths"] = filtered
    return openapi
