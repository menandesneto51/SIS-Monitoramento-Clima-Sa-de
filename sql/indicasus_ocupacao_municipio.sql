-- Ocupação IndicaSUS / BdSES (usuário Roney).
-- 1) Rode: python atualizar_ocupacao_indicasus.py --descobrir
-- 2) Substitua dbo.VW_OCUPACAO_LEITOS_MUNICIPIO pelo nome real listado.
-- 3) Ajuste aliases de colunas conforme o schema.
SELECT TOP 50000 *
FROM dbo.VW_OCUPACAO_LEITOS_MUNICIPIO;
