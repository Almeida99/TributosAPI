# TributosAPI

Motor de integração para sistemas tributários municipais. Permite criar, gerenciar e executar integrações dinâmicas via scripts Python, com suporte a API externa para terceiros autenticada por JWT.

## Multibanco

Uma única instância atende vários bancos SQL Server. Cada banco tem um **slug** usado no path da URL.

| Uso | URL |
|-----|-----|
| Seletor de bancos | `/` |
| Configurar bancos | `/config/bancos` |
| Painel do município | `/{slug}/integracoes?usr_cod=...` |
| API terceiros | `/{slug}/api/v1/...` |
| Executar integração | `/{slug}/v1/executar/{nome}` |
| Docs Swagger | `/{slug}/api/docs` |
| Health global | `/api/v1/health` |

Exemplo: `http://localhost:9097/lauro/integracoes?usr_cod=1`

O catálogo fica em `data/bancos.json` (volume Docker). **Os bancos são cadastrados apenas pela interface** em `/config/bancos`. As senhas são gravadas **cifradas** (`enc:v1:...`) com `BANCOS_SECRET_KEY`.

### Fluxo de cadastro

1. Suba a aplicação com `.env` (segredos: `BANCOS_SECRET_KEY`, `CONFIG_ADMIN_*`, etc.)
2. Acesse `/config/bancos` e autentique com o admin
3. Clique em **Novo Banco**, preencha servidor/database/usuário/senha e salve
4. O sistema aplica automaticamente o `init.sql` (tabelas V3) no banco novo
5. Na home (`/`), escolha o município e use `/{slug}/integracoes?...`

## Segurança (produção)

| Controle | Comportamento |
|----------|----------------|
| Home, painel, execução interna e `/config/*` | HTTP Basic (`CONFIG_ADMIN_USER` / `CONFIG_ADMIN_PASSWORD`). Sem essas vars → 503 |
| Senhas no catálogo | Cifradas com Fernet (`BANCOS_SECRET_KEY`). Texto puro legado é migrado na leitura |
| Credenciais de município | Só na interface / `bancos.json` — **não** no `.env` |
| SQL Server | `DB_ENCRYPT=yes` por padrão; `DB_TRUST_SERVER_CERTIFICATE` configurável |
| Painel (`usr_cod`) | Mantido para identificar/validar o usuário do ERP, além do HTTP Basic administrativo |
| API externa de terceiros (`/{slug}/api/v1/*`) | JWT + bcrypt + `API_ADMIN_KEY`; não usa `CONFIG_ADMIN_*` |

Checklist antes de subir:

1. Copiar `.env.example` → `.env` e preencher **todos** os segredos
2. Gerar `BANCOS_SECRET_KEY`: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
3. Definir `CONFIG_ADMIN_USER` / `CONFIG_ADMIN_PASSWORD` fortes
4. Definir `API_JWT_SECRET` e `API_ADMIN_KEY` longos e aleatórios
5. Restringir a porta `9097` (firewall / reverse proxy) e preferir HTTPS no proxy
6. Manter o volume `data/` com permissão restrita (contém o catálogo)

## Requisitos

- Docker e Docker Compose
- SQL Server (banco já existente com a tabela `FR_USUARIO`)

## Instalação

```bash
# 1. Clonar o repositório
git clone <repo> && cd tributosapi

# 2. Configurar variáveis de ambiente (segredos da app — não os municípios)
cp .env.example .env
# Editar: BANCOS_SECRET_KEY, CONFIG_ADMIN_*, API_*

# 3. Subir o container
docker compose up -d --build
```

O `init_db.py` no startup aplica o schema nos bancos **já cadastrados** no catálogo. Bancos novos cadastrados pela UI também recebem o `init.sql` na hora do salvamento.
- **Não altera** a tabela `FR_USUARIO`

Depois de subir, acesse `/config/bancos` (Basic Auth) e cadastre cada município.

## Configuração (.env)

| Variável | Descrição |
|----------|-----------|
| `DB_DRIVER` | Driver ODBC padrão (ex: `ODBC Driver 18 for SQL Server`) |
| `DB_ENCRYPT` | `yes`/`no` — TLS na conexão ODBC (padrão: `yes`) |
| `DB_TRUST_SERVER_CERTIFICATE` | `yes`/`no` — confiar em cert. autoassinado (padrão: `yes`) |
| `BANCOS_SECRET_KEY` | Chave Fernet para cifrar senhas em `bancos.json` (**obrigatória** para gravar) |
| `CONFIG_ADMIN_USER` | Usuário HTTP Basic da home, do painel, da execução interna e de `/config/*` |
| `CONFIG_ADMIN_PASSWORD` | Senha HTTP Basic da home, do painel, da execução interna e de `/config/*` |
| `API_JWT_SECRET` | Segredo JWT para API de terceiros (obrigatório para ativar o módulo) |
| `API_TOKEN_EXPIRE_MINUTES` | Tempo de expiração do token em minutos (padrão: 60) |
| `API_ORCHESTRATOR_USR_COD` | Código do usuário técnico na `FR_USUARIO` |
| `API_ADMIN_KEY` | Chave de administração para gerenciar cadastros via API |

## Estrutura do Projeto

```
tributosapi/
├── data/
│   └── bancos.json              # Catálogo multibanco (gerado/editado pela UI)
├── database/
│   └── init.sql                 # Script único de inicialização do banco
├── src/
│   ├── api/                     # Módulo API externa (terceiros/JWT)
│   ├── core/
│   │   ├── admin_auth.py        # HTTP Basic compartilhado das áreas administrativas
│   │   ├── config.py            # Variáveis de ambiente
│   │   ├── database.py          # Conexões SQL Server (por tenant)
│   │   ├── tenants.py           # Catálogo de bancos
│   │   ├── secrets.py           # Cifra/decifra senhas do catálogo
│   │   ├── schema_init.py       # Aplica init.sql ao cadastrar banco
│   │   └── tenant_middleware.py # Resolve /{slug}/...
│   ├── services/
│   ├── ui/
│   │   ├── config_router.py     # Tela /config/bancos (Basic Auth)
│   │   └── router.py            # Painel administrativo
│   └── main.py
├── init_db.py
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Tabelas do Banco

| Tabela | Descrição |
|--------|-----------|
| `TRB_INTEGRACAO` | Integrações cadastradas (nome, script Python, status) |
| `TRB_LOG_INTEGRACAO` | Logs de execução de cada integração |
| `TRB_GEMINI_TOKENS` | Tokens de API do Gemini (assistente IA) |
| `TRB_INTEGRACAO_TERCEIROS_CADASTRO` | Usuários de terceiros (login/senha hash) |
| `TRB_INTEGRACAO_TERCEIROS_ENDPOINT` | Permissões: qual terceiro acessa qual integração |
| `TRB_INTEGRACAO_TERCEIROS_AUDITORIA` | Log de auditoria (login, execuções, IPs) |
| `FR_USUARIO` | **Pré-existente** — tabela de usuários do sistema (não é alterada) |

---

## Painel Administrativo

1. Acesse `/` e autentique com `CONFIG_ADMIN_*` para escolher o banco, ou vá direto em `http://localhost:9097/{slug}/integracoes?usr_cod=<USR_CODIGO>`.
2. A mesma autenticação HTTP Basic protege todo o painel, a execução interna `/{slug}/v1/executar/{nome}` e `/config/*`.
3. O `usr_cod` continua sendo usado para identificar e validar o usuário do ERP.

> O painel por `usr_cod` deve permanecer em rede interna ou atrás de VPN/proxy autenticado.

### Funcionalidades

- **Bancos** (`/config/bancos`): único lugar para cadastrar, editar, testar e ativar/desativar municípios
- **Integrações**: Criar, editar, ativar/desativar e testar integrações
- **Terceiros**: Cadastrar usuários externos, definir senhas, vincular endpoints permitidos
- **Logs**: Visualizar histórico de execuções com payloads e respostas
- **Instalação**: Tela para configuração inicial do sistema

### Criando uma Integração

1. Acesse **Integrações > Nova Integração**
2. Preencha o **Nome** (identificador amigável) e o **Nome Técnico** (será a URL do endpoint)
3. Escreva o **Script Python** ou use um dos templates:
   - **XML**: Para integrações SOAP/XML
   - **JSON**: Para integrações REST/JSON
   - **Terceiro**: Template com paginação e filtros automáticos para API externa

### Script Python — Variáveis Disponíveis

O script recebe automaticamente as seguintes variáveis:

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `params` | `dict` | Parâmetros enviados no JSON da requisição |
| `executar_consulta(sql, params)` | `function` | Executa uma query SELECT no banco e retorna lista de dicts |
| `executar_insert(sql, params)` | `function` | Executa INSERT/UPDATE/DELETE no banco |
| `resultado` | `any` | Variável que deve conter o retorno da integração |

---

## API Externa (Terceiros)

Módulo ativado automaticamente quando `API_JWT_SECRET` está definido no `.env`.
A API externa em `/{slug}/api/v1/*` continua autenticada por JWT e não é protegida por `CONFIG_ADMIN_*`.

### Fluxo de Autenticação

```
[Terceiro] → POST /{slug}/api/v1/auth/token {login, senha}
         ← {access_token, token_type, expires_in}

[Terceiro] → POST /{slug}/api/v1/executar/hipac
              Authorization: Bearer <token>
              Body: {"pagina": 1}
         ← { ... }
```

### Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/{slug}/api/v1/auth/token` | Autenticação (retorna JWT) |
| `POST` | `/{slug}/api/v1/executar/{nome}` | Executa uma integração (requer Bearer token) |
| `GET`  | `/{slug}/api/docs` | Swagger interativo (HTTP Basic com o **login/senha do próprio terceiro**, não o `CONFIG_ADMIN_*`) |

---

## Docker

```bash
# Subir
docker compose up -d --build

# Ver logs
docker logs tributariai_api_tx -f

# Reiniciar (após alterar código Python)
docker compose restart tributariai_api

# Rebuild completo
docker compose up -d --build --force-recreate
```

> **Nota**: Os diretórios `src/`, `database/` e `data/` são montados como volumes. Alterações em templates HTML são refletidas imediatamente, mas alterações em código Python exigem `docker compose restart`.
