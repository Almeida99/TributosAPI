import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.deps import get_settings
from src.api.middleware_audit import AuditoriaRequisicaoMiddleware
from src.api.routers import admin, auth, executar
from src.api.validators import is_fr_usuario_ativo

logger = logging.getLogger(__name__)


def _validar_inicio() -> None:
    """Valida o usuário técnico no primeiro banco ativo (ou .env)."""
    from src.core.database import clear_current_tenant, db, set_current_tenant
    from src.core.tenants import list_bancos

    s = get_settings()
    bancos = list_bancos(apenas_ativos=True)
    if bancos:
        set_current_tenant(bancos[0])

    usr_valido = False
    try:
        if s.orchestrator_usr_cod > 0:
            usr_valido = is_fr_usuario_ativo(s.orchestrator_usr_cod)

        if not usr_valido:
            logger.warning(
                "API_ORCHESTRATOR_USR_COD (%s) inválido ou inativo. Buscando fallback...",
                s.orchestrator_usr_cod,
            )
            try:
                res = db.integracao_query(
                    "SELECT TOP 1 USR_CODIGO FROM fr_usuario WHERE USR_BLOQUEIO_USUARIO = 'N' ORDER BY USR_CODIGO"
                )
                if res:
                    s.orchestrator_usr_cod = int(res[0]["USR_CODIGO"])
                    usr_valido = True
                    logger.info("Usuário técnico de fallback definido: ORC=%s", s.orchestrator_usr_cod)
            except Exception as e:
                logger.error("Falha ao buscar usuário de fallback: %s", e)

        if not usr_valido:
            logger.error(
                "Nenhum usuário ativo encontrado em fr_usuario. O módulo API externa pode falhar ao executar integrações."
            )
        else:
            logger.info("Módulo API externa: usuário técnico ORC=%s", s.orchestrator_usr_cod)
    finally:
        clear_current_tenant()


def build_api_app() -> FastAPI:
    _validar_inicio()
    app = FastAPI(
        title="TributosAPI — Integração terceiros",
        description="Autenticação por login/senha, token JWT (1h).",
        version="1.0.0",
        docs_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuditoriaRequisicaoMiddleware)
    app.include_router(auth.router)
    app.include_router(admin.router, include_in_schema=False)
    # As rotas de execução são injetadas dinamicamente pelo main.py

    @app.get("/v1/health", include_in_schema=False)
    def health_terceiros():
        return {"status": "ok", "modulo": "integracao_terceiros"}

    # --- DOCUMENTAÇÃO PROTEGIDA ---
    from fastapi.security import HTTPBasic, HTTPBasicCredentials
    from fastapi import Depends, HTTPException, status
    from fastapi.openapi.utils import get_openapi
    from fastapi.openapi.docs import get_swagger_ui_html
    from src.api.security import verificar_senha
    from src.core.database import db

    security = HTTPBasic()

    def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
        res = db.integracao_query("SELECT id_cadastro, login, senha_hash FROM TRB_INTEGRACAO_TERCEIROS_CADASTRO WHERE login = ? AND ativo = 1", (credentials.username,))
        if not res:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login ou senha inválidos",
                headers={"WWW-Authenticate": "Basic"},
            )
        user = res[0]
        if not verificar_senha(credentials.password, user['senha_hash']):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login ou senha inválidos",
                headers={"WWW-Authenticate": "Basic"},
            )
        return user

    @app.get("/openapi.json", include_in_schema=False)
    async def get_protected_openapi(user: dict = Depends(get_current_user)):
        # Busca os endpoints permitidos para este usuário (tenant atual via path)
        rows = db.integracao_query(
            "SELECT nome_integracao FROM TRB_INTEGRACAO_TERCEIROS_ENDPOINT WHERE id_cadastro = ? AND ativo = 1",
            (user["id_cadastro"],),
        )
        permitidos = sorted({r["nome_integracao"] for r in rows if r.get("nome_integracao")})

        full_openapi = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

        # Lista integrações ativas do tenant + as permitidas ao usuário (união)
        from src.core.replication import listar_nomes_integracoes_ativas
        from src.core.openapi_expand import expand_executar_paths

        ativas = set(listar_nomes_integracoes_ativas())
        nomes = sorted(ativas | set(permitidos))
        # Se o usuário tem permissões, prioriza só as permitidas no docs (mais seguro).
        # Se ainda não tiver nenhuma permissão, mostra as ativas para descoberta.
        if permitidos:
            nomes = sorted(set(permitidos) & ativas) or sorted(permitidos)

        return expand_executar_paths(
            full_openapi,
            "/v1/executar/{nome_int}",
            nomes,
            keep_paths=["/v1/auth/token"],
        )
    @app.get("/docs", include_in_schema=False)
    async def get_protected_docs(user: dict = Depends(get_current_user)):
        return get_swagger_ui_html(
            openapi_url="./openapi.json",
            title=app.title + " - Docs",
            swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
            swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        )

    return app
