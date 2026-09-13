-- CNES serviço/classificação — competência mais recente, agregado municipal.
-- Flag: USE_DW_CNES.
WITH ultima_competencia AS (
    SELECT MAX(CONCAT(Ano, RIGHT('00' + Mes, 2))) AS comp
    FROM dbo.CNES_SERVICOCLASSIFICACAO
)
SELECT
    CONCAT(Ano, '-', RIGHT('00' + Mes, 2), '-01') AS data,
    EstabelecimentoMunicipioCodigo AS cod_ibge,
    MAX(EstabelecimentoMunicipioNome) AS municipio,
    SUM(COALESCE(QtdServicoClassificacao, 1)) AS cnes_servicos_classificacao_qtd,
    COUNT(DISTINCT CodigoCNES) AS cnes_estabelecimentos_com_servico,
    SUM(
        CASE
            WHEN AmbulatorialSus IN ('1', 'Sim', 'SIM', 'S', 'X')
              OR HospitalarSus IN ('1', 'Sim', 'SIM', 'S', 'X')
            THEN COALESCE(QtdServicoClassificacao, 1)
            ELSE 0
        END
    ) AS cnes_servicos_sus_qtd
FROM dbo.CNES_SERVICOCLASSIFICACAO
WHERE CONCAT(Ano, RIGHT('00' + Mes, 2)) = (SELECT comp FROM ultima_competencia)
  AND NULLIF(LTRIM(RTRIM(EstabelecimentoMunicipioCodigo)), '') IS NOT NULL
GROUP BY
    Ano,
    Mes,
    EstabelecimentoMunicipioCodigo;
