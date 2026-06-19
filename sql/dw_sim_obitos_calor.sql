SELECT
    DataObito AS data,
    DataObito AS data_obito,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    AnoObito AS ano,
    MesObito AS mes,
    CodigoMunicipioResidencia AS cod_ibge_residencia,
    MunicipioResidencia AS municipio_residencia,
    CodigoMunicipioOcorrencia AS cod_ibge_ocorrencia,
    MunicipioOcorrencia AS municipio_ocorrencia,
    RegionalResidencia AS regional_residencia,
    RegionalOcorrencia AS regional_ocorrencia,
    Sexo AS sexo,
    Idade AS idade,
    FaixaEtaria AS faixa_etaria,
    RacaCor AS raca_cor,
    LocalOcorrencia AS local_ocorrencia,
    CausaBasica AS cid10_causa_basica,
    CausaCid103C AS cid10_3c,
    CausaCid10Capitulo AS capitulo_cid10,
    LinhaA AS linha_a,
    LinhaB AS linha_b,
    LinhaC AS linha_c,
    LinhaD AS linha_d,
    NumeroObitos AS numero_obitos
FROM dbo.SIM
WHERE TRY_CONVERT(int, AnoObito) >= YEAR(GETDATE()) - 2
  AND (
        CausaBasica LIKE 'T67%'
     OR CausaBasica LIKE 'X30%'
     OR CausaBasica LIKE 'E86%'
     OR CausaBasica LIKE 'I1%'
     OR CausaBasica LIKE 'I2%'
     OR CausaBasica LIKE 'I6%'
     OR CausaBasica LIKE 'J4%'
     OR CausaBasica LIKE 'J8%'
     OR CausaBasica LIKE 'J9%'
     OR CausaBasica LIKE 'N17%'
     OR CausaBasica LIKE 'N18%'
     OR CausaBasica LIKE 'N19%'
  );
