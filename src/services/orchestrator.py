import json
import logging
import asyncio
from datetime import datetime, date
from decimal import Decimal
from ..core.database import db
from .python_integration_service import python_integration_service
from .envio_service import envio_service

logger = logging.getLogger(__name__)

def json_serializable(obj):
    """JSON serializer for objects not serializable by default json code"""
    return str(obj)

class IntegrationOrchestrator:
    """
    Motor de execução V3: Simplificado, robusto e focado em performance.
    """
    
    @staticmethod
    async def run(nome_integracao: str, usr_cod: int, input_params: dict, dry_run: bool = False, id_cadastro_terceiro: int = None):
        start_time = datetime.now()
        
        # Estrutura do log
        log_entry = {
            "id_integracao": None,
            "sucesso": 0,
            "status_code": None,
            "request_data": "",
            "response_data": "",
            "erro_desc": "",
            "tempo_ms": 0,
            "id_cadastro_terceiro": id_cadastro_terceiro
        }
        
        try:
            # 1. Buscar detalhes da integração (Schema V3 - apenas TRB_INTEGRACAO)
            # Tenta primeiro V3 puro (sem JOIN com TRB_CONEXAO)
            try:
                sql = """
                    SELECT ID_INTEGRACAO, NOME, NOME_INTEGRACAO, ATIVO, SCRIPT_PYTHON
                    FROM TRB_INTEGRACAO 
                    WHERE NOME_INTEGRACAO = ? AND ATIVO = 1
                """
                rows = db.integracao_query(sql, (nome_integracao,))
            except:
                # Fallback V1/V2 (com JOIN)
                sql = """
                    SELECT i.*, c.servidor, c.banco, c.usuario, c.senha, c.driver
                    FROM TRB_INTEGRACAO i
                    LEFT JOIN TRB_CONEXAO c ON i.ID_CONEXAO = c.ID_CONEXAO
                    WHERE i.NOME = ? AND i.ATIVO = 1
                """
                rows = db.integracao_query(sql, (nome_integracao,))

            if not rows:
                raise Exception(f"Integração '{nome_integracao}' não encontrada ou está inativa.")
            
            # Normalizar para facilitar acesso
            i = {str(k).lower(): v for k, v in rows[0].items()}
            log_entry["id_integracao"] = i.get('id_integracao')
            
            # 2. Configuração da Conexão de Origem (com valores padrão para V3)
            target_db = {
                "servidor": i.get("servidor") or "",
                "banco": i.get("banco") or "",
                "usuario": i.get("usuario") or "",
                "senha": i.get("senha") or "",
                "driver": i.get("driver") or ""
            }

            # 3. Execução do SQL de Origem (se houver) - V1/V2 only
            dados_sql = []
            consulta_sql = i.get("consulta_sql")
            if consulta_sql:
                # Substituir parâmetros no SQL
                sql_exec = consulta_sql
                for k, v in input_params.items():
                    if sql_exec:
                        sql_exec = sql_exec.replace("{" + k + "}", str(v))
                
                logger.info(f"[Orchestrator] Executando SQL para {nome_integracao}")
                dados_sql = db.origem_sp(target_db, sql_exec, [])

            # 4. Montagem do Payload
            payload_gerado = i.get("payload_layout") or ""
            if dados_sql and payload_gerado:
                # Injetar dados do primeiro registro retornado
                row_data = dados_sql[0]
                for k, v in row_data.items():
                    payload_gerado = payload_gerado.replace("{" + str(k) + "}", str(v) if v is not None else "")
            
            log_entry["request_data"] = payload_gerado

            # 5. Execução do Fluxo (Login + Envio)
            token = None
            status_http = 200
            resposta_text = ""

            # DETECTAR TIPO DE SCHEMA
            script_v3 = i.get("script_python")  # Schema V3 usa SCRIPT_PYTHON
            
            if script_v3:
                # Schema V3: Executar script Python diretamente
                logger.info(f"[Orchestrator] Executando Script V3 para {nome_integracao}...")
                res_envio = await python_integration_service._executar_codigo(
                    script_v3,
                    target_db,
                    "envio",
                    payload=payload_gerado,
                    token=token,
                    input_params=input_params
                )
                # Guardar XML de envio completo para log
                res_envio_parsed = res_envio
                if isinstance(res_envio, str):
                    # Se o script retornar uma string pura, assumimos que é a resposta bruta desejada
                    resposta_text = res_envio
                
                elif isinstance(res_envio, dict):
                    dados_envio = res_envio.get("dados", [])
                    raw_responses = res_envio.get("raw_response", [])
                    
                    # payload = TODOS xml_envio concatenados
                    if dados_envio:
                        xmls = [d.get("xml_envio", "") for d in dados_envio if d.get("xml_envio")]
                        payload_gerado = "|||".join(xmls) if xmls else ""
                        log_entry["request_data"] = payload_gerado
                    
                    # resposta = TODAS raw_responses concatenadas
                    if raw_responses:
                        resposta_text = "|||".join(raw_responses)
                    else:
                        resposta_text = res_envio
                else:
                    status_http = 200
                    resposta_text = res_envio
            else:
                # Schema V1/V2: Usar campos antigos
                # 5.1 Script de Login Python
                if i.get("script_login_py"):
                    logger.info(f"[Orchestrator] Executando Login Python...")
                    res_login = await python_integration_service.executar_login(
                        {"login_python": i.get("script_login_py")}, target_db
                    )
                    token = res_login.get("token")
                    if token:
                        payload_gerado = payload_gerado.replace("{token}", token)
                        log_entry["request_data"] = payload_gerado

                # 5.2 Script de Envio Python OU REST Padrão
                script_envio = i.get("script_envio_py") or i.get("snippet_python")
                
                if script_envio:
                    logger.info(f"[Orchestrator] Executando Envio Customizado (Python)...")
                    res_envio = await python_integration_service.executar_envio(
                        {"envio_python": script_envio},
                        target_db,
                        payload_gerado,
                        {"token": token, "params": input_params}
                    )
                    status_http = res_envio.get("status", 500)
                    resposta_text = res_envio.get("response", "")
                else:
                    if not i.get("url_endpoint"):
                       resposta_text = "Integração local executada com sucesso."
                    else:
                        if dry_run:
                            resposta_text = "[DRY RUN] Simulação de envio ok."
                        else:
                            integracao_info = {
                                "url_envio": i.get("url_endpoint"),
                                "metodo_http": i.get("metodo_http"),
                                "content_type": i.get("content_type"),
                                "timeout_segundos": 60
                            }
                            status_http, resposta_text, _ = await envio_service.enviar(integracao_info, payload_gerado, {"token": token})

            # Finalizar log entry
            log_entry["status_code"] = status_http
            # response_data = resposta completa do endpoint em formato legível
            if isinstance(resposta_text, dict):
                log_entry["response_data"] = json.dumps(resposta_text, default=json_serializable)
            else:
                log_entry["response_data"] = str(resposta_text)[:5000]
            log_entry["sucesso"] = 1 if 200 <= int(status_http) < 300 else 0
            
            # 6. Script Pós-Execução
            if i.get("script_pos_py") and log_entry["sucesso"] == 1:
                await python_integration_service._executar_codigo(
                    i.get("script_pos_py"), target_db, "post-exec", 
                    payload=payload_gerado, token=token, input_params=input_params
                )

            # Se for Script V3 e retornou uma string, devolvemos a string pura para a API
            if script_v3 and isinstance(res_envio, str):
                return res_envio

            return {
                "sucesso": log_entry["sucesso"] == 1,
                "status_code": status_http,
                "resposta": resposta_text
            }

        except Exception as e:
            msg = str(e)
            logger.error(f"[Orchestrator Error] {msg}")
            log_entry["sucesso"] = 0
            log_entry["erro_desc"] = msg
            return {"sucesso": False, "erro": msg}
            
        finally:
            # 7. Gravar Log em TRB_LOG_INTEGRACAO
            try:
                duracao = int((datetime.now() - start_time).total_seconds() * 1000)
                # Filtro: salvar como JSON string se for dict
                filtro_str = json.dumps(input_params, default=str) if isinstance(input_params, dict) else str(input_params)
                
                db.integracao_query("""
                    INSERT INTO TRB_LOG_INTEGRACAO 
                    (ID_INTEGRACAO, NOME_INTEGRACAO, USR_COD, FILTRO, PAYLOAD_ENVIO, PAYLOAD_RETORNO, STATUS, MENSAGEM, DURACAO_MS, ID_CADASTRO_TERCEIRO)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_entry["id_integracao"], nome_integracao, usr_cod, filtro_str,
                    log_entry["request_data"], log_entry["response_data"], 
                    str(log_entry["status_code"]), log_entry["erro_desc"],
                    duracao, log_entry["id_cadastro_terceiro"]
                ))
            except Exception as le:
                logger.error(f"Erro ao gravar log de integração: {le}")

orchestrator = IntegrationOrchestrator()
