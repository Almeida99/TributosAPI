import json
import logging
import re
from xml.etree.ElementTree import Element, tostring

logger = logging.getLogger(__name__)


class PayloadService:
    """Serviço para geração de payloads (JSON/XML)"""

    def gerar_payload(self, integracao: dict, dados: list, valor_where: str = None) -> str:
        """
        Gera payload baseado na integração:
        1. Se houver payload_template: usar template com substituição
        2. Se houver consulta_sql que retorna XML/JSON direto: usar resultado
        3. Se houver dados: converter para JSON ou XML baseado no content_type
        4. Fallback: JSON vazio
        """
        
        # Caso 1: Template definido
        template = integracao.get("payload_template")
        if template and dados:
            return self._substituir_placeholders(template, dados[0], valor_where)
        
        # Caso 2: Consulta que retorna payload pronto (quando consulta_sql é o payload)
        consulta_sql = integracao.get("consulta_sql")
        if consulta_sql and not integracao.get("payload_template"):
            # Se a consulta for para retornar o payload diretamente
            # Este caso é tratado na orquestra - aqui apenas geramos do zero
            pass
        
        # Caso 3: Converter dados para formato baseado no content_type
        if dados:
            primeiro = dados[0]
            content_type = integracao.get("content_type", "application/json").lower()
            
            if "xml" in content_type:
                return self._dict_to_xml(primeiro)
            else:
                # JSON padrão
                return json.dumps(primeiro, ensure_ascii=False, default=str)
        
        # Caso 4: Fallback
        return "{}"

    def _substituir_placeholders(self, template: str, dados: dict, valor_where: str = None) -> str:
        """Substitui placeholders {campo} pelos valores"""
        if not template:
            return "{}"
        
        resultado = template
        
        # Substituir cada campo dos dados
        for chave, valor in dados.items():
            placeholder = "{" + chave + "}"
            if placeholder in resultado:
                if valor is None:
                    resultado = resultado.replace(placeholder, "")
                elif isinstance(valor, (int, float, bool)):
                    resultado = resultado.replace(placeholder, str(valor))
                else:
                    # Se o campo contiver 'xml', injetar sem escapamento
                    if "xml" in chave.lower():
                        resultado = resultado.replace(placeholder, str(valor))
                    else:
                        # Escapar para XML se necessário
                        valor_str = str(valor).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        resultado = resultado.replace(placeholder, valor_str)
        
        # Substituir {valor} se existir
        if valor_where and "{valor}" in resultado:
            resultado = resultado.replace("{valor}", valor_where)
            
        return resultado

    def _dict_to_xml(self, data: dict, root_tag: str = "root") -> str:
        """Converte dicionário para XML"""
        root = Element(root_tag)
        for chave, valor in data.items():
            if valor is None:
                Element(chave, {}, root)
            else:
                child = Element(chave)
                child.text = str(valor)
                root.append(child)
        return tostring(root, encoding='unicode')


payload_service = PayloadService()