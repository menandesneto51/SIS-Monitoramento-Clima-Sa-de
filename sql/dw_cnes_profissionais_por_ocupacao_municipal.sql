-- CNES profissionais por ocupação (CBO) — competência mais recente, agregado municipal.
-- SEM nome, CNS, CPF, registro profissional ou qualquer identificador pessoal.
-- Flag: USE_DW_CNES.
WITH ultima_competencia AS (
    SELECT MAX(CONCAT(Ano, RIGHT('00' + Mes, 2))) AS comp
    FROM dbo.CNES_PROFISSIONAIS
)
SELECT
    CONCAT(Ano, '-', RIGHT('00' + Mes, 2), '-01') AS data,
    EstabelecimentoMunicipioCodigo AS cod_ibge,
    MAX(EstabelecimentoMunicipioNome) AS municipio,
    ISNULL(NULLIF(LTRIM(RTRIM(OcupacaoCodigo)), ''), 'SEM_CBO') AS ocupacao_codigo,
    SUM(COALESCE(QtdProfissionais, 1)) AS profissionais_qtd,
    COUNT(DISTINCT CodigoCnes) AS estabelecimentos_com_ocupacao,
    SUM(COALESCE(HoraAmbulatorial, 0) + COALESCE(HoraHospitalar, 0) + COALESCE(HoraOutras, 0)) AS horas_ocupacao
FROM dbo.CNES_PROFISSIONAIS
WHERE CONCAT(Ano, RIGHT('00' + Mes, 2)) = (SELECT comp FROM ultima_competencia)
  AND NULLIF(LTRIM(RTRIM(EstabelecimentoMunicipioCodigo)), '') IS NOT NULL
GROUP BY
    Ano,
    Mes,
    EstabelecimentoMunicipioCodigo,
    ISNULL(NULLIF(LTRIM(RTRIM(OcupacaoCodigo)), ''), 'SEM_CBO');
