from __future__ import annotations

import unittest
import unittest.mock

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

    def test_lat_lon_trocados_sao_corrigidos_e_invalidos_excluidos(self) -> None:
        cnes = pd.DataFrame(
            {
                "cnes": ["ok", "swap", "fora"],
                "fonte_coord": ["opendata_cnes"] * 3,
                "lat": [-15.70, -56.20, 0.0],
                "lon": [-56.20, -15.70, 0.0],
            }
        )
        off = unidades_oficiais(cnes)
        self.assertEqual(set(off["cnes"].astype(str)), {"ok", "swap"})
        self.assertTrue(off["lat"].between(-18.2, -7.2).all())
        self.assertTrue(off["lon"].between(-61.8, -50.0).all())

    def test_p90_extremo_exige_validacao_e_sai_do_ranking(self) -> None:
        cob = pd.DataFrame(
            {
                "municipio": ["Apiacás"] * 3 + ["Cuiabá"] * 3,
                "nome": list("abcdef"),
                "nivel": ["vermelha"] * 6,
                "nivel_predicao_7d": ["roxa"] * 6,
                "km_aps": [1000.0, 1050.0, 1100.0, 40.0, 50.0, 60.0],
                "km_hospital": [80.0] * 6,
                "longe_rede": [True] * 6,
            }
        )
        with unittest.mock.patch(
            "sisclima.engines.cobertura_territorio.load_cobertura",
            return_value=cob,
        ):
            from sisclima.engines.boletim_el_nino.territorios import _quadro_cobertura_rede

            tabela, _nota, recs, qa = _quadro_cobertura_rede()
        self.assertIn("Cuiabá", tabela)
        self.assertNotIn("Apiacás", tabela)
        self.assertIn("Distância em validação", recs)
        self.assertGreaterEqual(int(qa.get("n_route_validation_required") or 0), 1)
        self.assertTrue(any("Apiacás" in x for x in (qa.get("rotas_validacao") or [])))


if __name__ == "__main__":
    unittest.main()
