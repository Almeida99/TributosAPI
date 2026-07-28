import httpx
import logging
import json
import time
from ..core.config import get_conexao

logger = logging.getLogger(__name__)


class EnvioService:
    """Serviço para enviar requisições HTTP"""

    async def enviar(self, integracao: dict, payload: str, auth_info: dict) -> tuple:
        """
        Envia payload para URL configurada
        Retorna: (status_code, resposta_text, duracao_ms)
        """
        url = integracao.get("url_envio")
        if not url:
            return 400, "URL de envio não configurada", 0

        metodo = integracao.get("metodo_http", "POST").upper()
        content_type = integracao.get("content_type", "application/json")
        timeout = integracao.get("timeout_segundos", 60)

        # Preparar headers
        headers = {"Content-Type": content_type}
        headers.update(auth_info.get("headers", {}))

        # Headers extras do .env
        extras = integracao.get("headers_extras")
        if extras:
            try:
                extras_dict = json.loads(extras) if isinstance(extras, str) else extras
                headers.update(extras_dict)
            except:
                pass

        # Adicionar SOAPAction se presente
        if integracao.get("soap_action"):
            headers["SOAPAction"] = integracao.get("soap_action")

        # Preparar cookies
        cookies = auth_info.get("cookies", {})

        # Log do que será enviado
        logger.info(f"Enviando {metodo} {url}")
        payload_str = str(payload or "")
        logger.debug(f"Payload: {payload_str[:200]}..." if len(payload_str) > 200 else f"Payload: {payload_str}")

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                start_time = time.time()

                if metodo == "GET":
                    resp = await client.get(url, headers=headers, cookies=cookies)
                elif metodo == "POST":
                    resp = await client.post(
                        url,
                        content=payload.encode('utf-8'),
                        headers=headers,
                        cookies=cookies
                    )
                elif metodo == "PUT":
                    resp = await client.put(
                        url,
                        content=payload.encode('utf-8'),
                        headers=headers,
                        cookies=cookies
                    )
                elif metodo == "PATCH":
                    resp = await client.patch(
                        url,
                        content=payload.encode('utf-8'),
                        headers=headers,
                        cookies=cookies
                    )
                elif metodo == "DELETE":
                    resp = await client.delete(url, headers=headers, cookies=cookies)
                else:
                    return 405, f"Método {metodo} não suportado", 0

                # Calcular duração
                duracao_ms = int((time.time() - start_time) * 1000)

                # Log da resposta
                logger.info(f"Resposta: {resp.status_code} ({duracao_ms}ms)")
                logger.debug(f"Resposta body: {resp.text[:200]}..." if len(resp.text) > 200 else f"Resposta body: {resp.text}")

                return resp.status_code, resp.text, duracao_ms

        except httpx.TimeoutException:
            logger.error(f"Timeout ao enviar para {url}")
            return 408, "Timeout na requisição", 0
        except Exception as e:
            logger.error(f"Erro ao enviar requisição: {e}")
            return 500, str(e), 0


envio_service = EnvioService()