-- SINAN — agravos extras com vínculo climático (estiagem, calor, fauna, respiratório).
SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    'HANTAVIROSE' AS fonte_sinan,
    'Hantavirose' AS agravo,
    NumeroNotificacao AS numero_notificacao,
    NumeroCasos AS numero_casos
FROM dbo.VW_SINAN_HANTAVIROSE
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1

UNION ALL

SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    'ANIMAIS_PECONHENTOS' AS fonte_sinan,
    'Animais Peconhentos' AS agravo,
    NumeroNotificacao AS numero_notificacao,
    NumeroCasos AS numero_casos
FROM dbo.VW_SINAN_ANIMAISPECONHENTOS
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1

UNION ALL

SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    'SRAG_SINAN' AS fonte_sinan,
    'Sindrome Respiratoria Aguda Grave' AS agravo,
    NumeroNotificacao AS numero_notificacao,
    NumeroCasos AS numero_casos
FROM dbo.VW_SINAN_SINDROMERESPIRATORIAAGUDAGRAVE
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1

UNION ALL

SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    'LEISHMANIOSE_VISCERAL' AS fonte_sinan,
    'Leishmaniose Visceral' AS agravo,
    NumeroNotificacao AS numero_notificacao,
    NumeroCasos AS numero_casos
FROM dbo.VW_SINAN_LEISHMANIOSEVISCERAL
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1

UNION ALL

SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    'FEBRE_MACULOSA' AS fonte_sinan,
    'Febre Maculosa' AS agravo,
    NumeroNotificacao AS numero_notificacao,
    NumeroCasos AS numero_casos
FROM dbo.VW_SINAN_FEBREMACULOSA
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1;
