# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from sisclima.engines.cnes_rede_mapas import (
    assert_sem_pii,
    grupo_ocupacao_cbo,
    prepare_equipamentos_por_tipo,
    prepare_profissionais_por_ocupacao,
    pivot_equipamentos_municipio,
    pivot_profissionais_municipio,
)


class CnesRedeMapasTests(unittest.TestCase):
    def test_grupo_ocupacao(self) -> None:
        self.assertEqual(grupo_ocupacao_cbo("225125"), "Médicos")
        self.assertEqual(grupo_ocupacao_cbo("515105"), "ACS / agentes comunitários")
        self.assertEqual(grupo_ocupacao_cbo(""), "Sem CBO / não informado")

    def test_equipamentos_nebul_e_total(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "cod_ibge": "5103403",
                    "municipio": "Cuiabá",
                    "equipamento_grupo": "RESPIRATORIO",
                    "equipamento_tipo": "NEBULIZADOR",
                    "equipamentos_existentes": 4,
                    "equipamentos_em_uso": 3,
                    "estabelecimentos": 2,
                },
                {
                    "cod_ibge": "5103403",
                    "municipio": "Cuiabá",
                    "equipamento_grupo": "IMAGEM",
                    "equipamento_tipo": "RAIO X",
                    "equipamentos_existentes": 1,
                    "equipamentos_em_uso": 1,
                    "estabelecimentos": 1,
                },
            ]
        )
        prep = prepare_equipamentos_por_tipo(df)
        self.assertTrue(bool(prep.loc[0, "flag_nebulizacao"]))
        piv = pivot_equipamentos_municipio(prep)
        self.assertEqual(int(piv.iloc[0]["equipamentos_total"]), 5)
        self.assertEqual(int(piv.iloc[0]["equipamentos_nebulizacao"]), 4)

    def test_profissionais_sem_pii_e_filtro(self) -> None:
        df = pd.DataFrame(
            [
                {"cod_ibge": "5103403", "ocupacao_codigo": "225125", "profissionais_qtd": 10},
                {"cod_ibge": "5103403", "ocupacao_codigo": "515105", "profissionais_qtd": 30},
                {"cod_ibge": "5107925", "ocupacao_codigo": "225125", "profissionais_qtd": 5},
            ]
        )
        prep = prepare_profissionais_por_ocupacao(df)
        assert_sem_pii(prep)
        self.assertIn("grupo_ocupacao", prep.columns)
        med = pivot_profissionais_municipio(prep, grupo="Médicos")
        self.assertEqual(int(med.loc[med["cod_ibge"] == "5103403", "profissionais_qtd"].iloc[0]), 10)
        with self.assertRaises(ValueError):
            assert_sem_pii(pd.DataFrame([{"nome_profissional": "x", "cod_ibge": "1"}]))


if __name__ == "__main__":
    unittest.main()
