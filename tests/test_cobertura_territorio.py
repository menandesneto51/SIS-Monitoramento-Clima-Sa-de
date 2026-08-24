from __future__ import annotations

import unittest

import pandas as pd

from sisclima.engines.cobertura_territorio import calcular_cobertura, haversine_km, unidades_oficiais
from sisclima.ingestion.vigibarragens import CATEGORIA_ALDEIA, CATEGORIA_QUILOMBO


class CoberturaTerritorioTests(unittest.TestCase):
    def test_haversine_cuiaba_varzea(self) -> None:
        # Cuiabá x Várzea Grande ~ 10 km (ordem de grandeza)
        km = float(haversine_km([-15.6014], [-56.0979], [-15.6467], [-56.1325])[0, 0])
        self.assertGreater(km, 4)
        self.assertLess(km, 20)

    def test_ignora_centroide_municipal(self) -> None:
        terr = pd.DataFrame(
            {
                "nome": ["Aldeia Teste"],
                "categoria": [CATEGORIA_ALDEIA],
                "municipio": ["Cuiabá"],
                "cod_ibge": ["5103403"],
                "lat": [-15.6014],
                "lon": [-56.0979],
            }
        )
        cnes = pd.DataFrame(
            {
                "cnes": ["1111111", "2222222"],
                "nome_unidade": ["UBS centroide", "UBS oficial"],
                "tipo_unidade": ["UBS", "UBS"],
                "grupo_tipo": ["aps", "aps"],
                "fonte_coord": ["centroid_municipio", "opendata_cnes"],
                "lat": [-15.6015, -15.70],
                "lon": [-56.0980, -56.20],
            }
        )
        cob = calcular_cobertura(terr, cnes, aps_km=30, hospital_km=50, usar_trajeto=False)
        self.assertEqual(len(cob), 1)
        self.assertEqual(str(cob.iloc[0]["cnes_aps"]), "2222222")
        self.assertEqual(str(cob.iloc[0]["nome_aps"]), "UBS oficial")
        self.assertEqual(str(cob.iloc[0]["metodo_aps"]), "linha_reta")

    def test_flag_longe_aps(self) -> None:
        terr = pd.DataFrame(
            {
                "nome": ["Comunidade X"],
                "categoria": [CATEGORIA_QUILOMBO],
                "municipio": ["Cuiabá"],
                "cod_ibge": ["5103403"],
                "lat": [-15.60],
                "lon": [-56.10],
            }
        )
        cnes = pd.DataFrame(
            {
                "cnes": ["3333333"],
                "nome_unidade": ["UBS longe"],
                "tipo_unidade": ["UBS"],
                "grupo_tipo": ["aps"],
                "fonte_coord": ["dw_cnes"],
                "lat": [-15.90],
                "lon": [-56.50],
            }
        )
        cob = calcular_cobertura(terr, cnes, aps_km=30, hospital_km=50, usar_trajeto=False)
        km = float(cob.iloc[0]["km_aps"])
        self.assertGreater(km, 30)
        self.assertTrue(bool(cob.iloc[0]["longe_aps"]))

    def test_trajeto_pode_trocar_o_mais_proximo_em_linha_reta(self) -> None:
        terr = pd.DataFrame(
            {
                "nome": ["Aldeia Rota"],
                "categoria": [CATEGORIA_ALDEIA],
                "municipio": ["Cuiabá"],
                "cod_ibge": ["5103403"],
                "lat": [-15.60],
                "lon": [-56.10],
            }
        )
        cnes = pd.DataFrame(
            {
                "cnes": ["1111111", "2222222"],
                "nome_unidade": ["UBS reta", "UBS via"],
                "tipo_unidade": ["UBS", "UBS"],
                "grupo_tipo": ["aps", "aps"],
                "fonte_coord": ["opendata_cnes", "opendata_cnes"],
                "lat": [-15.61, -15.80],
                "lon": [-56.11, -56.30],
            }
        )

        def roteador(_la, _lo, destinos):
            # Mais perto em linha reta: 80 km / 90 min; a outra: 12 km / 18 min.
            return [(80.0, 90.0) if i == 0 else (12.0, 18.0) for i, _d in enumerate(destinos)]

        cob = calcular_cobertura(
            terr, cnes, aps_km=30, hospital_km=50, usar_trajeto=True, roteador=roteador, candidatos_k=2
        )
        self.assertEqual(str(cob.iloc[0]["cnes_aps"]), "2222222")
        self.assertEqual(float(cob.iloc[0]["km_aps"]), 12.0)
        self.assertEqual(float(cob.iloc[0]["min_aps"]), 18.0)
        self.assertEqual(str(cob.iloc[0]["metodo_aps"]), "trajeto")
        self.assertFalse(bool(cob.iloc[0]["longe_aps"]))

    def test_unidades_oficiais_exclui_centroide(self) -> None:
        cnes = pd.DataFrame(
            {
                "cnes": ["1", "2"],
                "fonte_coord": ["centroid_municipio", "opendata_cnes"],
                "lat": [-15.6, -15.7],
                "lon": [-56.1, -56.2],
            }
        )
        off = unidades_oficiais(cnes)
        self.assertEqual(len(off), 1)
        self.assertEqual(str(off.iloc[0]["cnes"]), "2")
        self.assertEqual(str(off.iloc[0]["fonte_coord"]), "opendata_cnes")


if __name__ == "__main__":
    unittest.main()
