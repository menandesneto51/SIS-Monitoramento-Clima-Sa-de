-- Snapshot agregado do cadastro individual (fato). Sem nome/CPF/CNS.
-- Um cidadão (co_fat_cidadao_pec) conta no máximo uma vez por município.
-- Idoso: faixa etária com 60+ na dimensão (não usa dt_nascimento).

WITH mun AS (
    SELECT
        co_seq_dim_municipio,
        no_municipio,
        regexp_replace(COALESCE(co_ibge::text, ''), '[^0-9]', '', 'g') AS ibge
    FROM tb_dim_municipio
    WHERE regexp_replace(COALESCE(co_ibge::text, ''), '[^0-9]', '', 'g') LIKE '51%'
)
SELECT
    m.ibge AS cod_ibge,
    MAX(m.no_municipio) AS municipio,
    COUNT(DISTINCT c.co_fat_cidadao_pec) AS cadastros,
    COUNT(DISTINCT CASE WHEN COALESCE(c.st_gestante, 0) = 1 THEN c.co_fat_cidadao_pec END) AS gestante,
    COUNT(DISTINCT CASE WHEN COALESCE(c.st_doenca_respira_asma, 0) = 1 THEN c.co_fat_cidadao_pec END) AS asma,
    COUNT(DISTINCT CASE WHEN COALESCE(c.st_doenca_respira_dpoc_enfisem, 0) = 1 THEN c.co_fat_cidadao_pec END) AS dpoc,
    COUNT(DISTINCT CASE WHEN COALESCE(c.st_doenca_respiratoria, 0) = 1 THEN c.co_fat_cidadao_pec END) AS doenca_respiratoria,
    COUNT(DISTINCT CASE WHEN COALESCE(c.st_fumante, 0) = 1 THEN c.co_fat_cidadao_pec END) AS fumante,
    COUNT(DISTINCT CASE WHEN COALESCE(c.st_hipertensao_arterial, 0) = 1 THEN c.co_fat_cidadao_pec END) AS hipertensao,
    COUNT(DISTINCT CASE WHEN COALESCE(c.st_diabete, 0) = 1 THEN c.co_fat_cidadao_pec END) AS diabetes,
    COUNT(DISTINCT CASE WHEN COALESCE(c.st_acamado, 0) = 1 THEN c.co_fat_cidadao_pec END) AS acamado,
    COUNT(DISTINCT CASE WHEN COALESCE(c.st_domiciliado, 0) = 1 THEN c.co_fat_cidadao_pec END) AS domiciliado,
    COUNT(DISTINCT CASE WHEN COALESCE(c.st_comunidade_tradicional, 0) = 1 THEN c.co_fat_cidadao_pec END) AS comunidade_tradicional,
    COUNT(DISTINCT CASE WHEN COALESCE(c.st_deficiencia, 0) = 1 THEN c.co_fat_cidadao_pec END) AS deficiencia,
    COUNT(DISTINCT CASE
        WHEN COALESCE(fe.ds_faixa_etaria, '') ~* '(^|[^0-9])(6[0-9]|[7-9][0-9]|1[01][0-9])'
        THEN c.co_fat_cidadao_pec
    END) AS idoso_60mais
FROM tb_fat_cad_individual c
INNER JOIN mun m ON m.co_seq_dim_municipio = c.co_dim_municipio
LEFT JOIN tb_dim_faixa_etaria fe
    ON fe.co_seq_dim_faixa_etaria = c.co_dim_faixa_etaria
GROUP BY m.ibge
ORDER BY m.ibge
;