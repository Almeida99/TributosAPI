import os
import json
import logging
import time
from typing import Optional, List
from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.core.database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["GUI"])
templates = Jinja2Templates(directory=["src/ui/templates", "src/ui"])


def _tenant_bp(request: Request) -> str:
    banco = getattr(request.state, "banco", None) or ""
    return f"/{banco}" if banco else ""


def ui_url(request: Request, path: str, usr_cod=None) -> str:
    """Monta URL com prefixo /{banco} para redirects do painel."""
    bp = _tenant_bp(request)
    if not path.startswith("/"):
        path = "/" + path
    url = f"{bp}{path}"
    if usr_cod is not None:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}usr_cod={usr_cod}"
    return url


def render(request: Request, name: str, context: dict):
    """TemplateResponse com banco/bp injetados."""
    ctx = dict(context)
    ctx.setdefault("request", request)
    banco = getattr(request.state, "banco", "") or ""
    ctx.setdefault("banco", banco)
    ctx.setdefault("bp", f"/{banco}" if banco else "")
    ctx.setdefault("banco_nome", getattr(request.state, "banco_nome", "") or banco)
    return templates.TemplateResponse(name, ctx)




async def ui_validate_user(usr_cod: Optional[int] = Query(None)) -> int:
    """Valida se o usr_cod existe e está ativo na fr_usuario."""
    if usr_cod is None:
        # Busca o primeiro usuário ativo disponível como padrão
        try:
            res = db.integracao_query("SELECT TOP 1 USR_CODIGO FROM fr_usuario WHERE USR_BLOQUEIO_USUARIO = 'N' ORDER BY USR_CODIGO")
            if res:
                return res[0].get('USR_CODIGO', 1)
        except:
            pass
        return 1 # Fallback caso falhe a busca

    try:
        res = db.integracao_query("SELECT USR_CODIGO FROM fr_usuario WHERE USR_CODIGO = ? AND USR_BLOQUEIO_USUARIO = 'N'", (usr_cod,))
        if not res:
            logger.warning(f"Tentativa de acesso com usr_cod inválido ou bloqueado: {usr_cod}")
            raise HTTPException(status_code=403, detail="Acesso negado: Usuário de integração inválido ou bloqueado.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro na validação do usuário UI: {e}")
        raise HTTPException(status_code=500, detail="Erro interno na validação de usuário.")
    return usr_cod


def normalize_row(row):
    return {str(k).lower(): v for k, v in row.items()} if row else {}


@router.get("/integracoes", response_class=HTMLResponse, include_in_schema=False)
async def ui_integracoes_list(request: Request, usr_cod: int = Depends(ui_validate_user)):
    rows = db.integracao_query("SELECT * FROM TRB_INTEGRACAO ORDER BY NOME")
    integracoes = [normalize_row(r) for r in rows]
    return render(request, "integracoes_list_modern.html", {"usr_cod": usr_cod, "integracoes": integracoes})


@router.get("/integracoes/nova", response_class=HTMLResponse, include_in_schema=False)
async def ui_integracoes_new(request: Request, usr_cod: int = Depends(ui_validate_user)):
    return render(request, "integracoes_form_v3.html", {"usr_cod": usr_cod, "i": {}})


@router.get("/integracoes/{id_int}/editar", response_class=HTMLResponse, include_in_schema=False)
async def ui_integracoes_edit(id_int: int, request: Request, usr_cod: int = Depends(ui_validate_user)):
    res = db.integracao_query("SELECT * FROM TRB_INTEGRACAO WHERE ID_INTEGRACAO = ?", (id_int,))
    if not res:
        return RedirectResponse(url=ui_url(request, "/integracoes", usr_cod))
    
    i = normalize_row(res[0])
    return render(request, "integracoes_form_v3.html", {"usr_cod": usr_cod, "i": i})


@router.get("/integracoes/{id_int}/testar", response_class=HTMLResponse, include_in_schema=False)
async def ui_integracoes_test(id_int: int, request: Request, usr_cod: int = Depends(ui_validate_user)):
    res = db.integracao_query("SELECT * FROM TRB_INTEGRACAO WHERE ID_INTEGRACAO = ?", (id_int,))
    if not res:
        return RedirectResponse(url=ui_url(request, "/integracoes", usr_cod))
    
    i = normalize_row(res[0])
    return render(request, "integracoes_testar_modern.html", {"usr_cod": usr_cod, "i": i})


@router.post("/integracoes/salvar", include_in_schema=False)
async def ui_integracoes_save(
    request: Request,
    usr_cod: int = Depends(ui_validate_user),
    id_integracao: Optional[int] = Form(None),
    nome: str = Form(...),
    nome_integracao: str = Form(""),
    ativo: int = Form(1),
    script_python: str = Form(""),
):
    try:
        logger.info(f"Saving integration: id_integracao={id_integracao}, nome={nome}, nome_integracao={nome_integracao}")
        if id_integracao:
            sql = """
                UPDATE TRB_INTEGRACAO SET 
                NOME=?, NOME_INTEGRACAO=?, ATIVO=?, SCRIPT_PYTHON=?, DATA_ATUALIZACAO=GETDATE()
                WHERE ID_INTEGRACAO=?
            """
            db.integracao_query(sql, (nome, nome_integracao, ativo, script_python, id_integracao))
            logger.info(f"Updated integration ID {id_integracao}")
        else:
            sql = """
                INSERT INTO TRB_INTEGRACAO (NOME, NOME_INTEGRACAO, ATIVO, SCRIPT_PYTHON)
                VALUES (?, ?, ?, ?)
            """
            db.integracao_query(sql, (nome, nome_integracao, ativo, script_python))
            logger.info("Inserted new integration")

        from src.core.refresher import trigger_refresh
        trigger_refresh()
        return RedirectResponse(url=ui_url(request, "/integracoes", usr_cod), status_code=303)
    except Exception as e:
        logger.error(f"Erro ao salvar integração: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/integracoes/{id_int}/excluir", include_in_schema=False)
async def ui_integracoes_delete(id_int: int, request: Request, usr_cod: int = Depends(ui_validate_user)):
    try:
        logger.info(f"Deleting integration ID: {id_int}")
        db.integracao_query("DELETE FROM TRB_INTEGRACAO WHERE ID_INTEGRACAO = ?", (id_int,))
        
        from src.core.refresher import trigger_refresh
        trigger_refresh()
        return RedirectResponse(url=ui_url(request, "/integracoes", usr_cod), status_code=303)
    except Exception as e:
        logger.error(f"Erro ao excluir integração: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gemini", response_class=HTMLResponse, include_in_schema=False)
async def ui_gemini_tokens(request: Request, usr_cod: int = Depends(ui_validate_user)):
    tokens = []
    try:
        rows = db.integracao_query("SELECT * FROM TRB_GEMINI_TOKENS ORDER BY ID_TOKEN DESC")
        tokens = [normalize_row(r) for r in rows]
    except Exception as e:
        logger.warning(f"Tabela TRB_GEMINI_TOKENS não encontrada ou erro na query: {e}")
    
    return render(request, "gemini_tokens.html", {"usr_cod": usr_cod, "tokens": tokens})


@router.get("/gemini/novo", response_class=HTMLResponse, include_in_schema=False)
async def ui_gemini_new(request: Request, usr_cod: int = Depends(ui_validate_user)):
    return render(request, "gemini_token_form.html", {"usr_cod": usr_cod, "t": {}})


@router.get("/gemini/{id_token}/editar", response_class=HTMLResponse, include_in_schema=False)
async def ui_gemini_edit(id_token: int, request: Request, usr_cod: int = Depends(ui_validate_user)):
    try:
        res = db.integracao_query("SELECT * FROM TRB_GEMINI_TOKENS WHERE ID_TOKEN = ?", (id_token,))
        if not res:
            return RedirectResponse(url=ui_url(request, "/gemini", usr_cod))
        t = normalize_row(res[0])
        return render(request, "gemini_token_form.html", {"usr_cod": usr_cod, "t": t})
    except Exception as e:
        logger.error(f"Erro ao editar token Gemini: {e}")
        return RedirectResponse(url=ui_url(request, "/gemini", usr_cod))


@router.post("/gemini/salvar", include_in_schema=False)
async def ui_gemini_save(
    request: Request,
    usr_cod: int = Depends(ui_validate_user),
    id_token: Optional[int] = Form(None),
    api_key: str = Form(...),
    modelo: str = Form("gemini-1.5-flash"),
    ativo: int = Form(1),
):
    try:
        if id_token:
            sql = "UPDATE TRB_GEMINI_TOKENS SET API_KEY=?, MODELO=?, ATIVO=? WHERE ID_TOKEN=?"
            db.integracao_query(sql, (api_key, modelo, ativo, id_token))
        else:
            sql = "INSERT INTO TRB_GEMINI_TOKENS (API_KEY, MODELO, ATIVO) VALUES (?, ?, ?)"
            db.integracao_query(sql, (api_key, modelo, ativo))
        
        return RedirectResponse(url=ui_url(request, "/gemini", usr_cod), status_code=303)
    except Exception as e:
        logger.error(f"Erro ao salvar token Gemini: {e}")
        raise HTTPException(status_code=500, detail="Erro ao salvar dados do Gemini no banco.")


@router.get("/gemini/{id_token}/excluir", include_in_schema=False)
async def ui_gemini_delete(id_token: int, request: Request, usr_cod: int = Depends(ui_validate_user)):
    try:
        db.integracao_query("DELETE FROM TRB_GEMINI_TOKENS WHERE ID_TOKEN = ?", (id_token,))
        return RedirectResponse(url=ui_url(request, "/gemini", usr_cod), status_code=303)
    except Exception as e:
        logger.error(f"Erro ao excluir token Gemini: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/documentacao", response_class=HTMLResponse, include_in_schema=False)
async def ui_documentacao(request: Request, usr_cod: int = Depends(ui_validate_user)):
    return render(request, "documentacao.html", {"usr_cod": usr_cod})


@router.get("/logs", response_class=HTMLResponse, include_in_schema=False)
async def ui_logs(request: Request, usr_cod: int = Depends(ui_validate_user)):
    logs_sistema = []
    logs_api = []
    logs_auditoria = []

    # Helper para montar dict de log de integração
    def _build_log_entry(rn, is_terceiro=False):
        # Usando explicitamente o ID numérico (Prioriza Terceiro se houver)
        id_terceiro = rn.get("id_cadastro_terceiro")
        id_sistema = rn.get("usr_id_sistema")
        
        usr_display = str(id_terceiro) if id_terceiro is not None else (str(id_sistema) if id_sistema is not None else "0")

        msg = str(rn.get("mensagem") or "")
        if len(msg) > 500: msg = msg[:500] + "..."
        resp = str(rn.get("payload_retorno") or "")
        if len(resp) > 500: resp = resp[:500] + "..."
        nome_int = rn.get("nome_integracao_log") or rn.get("nome_integracao") or f"ID: {rn.get('id_integracao')}"
        dh = rn.get("data_hora")
        return {
            "data_hora": dh.strftime("%d/%m/%Y %H:%M:%S") if dh else "—",
            "usr_id_log": usr_display,
            "nome_integracao": nome_int,
            "filtro": str(rn.get("filtro") or ""),
            "status": str(rn.get("status") or ""),
            "mensagem": msg,
            "resposta": resp,
            "duracao_ms": rn.get("duracao_ms", 0),
            "is_terceiro": is_terceiro
        }

    # 1. Logs de sistema (Execuções Manuais - sem terceiro vinculado)
    try:
        sql_sistema = """
            SELECT TOP 100 
                L.ID_LOG, L.ID_INTEGRACAO, L.USR_COD as USR_ID_SISTEMA, L.ID_CADASTRO_TERCEIRO, L.FILTRO,
                SUBSTRING(CAST(L.PAYLOAD_ENVIO AS NVARCHAR(MAX)), 1, 1000) as PAYLOAD_ENVIO,
                SUBSTRING(CAST(L.PAYLOAD_RETORNO AS NVARCHAR(MAX)), 1, 1000) as PAYLOAD_RETORNO,
                L.STATUS, 
                SUBSTRING(CAST(L.MENSAGEM AS NVARCHAR(MAX)), 1, 1000) as MENSAGEM,
                L.DATA_HORA, L.DURACAO_MS,
                L.NOME_INTEGRACAO as NOME_INTEGRACAO_LOG,
                I.NOME as NOME_INTEGRACAO
            FROM TRB_LOG_INTEGRACAO L
            LEFT JOIN TRB_INTEGRACAO I ON L.ID_INTEGRACAO = I.ID_INTEGRACAO
            ORDER BY L.DATA_HORA DESC
        """
        rows = db.integracao_query(sql_sistema)
        for r in (rows or []):
            rn = {str(k).lower(): v for k, v in r.items()}
            logs_sistema.append(_build_log_entry(rn, is_terceiro=False))
    except Exception as e:
        logger.error(f"Erro ao buscar logs de sistema: {e}")



    # 3. Auditoria de Acessos JWT
    try:
        sql_aud = """
            SELECT TOP 100 
                A.id_auditoria, A.id_cadastro as ID_CAD, A.tipo_evento, A.metodo_http,
                A.rota, A.status_http, A.duracao_ms, A.endereco_ip,
                A.user_agent, A.login_tentativa, A.sucesso, A.detalhe_erro,
                A.data_evento, A.json_requisicao, A.json_retorno
            FROM TRB_INTEGRACAO_TERCEIROS_AUDITORIA A
            ORDER BY A.data_evento DESC
        """
        rows_aud = db.integracao_query(sql_aud)
        for r in (rows_aud or []):
            rn = {str(k).lower(): v for k, v in r.items()}
            dh = rn.get("data_evento")
            id_cad = rn.get("id_cad")
            login_disp = str(id_cad) if id_cad is not None else (rn.get("login_tentativa") or "0")

            logs_auditoria.append({
                "data_hora": dh.strftime("%d/%m/%Y %H:%M:%S") if dh else "—",
                "login": login_disp,
                "tipo_evento": rn.get("tipo_evento", ""),
                "metodo_http": rn.get("metodo_http", ""),
                "rota": rn.get("rota", ""),
                "status_http": rn.get("status_http", ""),
                "sucesso": bool(rn.get("sucesso")),
                "endereco_ip": rn.get("endereco_ip", ""),
                "detalhe_erro": str(rn.get("detalhe_erro") or ""),
                "duracao_ms": rn.get("duracao_ms", 0),
                "json_requisicao": rn.get("json_requisicao"),
                "json_retorno": rn.get("json_retorno")
            })
    except Exception as e:
        logger.error(f"Erro ao buscar auditoria JWT: {e}")

    return render(request, "logs.html", {
        "usr_cod": usr_cod,
        "logs_sistema": logs_sistema,
        "logs_auditoria": logs_auditoria
    })


# --- GESTÃO DE TERCEIROS ---

@router.get("/terceiros", response_class=HTMLResponse, include_in_schema=False)
async def ui_terceiros_list(request: Request, usr_cod: int = Depends(ui_validate_user)):
    rows = db.integracao_query("SELECT * FROM TRB_INTEGRACAO_TERCEIROS_CADASTRO ORDER BY login")
    terceiros = [normalize_row(r) for r in rows]
    return render(request, "terceiros_list.html", {"usr_cod": usr_cod, "terceiros": terceiros})


@router.get("/terceiros/novo", response_class=HTMLResponse, include_in_schema=False)
async def ui_terceiros_new(request: Request, usr_cod: int = Depends(ui_validate_user)):
    return render(request, "terceiros_form.html", {"usr_cod": usr_cod, "t": {}})


@router.get("/terceiros/{id_t}/editar", response_class=HTMLResponse, include_in_schema=False)
async def ui_terceiros_edit(id_t: int, request: Request, usr_cod: int = Depends(ui_validate_user)):
    res = db.integracao_query("SELECT * FROM TRB_INTEGRACAO_TERCEIROS_CADASTRO WHERE id_cadastro = ?", (id_t,))
    if not res:
        return RedirectResponse(url=ui_url(request, "/terceiros", usr_cod))
    t = normalize_row(res[0])
    return render(request, "terceiros_form.html", {"usr_cod": usr_cod, "t": t})


@router.post("/terceiros/salvar", include_in_schema=False)
async def ui_terceiros_save(
    request: Request,
    usr_cod: int = Depends(ui_validate_user),
    id_cadastro: Optional[int] = Form(None),
    login: str = Form(...),
    senha: Optional[str] = Form(None),
    ativo: int = Form(1),
):
    try:
        from src.api.security import hash_senha
        if id_cadastro:
            if senha:
                sql = "UPDATE TRB_INTEGRACAO_TERCEIROS_CADASTRO SET login=?, senha_hash=?, ativo=? WHERE id_cadastro=?"
                db.integracao_query(sql, (login, hash_senha(senha), ativo, id_cadastro))
            else:
                sql = "UPDATE TRB_INTEGRACAO_TERCEIROS_CADASTRO SET login=?, ativo=? WHERE id_cadastro=?"
                db.integracao_query(sql, (login, ativo, id_cadastro))
        else:
            if not senha:
                raise HTTPException(status_code=400, detail="Senha obrigatória para novo cadastro.")
            sql = "INSERT INTO TRB_INTEGRACAO_TERCEIROS_CADASTRO (login, senha_hash, ativo) VALUES (?, ?, ?)"
            db.integracao_query(sql, (login, hash_senha(senha), ativo))
        
        return RedirectResponse(url=ui_url(request, "/terceiros", usr_cod), status_code=303)
    except Exception as e:
        logger.error(f"Erro ao salvar terceiro: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/terceiros/{id_t}/excluir", include_in_schema=False)
async def ui_terceiros_delete(id_t: int, request: Request, usr_cod: int = Depends(ui_validate_user)):
    try:
        # Remove endpoints primeiro por causa da FK (se houver, mas aqui não tem FK explícita no SQL, mas é bom limpar)
        db.integracao_query("DELETE FROM TRB_INTEGRACAO_TERCEIROS_ENDPOINT WHERE id_cadastro = ?", (id_t,))
        db.integracao_query("DELETE FROM TRB_INTEGRACAO_TERCEIROS_CADASTRO WHERE id_cadastro = ?", (id_t,))
        
        from src.core.refresher import trigger_refresh
        trigger_refresh()
        
        return RedirectResponse(url=ui_url(request, "/terceiros", usr_cod), status_code=303)
    except Exception as e:
        logger.error(f"Erro ao excluir terceiro: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/terceiros/{id_t}/endpoints", response_class=HTMLResponse, include_in_schema=False)
async def ui_terceiros_endpoints(id_t: int, request: Request, usr_cod: int = Depends(ui_validate_user)):
    # Cadastro do terceiro
    res_t = db.integracao_query("SELECT * FROM TRB_INTEGRACAO_TERCEIROS_CADASTRO WHERE id_cadastro = ?", (id_t,))
    if not res_t:
        return RedirectResponse(url=ui_url(request, "/terceiros", usr_cod))
    terceiro = normalize_row(res_t[0])

    # Endpoints já permitidos
    rows_p = db.integracao_query("SELECT * FROM TRB_INTEGRACAO_TERCEIROS_ENDPOINT WHERE id_cadastro = ?", (id_t,))
    permitidos = [normalize_row(r) for r in rows_p]

    # Todas as integrações disponíveis para adicionar
    rows_all = db.integracao_query("SELECT NOME_INTEGRACAO, NOME FROM TRB_INTEGRACAO WHERE ATIVO = 1 ORDER BY NOME")
    integracoes = [normalize_row(r) for r in rows_all]

    return render(request, "terceiros_endpoints.html", {
        "usr_cod": usr_cod, 
        "terceiro": terceiro,
        "permitidos": permitidos,
        "integracoes": integracoes
    })


@router.post("/terceiros/{id_t}/endpoints/adicionar", include_in_schema=False)
async def ui_terceiros_endpoint_add(
    id_t: int,
    request: Request,
    nome_integracao: str = Form(...),
    usr_cod: int = Depends(ui_validate_user)
):
    try:
        db.integracao_query(
            "INSERT INTO TRB_INTEGRACAO_TERCEIROS_ENDPOINT (id_cadastro, nome_integracao, ativo) VALUES (?, ?, 1)",
            (id_t, nome_integracao)
        )
        # Refresh das rotas dinâmicas
        from src.core.refresher import trigger_refresh
        trigger_refresh()
        
        return RedirectResponse(url=ui_url(request, f"/terceiros/{id_t}/endpoints", usr_cod), status_code=303)
    except Exception as e:
        logger.error(f"Erro ao adicionar endpoint: {e}")
        return RedirectResponse(url=ui_url(request, f"/terceiros/{id_t}/endpoints", usr_cod), status_code=303)


@router.get("/terceiros/{id_t}/endpoints/{id_ep}/excluir", include_in_schema=False)
async def ui_terceiros_endpoint_del(id_t: int, id_ep: int, request: Request, usr_cod: int = Depends(ui_validate_user)):
    try:
        db.integracao_query("DELETE FROM TRB_INTEGRACAO_TERCEIROS_ENDPOINT WHERE id_endpoint = ?", (id_ep,))
        # Refresh das rotas dinâmicas
        from src.core.refresher import trigger_refresh
        trigger_refresh()
        
        return RedirectResponse(url=ui_url(request, f"/terceiros/{id_t}/endpoints", usr_cod), status_code=303)
    except Exception as e:
        logger.error(f"Erro ao excluir endpoint: {e}")
        return RedirectResponse(url=ui_url(request, f"/terceiros/{id_t}/endpoints", usr_cod), status_code=303)



@router.get("/install", response_class=HTMLResponse, include_in_schema=False)
async def ui_install(request: Request, usr_cod: int = Depends(ui_validate_user)):
    return render(request, "install.html", {"usr_cod": usr_cod})


@router.post("/install/executar", include_in_schema=False)
async def ui_install_execute(request: Request, usr_cod: int = Depends(ui_validate_user)):
    return {"status": "ok", "message": "Nenhuma alteração pendente no schema."}


@router.get("/install/schema", response_class=HTMLResponse, include_in_schema=False)
async def ui_install_schema(request: Request, usr_cod: int = Depends(ui_validate_user)):
    return render(request, "install.html", {"usr_cod": usr_cod})


@router.post("/v1/gemini/ajustar", include_in_schema=False)
async def api_gemini_ajustar(request: Request, usr_cod: int = Depends(ui_validate_user)):
    return {"status": "ok"}


@router.post("/v1/script/padrao", include_in_schema=False)
async def api_script_padrao(request: Request):
    try:
        data = await request.json()
        tipo = data.get("tipo", "xml")
        
        if tipo == "xml":
            script = """import time
import re

filtro = params.get('filtro')
if not filtro:
    raise Exception('Parâmetro filtro obrigatório')

select_sql = f' select coluna as  payload_xml  from tabela WHERE campo  = {filtro}'

url_login = params.get('url_login', '')
url_api = params.get('url_api', '')
usuario_api = params.get('usuario_api', '')
senha_api = params.get('senha_api', '')

# 1. Login
token = ''
xml_login = f'<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body><Autenticar xmlns="https://wspub.cenprotnacional.org.br/ieptb-cenprot-empresas-arquivos-hml/services"><credenciais xmlns=""><usuario>{usuario_api}</usuario><senha>{senha_api}</senha></credenciais></Autenticar></Body></Envelope>'
resp_login = http_post(url_login, xml_login, {'Content-Type': 'text/xml', 'SOAPAction': '"Autenticar"'})
token_match = re.search(r'<token>(.*?)</token>', resp_login.get('text', ''))
if token_match:
    token = token_match.group(1)

# 2. Envio
rows = executar_consulta(select_sql)
if not rows:
    resultado = "Erro: Nenhum registro encontrado para o filtro."
else:
    xml_envio = rows[0].get('payload_xml', '')
    if token:
        xml_envio = xml_envio.replace("{token}", token)
    
    # Correção de encoding e caracteres especiais
    xml_envio = xml_envio.replace('º', 'o.').replace('ª', 'a.')
    
    action = "EnviarTitulo"
    if "ConsultarTitulo" in xml_envio: action = "ConsultarTitulo"
    
    resp_envio = http_post(url_api, xml_envio, {'Content-Type': 'text/xml', 'SOAPAction': f'"{action}"'})
    
    # Define o resultado como o texto bruto da resposta do endpoint
    resultado = resp_envio.get('text', '')
"""
        elif tipo == "json":
            script = """import time
import json

filtro = params.get('filtro')
if not filtro:
    raise Exception('Parâmetro filtro obrigatório')

select_sql = f"SELECT TOP 1 id, payload_json FROM sua_tabela WHERE filtro = {filtro}"

url_login = params.get('url_login', '')
url_api = params.get('url_api', '')
usuario_api = params.get('usuario_api', '')
senha_api = params.get('senha_api', '')

headers = {'Content-Type': 'application/json'}

# 1. Login
if url_login and usuario_api and senha_api:
    login_data = json.dumps({"usuario": usuario_api, "senha": senha_api})
    resp_login = http_post(url_login, data=login_data, headers=headers)
    if resp_login.get('status') in [200, 201]:
        token = json.loads(resp_login.get('text', '{}')).get('token')
        if token:
            headers['Authorization'] = f'Bearer {token}'

# 2. Envio
rows = executar_consulta(select_sql)
if not rows:
    resultado = "Erro: Nenhum registro encontrado para o filtro."
else:
    payload = rows[0].get('payload_json', '{}')
    resp_envio = http_post(url_api, data=payload, headers=headers)
    
    # Define o resultado como o texto bruto da resposta do endpoint
    resultado = resp_envio.get('text', '')
"""
        elif tipo == "terceiro":
            script = """import re

# 1. Configurações (50 por página)
TAMANHO = 50
pagina = int(params.get('pagina', 1)) if str(params.get('pagina', 1)).isdigit() else 1
if pagina < 1:
    pagina = 1

# 2. Filtros Automáticos com proteção contra SQL Injection
# - Nomes de campo: aceita apenas letras, números, underscore e ponto (ex: B.IMV_COD)
# - Valores: sempre via bind parameter (?)
where = "1=1"
filtros = []
for campo, valor in params.items():
    if campo == 'pagina':
        continue
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_.]*$', campo):
        raise Exception(f"Campo '{campo}' contém caracteres inválidos.")
    where += f" AND {campo} = ?"
    filtros.append(valor)

# 3. Execução da Consulta (SQL Server)
sql = f\"\"\"
    SELECT * FROM SuaTabela 
    WHERE {where} 
    ORDER BY ID 
    OFFSET {(pagina-1)*TAMANHO} ROWS FETCH NEXT {TAMANHO} ROWS ONLY
\"\"\"
dados = executar_consulta(sql, filtros)

# 4. Total de Registros
total_sql = f"SELECT COUNT(*) as total FROM SuaTabela WHERE {where}"
total = executar_consulta(total_sql, filtros)[0]['total']

# 5. Retorno
resultado = {
    "pagina_atual": pagina,
    "total_registros": total,
    "total_paginas": (total + TAMANHO - 1) // TAMANHO,
    "dados": dados
}
"""
        else:
            script = "# Script padrão não habilitado para este tipo"
            
        return {"script": script}
    except Exception as e:
        return {"error": str(e)}
