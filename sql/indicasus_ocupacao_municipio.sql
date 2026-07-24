-- Ocupação em tempo quase real — IndicaSUS / BdSES (usuário Roney).
-- ATENÇÃO: ajuste a view/tabela abaixo ao schema real do BdSES após
--   python atualizar_ocupacao_indicasus.py --descobrir
--
-- Saída esperada (colunas mínimas):
--   cod_ibge, municipio, leitos_existentes, leitos_ocupados, ocupacao_pct
--
-- Template genérico (falha de forma controlada se a view não existir):
SELECT
    COALESCE(CodIBGE, CodigoIBGE, CodMunicipio, IBGE) AS cod_ibge,
    COALESCE(Municipio, NomeMunicipio, Localidade) AS municipio,
    COALESCE(LocalidadeId, IdLocalidade) AS LocalidadeId,
    COALESCE(Unidades, QtdUnidades, 1) AS unidades,
    COALESCE(UltimaMovimentacao, DataAtualizacao, GETDATE()) AS ultima_movimentacao,
    COALESCE(LeitosExistentes, LeitosTotal, Capacidade) AS leitos_existentes,
    COALESCE(LeitosSUS, LeitosExistentes, LeitosTotal) AS leitos_sus,
    COALESCE(LeitosOcupados, Ocupados) AS leitos_ocupados,
    COALESCE(LeitosBloqueadosCadastro, 0) AS leitos_bloqueados_cadastro,
    COALESCE(LeitosBloqueadosMovimento, 0) AS leitos_bloqueados_movimento,
    COALESCE(LeitosHigienizacao, 0) AS leitos_higienizacao,
    COALESCE(LeitosReservados, 0) AS leitos_reservados,
    COALESCE(
        TaxaOcupacao,
        CASE
            WHEN COALESCE(LeitosExistentes, LeitosTotal, Capacidade, 0) > 0
            THEN 100.0 * COALESCE(LeitosOcupados, Ocupados, 0)
                 / COALESCE(LeitosExistentes, LeitosTotal, Capacidade)
            ELSE NULL
        END
    ) AS ocupacao_pct
FROM dbo.VW_OCUPACAO_LEITOS_MUNICIPIO;
