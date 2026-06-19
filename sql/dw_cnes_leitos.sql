WITH ultima_competencia AS (
    SELECT MAX(CONCAT(Ano, RIGHT('00' + Mes, 2))) AS comp
    FROM dbo.CNES_LEITOS
)
SELECT
    CONCAT(Ano, '-', RIGHT('00' + Mes, 2), '-01') AS data,
    EstabelecimentoMunicipioCodigo AS cod_ibge,
    EstabelecimentoMunicipioNome AS municipio,
    CodigoCnes AS cnes,
    EstabelecimentoNome AS unidade,
    TipoUnidade AS tipo_unidade,
    TipoLeito AS tipo_leito,
    Especialidade AS especialidade,
    Especialidade2 AS especialidade_2,
    QtdExistente AS leitos_existentes,
    QtdSUS AS leitos_sus
FROM dbo.CNES_LEITOS
WHERE CONCAT(Ano, RIGHT('00' + Mes, 2)) = (SELECT comp FROM ultima_competencia);
