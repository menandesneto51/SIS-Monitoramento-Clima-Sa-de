-- Sala de Situação — Plano El Niño 2026–2027
-- ARARAS = repositório operacional. E-mail/WhatsApp só notificam.
-- SQLite/PostgreSQL: tipos TEXT/INTEGER; timestamps ISO-8601.

CREATE TABLE IF NOT EXISTS plano_area (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    sigla TEXT,
    superintendencia TEXT
);

CREATE TABLE IF NOT EXISTS plano_acao (
    id TEXT PRIMARY KEY,              -- ARARAS-016
    plano_id TEXT NOT NULL,
    eixo TEXT NOT NULL,
    meta TEXT NOT NULL,
    descricao TEXT NOT NULL,
    area_id TEXT NOT NULL REFERENCES plano_area(id),
    responsavel_texto TEXT,
    prazo DATE,
    prioridade TEXT NOT NULL DEFAULT 'Alta',
    status TEXT NOT NULL DEFAULT 'nao_iniciada',
    -- nao_iniciada|em_andamento|em_validacao|concluida|impedida|suspensa|nao_aplicavel
    progresso_pct REAL,
    numerador REAL,
    denominador REAL,
    pendencia TEXT,
    previsao_conclusao DATE,
    atualizado_em TEXT,
    atualizado_por TEXT
);

CREATE TABLE IF NOT EXISTS plano_indicador (
    id TEXT PRIMARY KEY,              -- ARARA-001
    acao_id TEXT,
    eixo TEXT,
    tipo TEXT NOT NULL,               -- execucao|capacidade|resultado|risco_gatilho
    nome TEXT NOT NULL,
    formula TEXT,
    meta_gatilho TEXT,
    unidade TEXT,
    direcao TEXT,                     -- maior_melhor|menor_melhor|gatilho
    fonte TEXT,
    periodicidade TEXT,
    automacao TEXT NOT NULL,          -- automatico|semiautomatico|manual
    area_id TEXT NOT NULL,
    semaforo_regra TEXT,
    evidencia_minima TEXT,
    valor_oficial REAL,
    status_oficial TEXT,              -- nao_informado|informado|em_validacao|validado|rejeitado
    valor_calculado_em TEXT
);

CREATE TABLE IF NOT EXISTS plano_atualizacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acao_id TEXT NOT NULL,
    indicador_id TEXT,
    usuario_email TEXT NOT NULL,
    area_id TEXT NOT NULL,
    status TEXT,
    numerador REAL,
    denominador REAL,
    progresso_pct REAL,
    descricao TEXT,
    resultado_texto TEXT,
    pendencia TEXT,
    previsao_conclusao DATE,
    criado_em TEXT NOT NULL,
    validacao_status TEXT NOT NULL DEFAULT 'informado',
    -- informado|em_validacao|validado|rejeitado
    validado_por TEXT,
    validado_em TEXT,
    parecer TEXT
);

CREATE TABLE IF NOT EXISTS plano_evidencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atualizacao_id INTEGER NOT NULL REFERENCES plano_atualizacao(id),
    acao_id TEXT NOT NULL,
    indicador_id TEXT,
    tipo TEXT NOT NULL,              -- nota_tecnica|planilha|oficio|ata|foto|relatorio|link_sei
    titulo TEXT,
    documento_nr TEXT,
    data_documento DATE,
    area_id TEXT,
    versao TEXT,
    enviado_por TEXT,
    criado_em TEXT NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'enviado',
    processo_sei TEXT,
    documento_sei TEXT,
    url_sei TEXT,
    arquivo_path TEXT,
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS plano_decisao (
    id TEXT PRIMARY KEY,              -- SS-2026-038
    reuniao_id TEXT,
    descricao TEXT NOT NULL,
    area_id TEXT NOT NULL,
    prazo TEXT,
    prioridade TEXT DEFAULT 'Alta',
    status TEXT NOT NULL DEFAULT 'aberta',
    criado_em TEXT NOT NULL,
    criado_por TEXT
);

CREATE TABLE IF NOT EXISTS plano_auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entidade TEXT NOT NULL,         -- acao|indicador|evidencia|decisao|usuario
    entidade_id TEXT NOT NULL,
    evento TEXT NOT NULL,
    usuario_email TEXT,
    de_json TEXT,
    para_json TEXT,
    criado_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plano_acao_area ON plano_acao(area_id, status);
CREATE TABLE IF NOT EXISTS plano_notificacao_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evento TEXT NOT NULL,
    acao_id TEXT,
    canal TEXT NOT NULL,            -- email|whatsapp|sistema
    destinatario TEXT NOT NULL,
    enviado_em TEXT NOT NULL,
    ok INTEGER NOT NULL DEFAULT 1
);
