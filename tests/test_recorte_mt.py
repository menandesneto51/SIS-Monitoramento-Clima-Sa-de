from __future__ import annotations

import unittest

from sisclima.core.recorte_mt import alerta_abrange_mato_grosso, extrair_areas_mato_grosso


class RecorteMtTests(unittest.TestCase):
    def test_inclui_mesorregiao_mato_grossense(self) -> None:
        area = "Aviso para as Áreas: Norte Mato-grossense, Centro Goiano"
        self.assertTrue(alerta_abrange_mato_grosso(area))
        self.assertIn("Norte Mato-grossense", extrair_areas_mato_grosso(area))

    def test_exclui_mato_grosso_do_sul(self) -> None:
        area = "Sudoeste de Mato Grosso do Sul, Serrana, Oeste Catarinense"
        self.assertFalse(alerta_abrange_mato_grosso(area))

    def test_exclui_apenas_rs_sc(self) -> None:
        area = "Sudoeste Rio-grandense, Oeste Catarinense, Vale do Itajaí"
        self.assertFalse(alerta_abrange_mato_grosso(area))

    def test_inclui_mato_grosso_estado(self) -> None:
        self.assertTrue(alerta_abrange_mato_grosso("Mato Grosso — região norte"))


if __name__ == "__main__":
    unittest.main()
