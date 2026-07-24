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
    TipoLeito AS tipo_leito,
    Especialidade AS especialidade,
    QtdExistente AS leitos_existentes,
    QtdSUS AS leitos_sus,
    CAST(NULL AS int) AS leitos_ocupados,
    CAST(NULL AS int) AS leitos_livres,
    CAST(NULL AS decimal(10,2)) AS taxa_ocupacao,
    'CNES_CAPACIDADE_INSTALADA' AS fonte
FROM dbo.CNES_LEITOS
WHERE CONCAT(Ano, RIGHT('00' + Mes, 2)) = (SELECT comp FROM ultima_competencia);
