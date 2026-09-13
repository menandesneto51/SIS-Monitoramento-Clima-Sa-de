-- CNES profissionais — competência mais recente, agregado municipal.
-- SEM nome, CNS, CPF ou registro — só contagens.
-- Flag: USE_DW_CNES.
WITH ultima_competencia AS (
    SELECT MAX(CONCAT(Ano, RIGHT('00' + Mes, 2))) AS comp
    FROM dbo.CNES_PROFISSIONAIS
)
SELECT
    CONCAT(Ano, '-', RIGHT('00' + Mes, 2), '-01') AS data,
    EstabelecimentoMunicipioCodigo AS cod_ibge,
    MAX(EstabelecimentoMunicipioNome) AS municipio,
    SUM(COALESCE(QtdProfissionais, 1)) AS cnes_profissionais_qtd,
    COUNT(DISTINCT CodigoCnes) AS cnes_estabelecimentos_com_profissional,
    SUM(COALESCE(HoraAmbulatorial, 0) + COALESCE(HoraHospitalar, 0) + COALESCE(HoraOutras, 0)) AS cnes_horas_profissionais
FROM dbo.CNES_PROFISSIONAIS
WHERE CONCAT(Ano, RIGHT('00' + Mes, 2)) = (SELECT comp FROM ultima_competencia)
  AND NULLIF(LTRIM(RTRIM(EstabelecimentoMunicipioCodigo)), '') IS NOT NULL
GROUP BY
    Ano,
    Mes,
    EstabelecimentoMunicipioCodigo;
