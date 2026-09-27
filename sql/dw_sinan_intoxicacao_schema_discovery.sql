/*
SIS Clima-Saúde MT
Descoberta segura do schema da view de Intoxicação Exógena.

Objetivo:
confirmar os nomes reais das colunas necessárias ao contrato de
notificações de intoxicação por inalação de fumaça antes de alterar
sql/dw_sinan_agravos_calor.sql.

Somente leitura.
*/

DECLARE @schema sysname = N'dbo';
DECLARE @view sysname = N'VW_SINAN_INTOXICACAOEXOGENA';

SELECT
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.CHARACTER_MAXIMUM_LENGTH,
    c.IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS c
WHERE c.TABLE_SCHEMA = @schema
  AND c.TABLE_NAME = @view
ORDER BY c.ORDINAL_POSITION;

-- Candidatos semânticos esperados pelo contrato oficial.
SELECT
    c.COLUMN_NAME,
    c.DATA_TYPE,
    CASE
        WHEN UPPER(c.COLUMN_NAME) LIKE '%AGENT%' THEN 'agent'
        WHEN UPPER(c.COLUMN_NAME) LIKE '%TOX%' THEN 'agent'
        WHEN UPPER(c.COLUMN_NAME) LIKE '%VIA%' THEN 'route'
        WHEN UPPER(c.COLUMN_NAME) LIKE '%CIRC%' THEN 'circumstance'
        WHEN UPPER(c.COLUMN_NAME) LIKE '%NOTIF%' THEN 'notification'
        ELSE 'other'
    END AS semantic_group
FROM INFORMATION_SCHEMA.COLUMNS c
WHERE c.TABLE_SCHEMA = @schema
  AND c.TABLE_NAME = @view
  AND (
       UPPER(c.COLUMN_NAME) LIKE '%AGENT%'
    OR UPPER(c.COLUMN_NAME) LIKE '%TOX%'
    OR UPPER(c.COLUMN_NAME) LIKE '%VIA%'
    OR UPPER(c.COLUMN_NAME) LIKE '%CIRC%'
    OR UPPER(c.COLUMN_NAME) LIKE '%NOTIF%'
  )
ORDER BY semantic_group, c.COLUMN_NAME;
