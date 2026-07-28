-- ============================================================
-- TRIBUTOSAPI - SCRIPT DE INICIALIZAÇÃO COMPLETO
-- ============================================================
-- Executa ao subir o projeto em um novo banco.
-- - Cria todas as tabelas necessárias (V3 + Terceiros)
-- - Remove tabelas legadas do projeto anterior
-- - NÃO altera a tabela FR_USUARIO
-- ============================================================

-- ============================================================
-- ETAPA 1: GARANTIR TABELAS V3 (Integrações + Logs + Gemini)
-- ============================================================

-- ============================================================
-- ETAPA 2: CRIAR TABELAS V3 (Integrações + Logs + Gemini)
-- ============================================================

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'TRB_INTEGRACAO')
BEGIN
    CREATE TABLE dbo.TRB_INTEGRACAO (
        ID_INTEGRACAO    INT IDENTITY(1,1) PRIMARY KEY,
        NOME             NVARCHAR(255) NOT NULL,
        NOME_INTEGRACAO  NVARCHAR(255) NOT NULL,
        ATIVO            BIT NOT NULL DEFAULT 1,
        SCRIPT_PYTHON    NVARCHAR(MAX) NULL,
        DATA_CRIACAO     DATETIME NOT NULL DEFAULT GETDATE(),
        DATA_ATUALIZACAO DATETIME NULL
    );
    PRINT '   TRB_INTEGRACAO criada.';
END
ELSE
BEGIN
    -- Migração: adicionar colunas V3 se a tabela já existir (ex: banco com V2)
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TRB_INTEGRACAO' AND COLUMN_NAME = 'NOME_INTEGRACAO')
        ALTER TABLE dbo.TRB_INTEGRACAO ADD NOME_INTEGRACAO NVARCHAR(255) NULL;

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TRB_INTEGRACAO' AND COLUMN_NAME = 'SCRIPT_PYTHON')
        ALTER TABLE dbo.TRB_INTEGRACAO ADD SCRIPT_PYTHON NVARCHAR(MAX) NULL;

    -- Preencher NOME_INTEGRACAO se vazio
    UPDATE dbo.TRB_INTEGRACAO 
    SET NOME_INTEGRACAO = REPLACE(UPPER(NOME), ' ', '') 
    WHERE NOME_INTEGRACAO IS NULL;

    PRINT '   TRB_INTEGRACAO ja existe. Colunas V3 verificadas/adicionadas.';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'TRB_GEMINI_TOKENS')
BEGIN
    CREATE TABLE dbo.TRB_GEMINI_TOKENS (
        ID_TOKEN    INT IDENTITY(1,1) PRIMARY KEY,
        API_KEY     NVARCHAR(500) NOT NULL,
        MODELO      NVARCHAR(100) NOT NULL DEFAULT 'gemini-1.5-flash',
        ATIVO       BIT NOT NULL DEFAULT 1,
        ULTIMO_USO  DATETIME NULL,
        USO_COUNT   INT DEFAULT 0,
        DATA_CRIACAO DATETIME NOT NULL DEFAULT GETDATE()
    );
    PRINT '   TRB_GEMINI_TOKENS criada.';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'TRB_LOG_INTEGRACAO')
BEGIN
    CREATE TABLE dbo.TRB_LOG_INTEGRACAO (
        ID_LOG                BIGINT IDENTITY(1,1) PRIMARY KEY,
        ID_INTEGRACAO         INT NOT NULL,
        NOME_INTEGRACAO       NVARCHAR(255) NULL,
        USR_COD               INT NULL,
        ID_CADASTRO_TERCEIRO  INT NULL,
        FILTRO                NVARCHAR(MAX) NULL,
        PAYLOAD_ENVIO   NVARCHAR(MAX) NULL,
        PAYLOAD_RETORNO NVARCHAR(MAX) NULL,
        STATUS          NVARCHAR(50) NULL,
        MENSAGEM        NVARCHAR(MAX) NULL,
        DATA_HORA       DATETIME NOT NULL DEFAULT GETDATE(),
        DURACAO_MS      INT NULL
    );
    PRINT '   TRB_LOG_INTEGRACAO criada.';
END
ELSE
BEGIN
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TRB_LOG_INTEGRACAO' AND COLUMN_NAME = 'NOME_INTEGRACAO')
        ALTER TABLE dbo.TRB_LOG_INTEGRACAO ADD NOME_INTEGRACAO NVARCHAR(255) NULL;

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TRB_LOG_INTEGRACAO' AND COLUMN_NAME = 'ID_CADASTRO_TERCEIRO')
        ALTER TABLE dbo.TRB_LOG_INTEGRACAO ADD ID_CADASTRO_TERCEIRO INT NULL;

    -- Alterar USR_COD para NULL caso seja NOT NULL
    IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TRB_LOG_INTEGRACAO' AND COLUMN_NAME = 'USR_COD' AND IS_NULLABLE = 'NO')
        ALTER TABLE dbo.TRB_LOG_INTEGRACAO ALTER COLUMN USR_COD INT NULL;

    PRINT '   TRB_LOG_INTEGRACAO ja existe. Colunas adicionais verificadas.';
END
GO

-- ============================================================
-- ETAPA 3: CRIAR TABELAS DE TERCEIROS (API Externa com JWT)
-- ============================================================

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'TRB_INTEGRACAO_TERCEIROS_CADASTRO')
BEGIN
    CREATE TABLE dbo.TRB_INTEGRACAO_TERCEIROS_CADASTRO (
        id_cadastro      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        login            NVARCHAR(255) NOT NULL,
        senha_hash       NVARCHAR(500) NOT NULL,
        ativo            BIT NOT NULL DEFAULT 1,
        data_criacao     DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
        data_atualizacao DATETIME2(0) NULL,
        CONSTRAINT UQ_TRB_INT_TERC_CAD_LOGIN UNIQUE (login)
    );
    PRINT '   TRB_INTEGRACAO_TERCEIROS_CADASTRO criada.';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'TRB_INTEGRACAO_TERCEIROS_ENDPOINT')
BEGIN
    CREATE TABLE dbo.TRB_INTEGRACAO_TERCEIROS_ENDPOINT (
        id_endpoint      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        id_cadastro      INT NOT NULL,
        nome_integracao  NVARCHAR(255) NOT NULL,
        ativo            BIT NOT NULL DEFAULT 1,
        data_criacao     DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
        CONSTRAINT FK_TRB_INT_TERC_EP_CAD FOREIGN KEY (id_cadastro)
            REFERENCES dbo.TRB_INTEGRACAO_TERCEIROS_CADASTRO (id_cadastro) ON DELETE CASCADE,
        CONSTRAINT UQ_TRB_INT_TERC_EP_CAD_NOME UNIQUE (id_cadastro, nome_integracao)
    );
    CREATE INDEX IX_TRB_INT_TERC_EP_CAD ON dbo.TRB_INTEGRACAO_TERCEIROS_ENDPOINT (id_cadastro);
    PRINT '   TRB_INTEGRACAO_TERCEIROS_ENDPOINT criada.';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'TRB_INTEGRACAO_TERCEIROS_AUDITORIA')
BEGIN
    CREATE TABLE dbo.TRB_INTEGRACAO_TERCEIROS_AUDITORIA (
        id_auditoria     BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        id_cadastro      INT NULL,
        tipo_evento      NVARCHAR(30) NOT NULL,
        metodo_http      NVARCHAR(16) NULL,
        rota             NVARCHAR(1024) NULL,
        status_http      INT NULL,
        duracao_ms       INT NULL,
        endereco_ip      NVARCHAR(128) NULL,
        user_agent       NVARCHAR(512) NULL,
        login_tentativa  NVARCHAR(255) NULL,
        sucesso          BIT NULL,
        detalhe_erro     NVARCHAR(500) NULL,
        json_requisicao  NVARCHAR(MAX) NULL,
        json_retorno     NVARCHAR(MAX) NULL,
        data_evento      DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
        CONSTRAINT FK_TRB_INT_TERC_AUD_CAD FOREIGN KEY (id_cadastro)
            REFERENCES dbo.TRB_INTEGRACAO_TERCEIROS_CADASTRO (id_cadastro) ON DELETE SET NULL
    );
    CREATE INDEX IX_TRB_INT_TERC_AUD_CAD ON dbo.TRB_INTEGRACAO_TERCEIROS_AUDITORIA (id_cadastro);
    CREATE INDEX IX_TRB_INT_TERC_AUD_DH  ON dbo.TRB_INTEGRACAO_TERCEIROS_AUDITORIA (data_evento);
    PRINT '   TRB_INTEGRACAO_TERCEIROS_AUDITORIA criada.';
END
ELSE
BEGIN
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TRB_INTEGRACAO_TERCEIROS_AUDITORIA' AND COLUMN_NAME = 'json_requisicao')
        ALTER TABLE dbo.TRB_INTEGRACAO_TERCEIROS_AUDITORIA ADD json_requisicao NVARCHAR(MAX) NULL;

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TRB_INTEGRACAO_TERCEIROS_AUDITORIA' AND COLUMN_NAME = 'json_retorno')
        ALTER TABLE dbo.TRB_INTEGRACAO_TERCEIROS_AUDITORIA ADD json_retorno NVARCHAR(MAX) NULL;

    -- Renomear data_hora para data_evento se necessário (tratamento seguro para migração manual)
    IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TRB_INTEGRACAO_TERCEIROS_AUDITORIA' AND COLUMN_NAME = 'data_hora')
       AND NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TRB_INTEGRACAO_TERCEIROS_AUDITORIA' AND COLUMN_NAME = 'data_evento')
    BEGIN
        EXEC sp_rename 'dbo.TRB_INTEGRACAO_TERCEIROS_AUDITORIA.data_hora', 'data_evento', 'COLUMN';
    END

    PRINT '   TRB_INTEGRACAO_TERCEIROS_AUDITORIA ja existe. Colunas JSON e data_evento verificadas.';
END
GO

PRINT '>> Inicializacao do banco concluida com sucesso!';
GO
