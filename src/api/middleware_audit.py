import time
import logging
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.api import repository
from src.api.deps import get_settings
from src.api.security import extrair_id_cadastro

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> Optional[str]:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


class AuditoriaRequisicaoMiddleware(BaseHTTPMiddleware):
    """Registra consumo de rotas /v1 (exceto login, documentação e preflight)."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path.rstrip("/").endswith("/docs") or path.endswith("/openapi.json") or path.endswith("/redoc"):
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if "/v1/health" in path:
            return await call_next(request)

        # Capturar corpo da requisição
        req_body = b""
        if request.method in ["POST", "PUT", "PATCH"]:
            req_body = await request.body()
            # Reinjetar o corpo para que o handler possa ler
            async def receive():
                return {"type": "http.request", "body": req_body, "more_body": False}
            request._receive = receive

        start = time.perf_counter()
        try:
            settings = get_settings()
        except Exception as e:
            logger.warning("API terceiros: %s", e)
            settings = None

        id_cad: Optional[int] = None
        if settings:
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                id_cad = extrair_id_cadastro(auth[7:].strip(), settings.jwt_secret)

        try:
            response = await call_next(request)
            
            # Capturar corpo da resposta (apenas se for JSON/XML)
            resp_body = b""
            if settings:
                # Ler o conteúdo da resposta
                content = [chunk async for chunk in response.body_iterator]
                resp_body = b"".join(content)
                # Re-criar a resposta para o cliente
                response = Response(
                    content=resp_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )

        except Exception as e:
            if settings:
                dur = int((time.perf_counter() - start) * 1000)
                repository.registrar_auditoria(
                    id_cad,
                    "requisicao",
                    metodo_http=request.method,
                    rota=path,
                    status_http=500,
                    duracao_ms=dur,
                    endereco_ip=_client_ip(request),
                    user_agent=(request.headers.get("user-agent") or "")[:512],
                    sucesso=False,
                    detalhe_erro=str(e)[:500],
                    json_requisicao=req_body.decode('utf-8', errors='ignore')[:10000] if req_body else None
                )
            raise

        dur = int((time.perf_counter() - start) * 1000)
        if settings:
            repository.registrar_auditoria(
                id_cad,
                "requisicao",
                metodo_http=request.method,
                rota=path,
                status_http=response.status_code,
                duracao_ms=dur,
                endereco_ip=_client_ip(request),
                user_agent=(request.headers.get("user-agent") or "")[:512],
                sucesso=200 <= response.status_code < 400,
                json_requisicao=req_body.decode('utf-8', errors='ignore')[:10000] if req_body else None,
                json_retorno=resp_body.decode('utf-8', errors='ignore')[:10000] if resp_body else None
            )
        return response
