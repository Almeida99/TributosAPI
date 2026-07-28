"""Middleware que resolve o banco pelo primeiro segmento do path."""
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from src.core.database import clear_current_tenant, set_current_tenant
from src.core.tenants import RESERVED_SLUGS, get_banco

logger = logging.getLogger(__name__)


class TenantPathMiddleware(BaseHTTPMiddleware):
    """
    URLs no formato /{slug}/... usam o banco configurado com esse slug.
    O prefixo /{slug} é removido do path interno para as rotas existentes
    continuarem em /integracoes, /api, /v1, etc.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.scope.get("path") or request.url.path or "/"
        parts = [p for p in path.split("/") if p]

        if not parts:
            return await call_next(request)

        first = parts[0].lower()

        # Rotas globais (sem tenant)
        if first in RESERVED_SLUGS:
            return await call_next(request)

        banco = get_banco(first)
        if not banco:
            # Path sem banco conhecido: deixa passar (pode ser 404 das rotas)
            # Exceto se parece tentativa de tenant inválido com subpath
            if len(parts) >= 1:
                accept = (request.headers.get("accept") or "").lower()
                if "text/html" in accept:
                    return RedirectResponse(url="/?erro=banco_invalido", status_code=302)
                return JSONResponse(
                    status_code=404,
                    content={"detail": f"Banco '{first}' não encontrado. Configure em /config/bancos."},
                )
            return await call_next(request)

        if not banco.get("ativo", True):
            return JSONResponse(
                status_code=403,
                content={"detail": f"Banco '{first}' está inativo."},
            )

        set_current_tenant(banco)
        request.state.banco = banco["slug"]
        request.state.banco_nome = banco.get("nome") or banco["slug"]

        new_path = "/" + "/".join(parts[1:]) if len(parts) > 1 else "/"
        request.scope["path"] = new_path
        if "raw_path" in request.scope:
            request.scope["raw_path"] = new_path.encode("utf-8")

        try:
            return await call_next(request)
        finally:
            clear_current_tenant()
