-- Equipes de atenção básica CNES — última competência.
WITH ultima_competencia AS (
    SELECT MAX(CONCAT(Ano, RIGHT('00' + CAST(Mes AS varchar(2)), 2))) AS comp
    FROM dbo.CNES_EQUIPESATENCAOBASICA
)
SELECT *
FROM dbo.CNES_EQUIPESATENCAOBASICA
WHERE CONCAT(Ano, RIGHT('00' + CAST(Mes AS varchar(2)), 2)) = (SELECT comp FROM ultima_competencia);
