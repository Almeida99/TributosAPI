"""Tela e API de configuração multibanco (protegida por HTTP Basic)."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.core import tenants as tenants_mod
from src.core.admin_auth import require_admin_basic

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=["src/ui/templates", "src/ui"])


router = APIRouter(
    prefix="/config",
    tags=["Configuração"],
    dependencies=[Depends(require_admin_basic)],
)


def _ctx(request: Request, **extra):
    data = {
        "request": request,
        "banco": "",
        "bp": "",
        "banco_nome": "Configuração",
        "usr_cod": request.query_params.get("usr_cod") or "",
    }
    data.update(extra)
    return data


def _bancos_para_ui():
    """Lista bancos sem expor senhas no HTML."""
    out = []
    for b in tenants_mod.list_bancos():
        item = dict(b)
        item["password"] = ""
        out.append(item)
    return out


@router.get("/bancos", response_class=HTMLResponse, include_in_schema=False)
async def config_bancos_list(request: Request, msg: Optional[str] = None, erro: Optional[str] = None):
    return templates.TemplateResponse(
        "config_bancos.html",
        _ctx(request, bancos=_bancos_para_ui(), msg=msg, erro=erro),
    )


@router.get("/bancos/novo", response_class=HTMLResponse, include_in_schema=False)
async def config_bancos_novo(request: Request):
    return templates.TemplateResponse(
        "config_banco_form.html",
        _ctx(request, b={}, is_new=True),
    )


@router.get("/bancos/{slug}/editar", response_class=HTMLResponse, include_in_schema=False)
async def config_bancos_editar(slug: str, request: Request):
    b = tenants_mod.get_banco(slug)
    if not b:
        return RedirectResponse(url="/config/bancos?erro=nao_encontrado", status_code=303)
    b = dict(b)
    b["password"] = ""
    return templates.TemplateResponse(
        "config_banco_form.html",
        _ctx(request, b=b, is_new=False, slug_original=slug),
    )


@router.post("/bancos/salvar", include_in_schema=False)
async def config_bancos_salvar(
    request: Request,
    slug: str = Form(...),
    nome: str = Form(...),
    server: str = Form(...),
    database: str = Form(...),
    username: str = Form(...),
    password: str = Form(""),
    driver: str = Form("ODBC Driver 18 for SQL Server"),
    ativo: int = Form(1),
    slug_original: Optional[str] = Form(None),
):
    try:
        entry, criado = tenants_mod.upsert_banco(
            {
                "slug": slug,
                "nome": nome,
                "server": server,
                "database": database,
                "username": username,
                "password": password if password else None,
                "driver": driver,
                "ativo": bool(ativo),
            },
            slug_original=slug_original or None,
        )
        msg = "salvo"
        if criado:
            try:
                from src.core.schema_init import apply_init_sql_to_banco

                apply_init_sql_to_banco(entry)
                msg = "salvo_schema_ok"
            except Exception as schema_err:
                logger.error("Banco salvo, mas falha ao aplicar schema: %s", schema_err)
                msg = "salvo_schema_erro"
        return RedirectResponse(url=f"/config/bancos?msg={msg}", status_code=303)
    except Exception as e:
        logger.error("Erro ao salvar banco: %s", e)
        return templates.TemplateResponse(
            "config_bancos.html",
            _ctx(request, bancos=_bancos_para_ui(), erro=str(e)),
            status_code=400,
        )


@router.post("/bancos/{slug}/testar", include_in_schema=False)
async def config_bancos_testar(slug: str, request: Request):
    b = tenants_mod.get_banco(slug)
    if not b:
        return RedirectResponse(url="/config/bancos?erro=nao_encontrado", status_code=303)
    try:
        tenants_mod.testar_conexao(b)
        return RedirectResponse(url=f"/config/bancos?msg=ok_conexao_{slug}", status_code=303)
    except Exception as e:
        logger.error("Falha ao testar banco %s: %s", slug, e)
        return RedirectResponse(
            url=f"/config/bancos?erro=Falha+em+{slug}:+{str(e)[:120]}",
            status_code=303,
        )


@router.post("/bancos/testar-form", include_in_schema=False)
async def config_bancos_testar_form(
    server: str = Form(...),
    database: str = Form(...),
    username: str = Form(...),
    password: str = Form(""),
    driver: str = Form("ODBC Driver 18 for SQL Server"),
    slug_original: Optional[str] = Form(None),
):
    """Testa credenciais do formulário (antes de salvar)."""
    pwd = password
    if (not pwd) and slug_original:
        atual = tenants_mod.get_banco(slug_original)
        if atual:
            pwd = atual.get("password") or ""
    try:
        tenants_mod.testar_conexao(
            {
                "server": server,
                "database": database,
                "username": username,
                "password": pwd,
                "driver": driver,
            }
        )
        return {"ok": True, "mensagem": "Conexão bem-sucedida."}
    except Exception as e:
        return {"ok": False, "mensagem": str(e)}


@router.get("/bancos/{slug}/excluir", include_in_schema=False)
async def config_bancos_excluir(slug: str, confirm: int = Query(0)):
    if not confirm:
        return RedirectResponse(url="/config/bancos?erro=confirmacao", status_code=303)
    ok = tenants_mod.delete_banco(slug)
    if ok:
        return RedirectResponse(url="/config/bancos?msg=excluido", status_code=303)
    return RedirectResponse(url="/config/bancos?erro=nao_encontrado", status_code=303)
