WITH ultima_competencia AS (
    SELECT MAX(CONCAT(Ano, RIGHT('00' + Mes, 2))) AS comp
    FROM dbo.CNES_ESTABELECIMENTOS
)
SELECT
    CONCAT(Ano, '-', RIGHT('00' + Mes, 2), '-01') AS data,
    EstabelecimentoMunicipioCodigo AS cod_ibge,
    EstabelecimentoMunicipioNome AS municipio,
    CodigoCnes AS cnes,
    EstabelecimentoNome AS nome_unidade,
    TipoUnidade AS tipo_unidade,
    Natureza AS natureza,
    EsferaAdministrativa AS esfera_administrativa,
    TipoGestao AS tipo_gestao,
    VinculoSUS AS vinculo_sus,
    EstabelecimentoRegional AS regional_saude,
    EstabelecimentoMacrorregiao AS macroregiao_saude,
    SituacaoUnidade AS situacao_unidade,
    QtdEstabelecimento AS qtd_estabelecimento
FROM dbo.CNES_ESTABELECIMENTOS
WHERE CONCAT(Ano, RIGHT('00' + Mes, 2)) = (SELECT comp FROM ultima_competencia);
