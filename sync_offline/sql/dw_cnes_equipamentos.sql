-- Equipamentos CNES — última competência (padrão colunas SES/MT DW).
WITH ultima_competencia AS (
    SELECT MAX(CONCAT(Ano, RIGHT('00' + CAST(Mes AS varchar(2)), 2))) AS comp
    FROM dbo.CNES_EQUIPAMENTOS
)
SELECT *
FROM dbo.CNES_EQUIPAMENTOS
WHERE CONCAT(Ano, RIGHT('00' + CAST(Mes AS varchar(2)), 2)) = (SELECT comp FROM ultima_competencia);
