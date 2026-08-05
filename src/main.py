import json
import logging
import os
from typing import Any, Dict, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from src.core.admin_auth import require_admin_basic
from src.core.database import db, get_current_tenant
from src.core.tenant_middleware import TenantPathMiddleware
from src.core.tenants import list_bancos
from src.services.orchestrator import orchestrator
from src.ui.config_router import router as config_router
from src.ui.router import router as ui_router

PayloadParams = Dict[str, Any]

logger = logging.getLogger("uvicorn.error")
templates = Jinja2Templates(directory=["src/ui/templates", "src/ui"])

app = FastAPI(
    title="TributosAPI",
    description="Motor de Integração multibanco — acesse /{banco}/docs",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Middleware: CORS primeiro; tenant por último a ser adicionado = executa primeiro no request
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantPathMiddleware)


def _build_main_openapi() -> dict:
    """OpenAPI de consumo: /{banco}/api/v1/... com Bearer JWT."""
    from fastapi.openapi.utils import get_openapi

    from src.core.database import get_current_tenant
    from src.core.openapi_expand import aplicar_base_banco, expand_executar_paths
    from src.core.replication import listar_integracoes_para_openapi

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=(
            "API de consumo para terceiros. "
            "1) POST /v1/auth/token → 2) Authorize (Bearer) → 3) POST /v1/executar/{nome}."
        ),
        routes=app.routes,
    )
    # Não documenta a rota interna do painel (sem JWT)
    paths = schema.get("paths") or {}
    paths.pop("/v1/executar/{nome_int}", None)
    schema["paths"] = paths

    integracoes = []
    if get_current_tenant():
        integracoes = listar_integracoes_para_openapi()
    expand_executar_paths(
        schema,
        "/v1/executar/{nome_int}",
        integracoes,
        keep_paths=["/v1/auth/token"],
        require_bearer=True,
    )
    # Documenta a URL real de consumo (mount /api)
    return aplicar_base_banco(schema, path_prefix="/api")


@app.get("/openapi.json", include_in_schema=False)
async def openapi_json():
    """Relativo a /{slug}/openapi.json — preserva o tenant do middleware."""
    return _build_main_openapi()


@app.get("/docs", include_in_schema=False)
async def swagger_docs():
    from fastapi.openapi.docs import get_swagger_ui_html

    return get_swagger_ui_html(
        openapi_url="./openapi.json",
        title=f"{app.title} - Docs",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        swagger_ui_parameters={"persistAuthorization": True},
    )

# --- API de integração com terceiros (JWT, docs em /api/docs) — opcional via env ---
_api_subapp: Optional[FastAPI] = None

if os.getenv("API_JWT_SECRET", "").strip():
    try:
        from src.api.app import build_api_app

        _api_subapp = build_api_app()
        app.mount("/api", _api_subapp)
        logger.info("Módulo /api (API terceiros) carregado; use /{banco}/api/docs")
    except Exception as e:
        logger.exception("Falha ao carregar o módulo de API terceiros: %s", e)
        raise


def is_active_user(usr_cod: int) -> bool:
    """Verifica se o usuário existe e não está bloqueado no banco do tenant."""
    try:
        res = db.integracao_query(
            "SELECT USR_CODIGO FROM fr_usuario WHERE USR_CODIGO = ? AND USR_BLOQUEIO_USUARIO = 'N'",
            (usr_cod,),
        )
        return len(res) > 0
    except Exception as e:
        logger.error(f"Erro ao validar usuário {usr_cod}: {e}")
        return False


def _require_tenant():
    if not get_current_tenant():
        raise HTTPException(
            status_code=400,
            detail="Informe o banco no path: /{banco}/.... Configure em /config/bancos.",
        )


@app.get("/api/v1/health", include_in_schema=False)
async def health_check():
    return {
        "status": "healthy",
        "engine": "Motor-Core",
        "bancos": len(list_bancos(apenas_ativos=True)),
    }


@app.get("/api/v1/info", include_in_schema=False)
async def public_info():
    tenant = get_current_tenant()
    if not tenant:
        return {
            "servico": "TributosAPI",
            "status": "online",
            "bancos_ativos": [b["slug"] for b in list_bancos(apenas_ativos=True)],
        }
    try:
        ativas = db.integracao_query("SELECT COUNT(*) as t FROM TRB_integracao WHERE ativo = 1")[0]["t"]
        return {
            "servico": "TributosAPI",
            "banco": tenant.get("slug"),
            "integracoes_ativas": ativas,
            "status": "online",
        }
    except Exception:
        return {"status": "online", "mode": "maintenance", "banco": tenant.get("slug")}


async def _executar_interno(nome: str, usr_cod: Optional[int], payload_params: Optional[PayloadParams]):
    _require_tenant()
    current_user = usr_cod
    if current_user is None:
        res_def = db.integracao_query(
            "SELECT TOP 1 USR_CODIGO FROM fr_usuario WHERE USR_BLOQUEIO_USUARIO = 'N' ORDER BY USR_CODIGO"
        )
        current_user = res_def[0]["USR_CODIGO"] if res_def else 1

    if not is_active_user(current_user):
        raise HTTPException(status_code=403, detail=f"Acesso negado: Usuário {current_user} inválido.")

    res = await orchestrator.run(nome, current_user, payload_params or {})
    if isinstance(res, str):
        media_type = "application/xml" if res.strip().startswith("<") else "text/plain"
        return Response(content=res, media_type=media_type)
    if isinstance(res, dict):
        return JSONResponse(content=json.loads(json.dumps(res, default=str)))
    return res


async def _executar_parceiro(nome: str, id_cadastro: int, payload_params: Dict[str, Any]):
    _require_tenant()
    from src.api import repository
    from src.api.deps import get_settings

    if not repository.tem_permissao_endpoint(id_cadastro, nome):
        raise HTTPException(status_code=403, detail="Acesso não autorizado para esta integração.")

    s = get_settings()
    res = await orchestrator.run(
        nome, s.orchestrator_usr_cod, payload_params or {}, id_cadastro_terceiro=id_cadastro
    )
    if isinstance(res, str):
        media_type = "application/xml" if res.strip().startswith("<") else "text/plain"
        return Response(content=res, media_type=media_type)
    if isinstance(res, dict):
        return JSONResponse(content=json.loads(json.dumps(res, default=str)))
    return res


def registrar_endpoints():
    """
    Registra rotas catch-all de execução.
    O banco é resolvido pelo path /{banco}/... (middleware); as integrações
    são buscadas no SQL do tenant no momento da chamada.
    """
    logger.info("Registrando endpoints dinâmicos (multibanco)...")
    try:
        # Remover rotas dinâmicas anteriores (por nome)
        nomes_dyn = {
            "api_executar_catch",
            "partner_executar_catch",
        }
        app.routes[:] = [
            r for r in app.routes if getattr(r, "name", None) not in nomes_dyn
        ]
        app.openapi_schema = None

        if _api_subapp:
            _api_subapp.routes[:] = [
                r
                for r in _api_subapp.routes
                if getattr(r, "name", None) != "partner_executar_catch"
            ]
            _api_subapp.openapi_schema = None

        async def handler_interno(
            nome_int: str,
            payload_params: Optional[PayloadParams] = Body(
                None,
                example={"pagina": 1, "filtro": "exemplo"},
                description=(
                    "É possível passar campos no JSON do body; cada campo será usado como filtro."
                ),
            ),
            usr_cod: Optional[int] = Query(None),
        ):
            return await _executar_interno(nome_int, usr_cod, payload_params)

        # Rota interna do painel (usr_cod) — fora do Swagger público
        app.add_api_route(
            path="/v1/executar/{nome_int}",
            endpoint=handler_interno,
            methods=["POST"],
            dependencies=[Depends(require_admin_basic)],
            tags=["Integrações"],
            name="api_executar_catch",
            include_in_schema=False,
        )

        if _api_subapp:
            from src.api.deps import get_cadastro_jwt

            async def partner_handler(
                nome_int: str,
                payload_params: Dict[str, Any] = Body(
                    ...,
                    example={"pagina": 1},
                    description=(
                        "É possível passar campos no JSON do body; cada campo será usado como filtro."
                    ),
                ),
                id_cadastro: int = Depends(get_cadastro_jwt),
            ):
                return await _executar_parceiro(nome_int, id_cadastro, payload_params)

            _api_subapp.add_api_route(
                path="/v1/executar/{nome_int}",
                endpoint=partner_handler,
                methods=["POST"],
                tags=["Terceiros Integracoes"],
                name="partner_executar_catch",
            )

        logger.info("Rotas /v1/executar/{nome} registradas (resolução por tenant).")
    except Exception as e:
        logger.error(f"Erro crítico ao registrar rotas dinâmicas: {e}")


# Rotas globais e GUI
app.include_router(config_router)
app.include_router(ui_router)

from src.api.routers import auth as api_auth

app.include_router(api_auth.router)

from src.core.refresher import set_refresher

set_refresher(registrar_endpoints)


@app.on_event("startup")
async def startup_event():
    registrar_endpoints()


@app.get(
    "/",
    response_class=HTMLResponse,
    include_in_schema=False,
    dependencies=[Depends(require_admin_basic)],
)
async def home_bancos(request: Request, usr_cod: Optional[int] = None, erro: Optional[str] = None):
    bancos = []
    for b in list_bancos(apenas_ativos=True):
        item = dict(b)
        item.pop("password", None)
        bancos.append(item)
    return templates.TemplateResponse(
        "home_bancos.html",
        {
            "request": request,
            "bancos": bancos,
            "usr_cod": usr_cod or "",
            "erro": erro,
            "banco": "",
            "bp": "",
            "banco_nome": "",
        },
    )


@app.get("/integracoes", include_in_schema=False)
async def redirect_integracoes_sem_banco():
    return RedirectResponse(url="/?erro=banco_invalido", status_code=302)
