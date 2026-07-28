import httpx
import json
import logging
from .gemini_engine import gemini_rotator

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


class GeminiService:
    """Serviço Gemini para análise de exemplos e sugestões"""
    
    async def generate(self, prompt: str, system: str = "") -> dict:
        """Gera conteúdo usando o Gemini"""
        try:
            token_data = gemini_rotator.get_next()
            if not token_data:
                return {"sucesso": False, "erro": "Nenhum token Gemini disponível"}
            
            api_key = token_data["api_key"]
            modelo = token_data.get("modelo", "gemini-2.0-flash")
            
            # Normalizar nome do modelo
            modelo = token_data.get("modelo", "gemini-2.0-flash")
            modelo = modelo.replace("-latest", "").replace("_latest", "").replace("latest", "").strip()
            if not modelo:
                modelo = "gemini-2.0-flash"
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
            
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 8000}
            }
            
            if system:
                payload["systemInstruction"] = {"parts": [{"text": system}]}
            
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, json=payload)
                
                if resp.status_code == 200:
                    data = resp.json()
                    texto = ""
                    if data.get("candidates"):
                        candidate = data["candidates"][0]
                        if candidate.get("content", {}).get("parts"):
                            texto = candidate["content"]["parts"][0].get("text", "")
                    
                    # Limpar markers de código ```python ou ```
                    texto = texto.strip()
                    if texto.startswith("```"):
                        lines = texto.split("\n")
                        # Remover primeira linha se for ```python ou ```
                        if lines[0].strip().startswith("```"):
                            lines = lines[1:]
                        # Remover última linha se for ```
                        if lines and lines[-1].strip() == "```":
                            lines = lines[:-1]
                        texto = "\n".join(lines)
                    
                    return {"sucesso": True, "texto": texto}
                else:
                    return {"sucesso": False, "erro": f"Erro API: {resp.status_code}"}
                    
        except Exception as e:
            return {"sucesso": False, "erro": str(e)}
    
    async def analisar_exemplo(self, exemplo: str, contexto: str = "") -> dict:
        """Analisa exemplo JSON/XML e sugere formato de template"""
        token_data = gemini_rotator.get_next()
        if not token_data:
            return {"erro": "Nenhum token disponível"}
        
        token = token_data["api_key"]
        
        prompt = f"""Analise o exemplo e sugira um template JSON ou XML.

EXEMPLO: {exemplo}
CONTEXTO: {contexto}

RESPONDA APENAS COM JSON: {{"formato": "json|xml", "template": "...", "descricao": "..."}}"""

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{GEMINI_URL}?key={token}",
                    json={"contents": [{"parts": [{"text": prompt}]}]}
                )
                
                if resp.status_code != 200:
                    return {"erro": f"Erro API: {resp.status_code}"}
                
                data = resp.json()
                text = ""
                if data.get("candidates"):
                    parts = data["candidates"][0].get("content", {}).get("parts", [{}])
                    if parts:
                        text = parts[0].get("text", "{}")
                
                # Limpar marcadores
                text = text.strip()
                if text.startswith("```json"):
                    text = text[7:-3].strip()
                elif text.startswith("```"):
                    text = text[3:-3].strip()
                
                return json.loads(text)
                
        except Exception as e:
            return {"erro": str(e)}
    
    async def sugerir_nome(self, contexto: str, url: str = "", tipo_dado: str = "") -> dict:
        """Sugere nome para integração"""
        token_data = gemini_rotator.get_next()
        if not token_data:
            return {"nome": "Integracao_Automatica"}
        
        token = token_data["api_key"]
        
        prompt = f"""Sugira nome curto (max 50 caracteres) para: URL={url} TIPO={tipo_dado} CONTEXTO={contexto}
RESPONDA APENAS COM JSON: {{"nome": "nome_aqui"}}"""

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{GEMINI_URL}?key={token}",
                    json={"contents": [{"parts": [{"text": prompt}]}]}
                )
                
                if resp.status_code != 200:
                    return {"nome": "Integracao_Automatica"}
                
                data = resp.json()
                text = ""
                if data.get("candidates"):
                    parts = data["candidates"][0].get("content", {}).get("parts", [{}])
                    if parts:
                        text = parts[0].get("text", "{}")
                
                text = text.strip()
                if text.startswith("```json"):
                    text = text[7:-3].strip()
                elif text.startswith("```"):
                    text = text[3:-3].strip()
                
                result = json.loads(text)
                nome = result.get("nome", "Integracao_Automatica")
                nome = "".join(c if c.isalnum() or c == "_" else "_" for c in nome)[:50]
                return {"nome": nome}
                
        except Exception as e:
            return {"nome": "Integracao_Automatica"}


gemini_service = GeminiService()