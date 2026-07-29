-- Placeholder / contrato de dados SISREG para o índice de pressão.
-- Popular a tabela operacional `ops_sisreg_municipio` (Postgres/SQLite do SIS)
-- com agregação municipal diária ou da última carga.

-- Colunas esperadas pelo motor `sisclima.engines.indice_pressao_saude`:
--   cod_ibge              CHAR(7)   -- IBGE 7 dígitos
--   municipio             TEXT
--   regional_saude        TEXT      -- opcional
--   data_referencia       DATE
--   fila_media_h          NUMERIC   -- tempo médio de espera (horas)
--   tempo_espera_h        NUMERIC   -- alias aceito se fila_media_h ausente
--   solicitacoes_abertas  INTEGER
--   taxa_regulacao_pct    NUMERIC   -- opcional
--   fonte                 TEXT      -- ex.: SISREG_DW / CENTRAL_REGULACAO

-- Exemplo de DDL (ajustar schema conforme DW SES):
/*
CREATE TABLE IF NOT EXISTS ops_sisreg_municipio (
    cod_ibge             VARCHAR(7) NOT NULL,
    municipio            TEXT,
    regional_saude       TEXT,
    data_referencia      DATE,
    fila_media_h         DOUBLE PRECISION,
    tempo_espera_h       DOUBLE PRECISION,
    solicitacoes_abertas INTEGER,
    taxa_regulacao_pct   DOUBLE PRECISION,
    fonte                TEXT DEFAULT 'SISREG',
    atualizado_em        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
*/

-- SELECT de exemplo (substituir pela view real do DW):
-- SELECT ... FROM dbo.VW_SISREG_FILA_MUNICIPAL WHERE uf = 'MT';
