-- Plano de Ação El Niño 2026 — ARARAS MT (CIEVS/SES-MT)
-- Histórico append-only: nunca UPDATE em atualizacao/evidencia/validacao/audit_log.
-- SEI é o processo administrativo oficial; ARARAS guarda link + cópia PDF opcional.
-- SQLite: INTEGER PRIMARY KEY AUTOINCREMENT | PostgreSQL: SERIAL PRIMARY KEY

CREATE TABLE IF NOT EXISTS plano (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    vigencia_inicio TEXT,
    vigencia_fim TEXT,
    fonte_xlsx TEXT,
    criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eixo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plano_codigo TEXT NOT NULL,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    ordem INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    eixo_codigo TEXT NOT NULL,
    descricao TEXT NOT NULL,
    meta_numerica TEXT,
    unidade TEXT,
    prazo TEXT
);

CREATE TABLE IF NOT EXISTS acao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    meta_codigo TEXT,
    eixo_codigo TEXT NOT NULL,
    area_id TEXT NOT NULL,
    descricao TEXT NOT NULL,
    responsavel TEXT,
    prazo TEXT,
    prazo_iso TEXT,
    prioridade TEXT,
    status_inicial TEXT NOT NULL DEFAULT 'nao_iniciada',
    linha_fonte INTEGER
);

CREATE TABLE IF NOT EXISTS indicador (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    codigo_fonte TEXT,
    acao_codigo TEXT,
    meta_codigo TEXT,
    eixo_codigo TEXT,
    area_id TEXT NOT NULL,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL,
    modo_atualizacao TEXT NOT NULL,
    formula TEXT,
    meta_numerica TEXT,
    unidade TEXT,
    direcao TEXT,
    fonte TEXT,
    periodicidade TEXT,
    entra_no_indice INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS atualizacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alvo TEXT NOT NULL,
    alvo_codigo TEXT NOT NULL,
    status TEXT NOT NULL,
    valor TEXT,
    observacao TEXT,
    situacao_validacao TEXT NOT NULL DEFAULT 'informado',
    autor_email TEXT,
    autor_area_id TEXT,
    criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atualizacao_id INTEGER,
    acao_codigo TEXT,
    tipo TEXT,
    documento TEXT,
    data TEXT,
    area TEXT,
    versao TEXT,
    responsavel_envio TEXT,
    uploaded_at TEXT NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'enviada',
    link_sei TEXT,
    arquivo TEXT,
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS validacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atualizacao_id INTEGER NOT NULL,
    decisao TEXT NOT NULL,
    validador_email TEXT,
    observacao TEXT,
    criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisao_sala (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em TEXT NOT NULL,
    autor_email TEXT,
    tipo TEXT,
    titulo TEXT NOT NULL,
    texto TEXT NOT NULL,
    acao_codigo TEXT
);

CREATE TABLE IF NOT EXISTS alerta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evento TEXT NOT NULL,
    alvo_codigo TEXT,
    canal TEXT NOT NULL DEFAULT 'email',
    payload TEXT,
    status TEXT NOT NULL DEFAULT 'pendente',
    criado_em TEXT NOT NULL,
    enviado_em TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em TEXT NOT NULL,
    ator_email TEXT,
    acao TEXT NOT NULL,
    entidade TEXT,
    entidade_id TEXT,
    detalhe TEXT
);

-- Status ação: nao_iniciada | em_andamento | em_validacao | concluida | impedida | suspensa | nao_aplicavel
-- Validação: informado → em_validacao → validado | rejeitado
-- Modo indicador: automatico | semiautomatico | documental
