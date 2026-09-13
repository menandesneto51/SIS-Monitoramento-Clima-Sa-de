-- CNES equipamentos — competência mais recente, agregado municipal (sem PII).
-- Inclui contagem de nebulização quando o tipo/grupo contém NEBUL.
-- Flag: USE_DW_CNES.
WITH ultima_competencia AS (
    SELECT MAX(CONCAT(Ano, RIGHT('00' + Mes, 2))) AS comp
    FROM dbo.CNES_EQUIPAMENTOS
)
SELECT
    CONCAT(Ano, '-', RIGHT('00' + Mes, 2), '-01') AS data,
    EstabelecimentoMunicipioCodigo AS cod_ibge,
    MAX(EstabelecimentoMunicipioNome) AS municipio,
    SUM(COALESCE(QtdExistente, 0)) AS equipamentos_total,
    SUM(COALESCE(QtdUso, 0)) AS equipamentos_em_uso,
    SUM(
        CASE
            WHEN UPPER(CONCAT(ISNULL(EquipamentoTipo, ''), ' ', ISNULL(EquipamentoGrupo, ''))) LIKE '%NEBUL%'
            THEN COALESCE(QtdExistente, 0)
            ELSE 0
        END
    ) AS equipamentos_nebulizacao,
    COUNT(DISTINCT CodigoCnes) AS estabelecimentos_com_equipamento
FROM dbo.CNES_EQUIPAMENTOS
WHERE CONCAT(Ano, RIGHT('00' + Mes, 2)) = (SELECT comp FROM ultima_competencia)
  AND NULLIF(LTRIM(RTRIM(EstabelecimentoMunicipioCodigo)), '') IS NOT NULL
GROUP BY
    Ano,
    Mes,
    EstabelecimentoMunicipioCodigo;
