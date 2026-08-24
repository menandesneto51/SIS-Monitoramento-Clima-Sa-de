from __future__ import annotations

import unittest

import pandas as pd

from sisclima.ingestion.cnes_geo import (
    coords_validas_mt,
    grupo_tipo,
    normalize_opendata_rows,
)


class CnesGeoTests(unittest.TestCase):
    def test_grupo_tipo_hospital_e_ubs(self) -> None:
        self.assertEqual(grupo_tipo("Hospital Geral"), "hospital")
        self.assertEqual(grupo_tipo("Centro de Saúde / Unidade Básica"), "aps")
        self.assertEqual(grupo_tipo("UPA 24h"), "urgencia")

    def test_normaliza_api_e_filtra_mt(self) -> None:
        rows = [
            {
                "codigo_cnes": "2121674",
                "nome_fantasia": "HOSPITAL SANTA ROSA",
                "descricao_tipo_unidade": "Hospital Geral",
                "codigo_municipio": "5103403",
                "nome_municipio": "Cuiabá",
                "latitude": -15.601,
                "longitude": -56.097,
            },
            {
                "codigo_cnes": "9999999",
                "nome_fantasia": "Fora do estado",
                "codigo_municipio": "3550308",
                "latitude": -23.55,
                "longitude": -46.63,
            },
        ]
        df = normalize_opendata_rows(rows)
        self.assertEqual(len(df), 1)
        self.assertEqual(str(df.iloc[0]["cnes"]).zfill(7), "2121674")
        self.assertAlmostEqual(float(df.iloc[0]["lat"]), -15.601, places=3)
        self.assertEqual(df.iloc[0]["grupo_tipo"], "hospital")
        self.assertEqual(df.iloc[0]["fonte_coord"], "opendata_cnes")

    def test_corrige_lat_lon_invertidos(self) -> None:
        rows = [
            {
                "cnes": "1234567",
                "nome_fantasia": "UBS Centro",
                "descricao_tipo_unidade": "Centro de Saúde",
                "codigo_municipio": "5103403",
                "latitude": -56.09,
                "longitude": -15.60,
            }
        ]
        df = normalize_opendata_rows(rows)
        self.assertEqual(len(df), 1)
        self.assertTrue(coords_validas_mt(df["lat"], df["lon"]).iloc[0])
        self.assertLess(float(df.iloc[0]["lat"]), -7)
        self.assertGreater(float(df.iloc[0]["lat"]), -18.2)

    def test_descarta_coordenada_nula(self) -> None:
        rows = [
            {
                "cnes": "1111111",
                "nome_fantasia": "Sem ponto",
                "codigo_municipio": "5103403",
                "latitude": 0,
                "longitude": 0,
            }
        ]
        df = normalize_opendata_rows(rows)
        self.assertTrue(pd.isna(df.iloc[0]["lat"]) or pd.isna(df.iloc[0]["lon"]))
        self.assertEqual(df.iloc[0]["fonte_coord"], "")


if __name__ == "__main__":
    unittest.main()
