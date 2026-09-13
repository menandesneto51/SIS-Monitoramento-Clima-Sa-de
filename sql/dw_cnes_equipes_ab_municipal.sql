-- CNES equipes de atenção básica — competência mais recente, agregado municipal.
-- SEM nomes de profissionais — só contagens de equipes / CNES.
-- Flag: USE_DW_CNES.
WITH ultima_competencia AS (
    SELECT MAX(CONCAT(Ano, RIGHT('00' + Mes, 2))) AS comp
    FROM dbo.CNES_EQUIPESATENCAOBASICA
)
SELECT
    CONCAT(Ano, '-', RIGHT('00' + Mes, 2), '-01') AS data,
    EstabelecimentoMunicipioCodigo AS cod_ibge,
    MAX(EstabelecimentoMunicipioNome) AS municipio,
    SUM(COALESCE(QtdEquipes, 1)) AS cnes_equipes_ab_qtd,
    COUNT(DISTINCT CodigoCnes) AS cnes_estabelecimentos_com_eab,
    SUM(
        CASE
            WHEN EquipeAtendePopulacaoAssistidaIndigena IN ('1', 'Sim', 'SIM', 'S')
              OR EquipeAtendePopulacaoAssistidaQuilombolas IN ('1', 'Sim', 'SIM', 'S')
            THEN COALESCE(QtdEquipes, 1)
            ELSE 0
        END
    ) AS cnes_equipes_ab_povos_tradicionais
FROM dbo.CNES_EQUIPESATENCAOBASICA
WHERE CONCAT(Ano, RIGHT('00' + Mes, 2)) = (SELECT comp FROM ultima_competencia)
  AND NULLIF(LTRIM(RTRIM(EstabelecimentoMunicipioCodigo)), '') IS NOT NULL
GROUP BY
    Ano,
    Mes,
    EstabelecimentoMunicipioCodigo;
