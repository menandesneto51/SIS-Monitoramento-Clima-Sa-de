-- Agregado municipal APS x clima (Centralizador esus2). Somente leitura.
-- Placeholders {{CID_*}} / {{SIGTAP_*}} substituídos em esus_aps_clima.py.
-- Filtro temporal: dt_inicial_atendimento (não usar co_dim_tempo sozinho).

WITH mun AS (
    SELECT
        co_seq_dim_municipio,
        no_municipio,
        regexp_replace(COALESCE(co_ibge::text, ''), '[^0-9]', '', 'g') AS ibge
    FROM tb_dim_municipio
    WHERE regexp_replace(COALESCE(co_ibge::text, ''), '[^0-9]', '', 'g') LIKE '51%'
),
atd AS (
    SELECT
        m.ibge AS cod_ibge,
        MAX(m.no_municipio) AS municipio,
        COUNT(*) FILTER (WHERE a.dt_inicial_atendimento >= :dt_ini_7d) AS atendimentos_7d,
        COUNT(*) AS atendimentos_28d,
        COUNT(*) FILTER (
            WHERE a.dt_inicial_atendimento >= :dt_ini_7d
              AND COALESCE(a.ds_filtro_cids, '') ~* '{{CID_RESP}}'
        ) AS resp_cid_7d,
        COUNT(*) FILTER (
            WHERE COALESCE(a.ds_filtro_cids, '') ~* '{{CID_RESP}}'
        ) AS resp_cid_28d,
        COUNT(*) FILTER (
            WHERE a.dt_inicial_atendimento >= :dt_ini_7d
              AND COALESCE(a.ds_filtro_ciaps, '') ~* '{{CIAP_RESP}}'
        ) AS resp_ciap_7d,
        COUNT(*) FILTER (
            WHERE a.dt_inicial_atendimento >= :dt_ini_7d
              AND COALESCE(a.ds_filtro_cids, '') ~* '{{CID_CALOR}}'
        ) AS calor_cid_7d,
        COUNT(*) FILTER (
            WHERE COALESCE(a.ds_filtro_cids, '') ~* '{{CID_CALOR}}'
        ) AS calor_cid_28d,
        COUNT(*) FILTER (
            WHERE a.dt_inicial_atendimento >= :dt_ini_7d
              AND COALESCE(a.ds_filtro_cids, '') ~* '{{CID_DDA}}'
        ) AS dda_cid_7d,
        COUNT(*) FILTER (
            WHERE COALESCE(a.ds_filtro_cids, '') ~* '{{CID_DDA}}'
        ) AS dda_cid_28d,
        COUNT(*) FILTER (
            WHERE a.dt_inicial_atendimento >= :dt_ini_7d
              AND COALESCE(a.st_encaminhamento_urgencia, 0) = 1
        ) AS encaminhamento_urgencia_7d,
        COUNT(*) FILTER (
            WHERE a.dt_inicial_atendimento >= :dt_ini_7d
              AND COALESCE(a.st_encaminhamento_intern_hospi, 0) = 1
        ) AS encaminhamento_internacao_7d
    FROM tb_fat_atendimento_individual a
    INNER JOIN mun m ON m.co_seq_dim_municipio = a.co_dim_municipio
    WHERE a.dt_inicial_atendimento >= :dt_ini_28d
      AND a.dt_inicial_atendimento < :dt_fim
      -- Descarta datas futuras inválidas no cubo (ex.: 2041).
      AND a.dt_inicial_atendimento < (NOW() + INTERVAL '1 day')
    GROUP BY m.ibge
),
neb AS (
    SELECT
        m.ibge AS cod_ibge,
        COUNT(*) FILTER (WHERE p.dt_inicial_atendimento >= :dt_ini_7d) AS nebulizacao_7d,
        COUNT(*) AS nebulizacao_28d
    FROM tb_fat_atd_ind_procedimentos p
    INNER JOIN mun m ON m.co_seq_dim_municipio = p.co_dim_municipio
    INNER JOIN tb_dim_procedimento d
        ON d.co_seq_dim_procedimento IN (
            p.co_dim_procedimento_avaliado,
            p.co_dim_procedimento_solicitado
        )
    WHERE p.dt_inicial_atendimento >= :dt_ini_28d
      AND p.dt_inicial_atendimento < :dt_fim
      AND p.dt_inicial_atendimento < (NOW() + INTERVAL '1 day')
      AND regexp_replace(COALESCE(d.co_proced, ''), '[^0-9]', '', 'g') IN (
          '{{SIGTAP_A}}',
          '{{SIGTAP_B}}'
      )
    GROUP BY m.ibge
)
SELECT
    a.cod_ibge,
    a.municipio,
    a.atendimentos_7d,
    a.atendimentos_28d,
    a.resp_cid_7d,
    a.resp_cid_28d,
    a.resp_ciap_7d,
    a.calor_cid_7d,
    a.calor_cid_28d,
    a.dda_cid_7d,
    a.dda_cid_28d,
    COALESCE(n.nebulizacao_7d, 0) AS nebulizacao_7d,
    COALESCE(n.nebulizacao_28d, 0) AS nebulizacao_28d,
    a.encaminhamento_urgencia_7d,
    a.encaminhamento_internacao_7d
FROM atd a
LEFT JOIN neb n ON n.cod_ibge = a.cod_ibge
ORDER BY a.cod_ibge
;