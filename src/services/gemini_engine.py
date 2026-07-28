import itertools
import httpx
import json
import logging

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiRotator:
    """
    Gerencia o pool de tokens Gemini com rotatividade Round-Robin.
    Inicialização lazy — só conecta ao banco quando get_next() é chamado.
    """

    def __init__(self):
        self._tokens = []
        self._cycle = None

    def refresh_tokens(self):
        """Busca tokens ativos no banco de dados."""
        try:
            from src.core.security import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT API_KEY, MODELO FROM TRB_GEMINI_TOKENS WHERE ATIVO = 1")
            rows = cursor.fetchall()
            self._tokens = [{"api_key": row[0], "modelo": row[1]} for row in rows]
            cursor.close()
            conn.close()

            logger.info(f"Tokens Gemini carregados: {len(self._tokens)}")
            if self._tokens:
                import random
                random.shuffle(self._tokens)
                self._cycle = itertools.cycle(self._tokens)
            else:
                self._cycle = None
        except Exception as e:
            logger.error(f"Erro ao carregar tokens Gemini: {e}")
            self._cycle = None

    def get_next(self):
        """Retorna o próximo token e modelo do ciclo (lazy load)."""
        if not self._cycle:
            self.refresh_tokens()
            if not self._cycle:
                raise Exception("Nenhum token Gemini ativo configurado no banco de dados.")

        token_data = next(self._cycle)
        logger.info(f"Usando token Gemini: {token_data['api_key'][:8]}...")
        self._update_usage(token_data['api_key'])
        return token_data

    def _update_usage(self, api_key):
        try:
            from src.core.security import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE TRB_GEMINI_TOKENS SET ULTIMO_USO = GETDATE(), USO_COUNT = USO_COUNT + 1 WHERE API_KEY = ?",
                (api_key,),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            pass


gemini_rotator = GeminiRotator()


async def analyze_code_snippet(snippet: str, context: str = "padrao"):
    """
    Usa o Gemini para analisar um snippet de código ou comando e extrair metadados.
    context: 'padrao' (analise de codigo), 'chat' (conversa geral), 'log' (analise de log)
    """
    token_data = gemini_rotator.get_next()
    token = token_data["api_key"]

    if context == "log":
        prompt = f"""Você é um analista de sistemas sênior. Analise o resumo de logs abaixo e identifique padrões de erro,
integrações críticas com falha e sugira ações imediatas para correção.

LOGS:
{snippet}"""
    elif context == "chat":
        prompt = f"""Você é o assistente inteligente do TributosAPI (Antigravity).

O usuário administra integrações de APIs através deste sistema.

REGRAS DE CONVERSAÇÃO E SEGURANÇA (OBRIGATÓRIAS):
1. Controle a sua prolixidade. Seja direto, conciso e sucinto, sem introduções robóticas como "Compreendido, para criar...", "Entendi" ou "Claro".
2. JAMAIS divulgue ou mencione os nomes reais das tabelas de banco de dados (ex: TRB_INTEGRACAO, TRB_CONEXAO) ou estrutura de SQL para o usuário. Fale sempre no contexto da "aplicação" ("Criada a integração X", "Configurado no sistema").
3. O usuário não sabe e não deve saber que o backend funciona gerando SQL a partir de suas respostas explícitas. Retorne mensagens sobre "Gerenciamento de Integrações" e "Configuração de Endpoints".

CAPACIDADES DE AUTO-EXECUÇÃO SILENCIOSA:
- Apesar de não poder mostrar SQL ao usuário, para as ações em que o usuário pede explicitamente a CRIAÇÃO, EDIÇÃO ou DELEÇÃO de uma integração, você DEVE gerar silenciosamente o código SQL correspondente para a tabela real TRB_INTEGRACAO ou TRB_CONEXAO (ID_CONEXAO genérico: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890') dentro de um bloco delimitado por ```sql ... ```.
- MUITO IMPORTANTE: O banco de dados é MICROSOFT SQL SERVER (T-SQL). NÃO use funções de outros bancos como UUID() ou NOW(). Use NEWID() e GETDATE().
- O campo ID_INTEGRACAO é IDENTITY(1,1), não tente inseri-lo num INSERT.
- Coloque o bloco de código SQL no FINAL absoluto da sua resposta (ele será interceptado pelo backend e deletado da interface para o usuário).
- Forneça a resposta natural em texto normal ensinando algo sobre integrações ou confirmando que fez a ação solicitada.

DADOS DIGITADOS PELO USUÁRIO PARA ANÁLISE:
- {snippet}"""
    else:
        prompt = f"""Analise o seguinte código Python de integração e extraia:
1. URL Base
2. Método HTTP (POST, GET, etc)
3. Headers necessários
4. Tipo de Autenticação identificado (TOKEN, JWT, SESSION, ou NONE)
5. Se for login, qual o campo provável que retorna o token no JSON?
6. Sugestão de mapeamento de variáveis para o payload (campos entre chaves {{}}).

Código:
{snippet}

Retorne APENAS um JSON válido."""

    # Tentar até 3 tokens diferentes caso ocorra Quota Limit (429)
    max_attempts = min(3, len(gemini_rotator._tokens) if gemini_rotator._tokens else 1)
    last_error = ""

    for attempt in range(max_attempts):
        try:
            token_data = gemini_rotator.get_next()
            token = token_data["api_key"]
            modelo = token_data.get("modelo", "gemini-2.5-flash")
            url = GEMINI_BASE_URL.format(model=modelo)

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url}?key={token}",
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                )

                if resp.status_code == 429:
                    last_error = f"Token {attempt+1} esgotado (429). Tentando próximo..."
                    logger.warning(last_error)
                    continue

                if resp.status_code != 200:
                    return f"Erro na API Gemini: {resp.status_code} - {resp.text}"

                data = resp.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )

                if text.strip().startswith("```json"):
                    text = text.strip()[7:-3].strip()
                elif text.strip().startswith("```"):
                    text = text.strip()[3:-3].strip()

                return text

        except Exception as e:
            last_error = str(e)
            logger.error(f"Tentativa {attempt+1} falhou: {e}")
            continue

    return f"Erro: Todos os tokens Gemini falharam ou atingiram o limite de cota (429). {last_error}"

