from __future__ import annotations

import unittest
from datetime import date

from sisclima.engines.boletim_el_nino.referencias import cite, format_referencias_bibliograficas


class BoletimReferenciasTests(unittest.TestCase):
    def test_cite_retorna_formato_abnt_curto(self) -> None:
        self.assertIn("INMET", cite("inmet_alertas"))
        self.assertTrue(cite("inmet_alertas").startswith("("))

    def test_referencias_completas(self) -> None:
        refs = format_referencias_bibliograficas(ref_ids=["inmet_alertas", "cemaden_alertas"], acesso_em=date(2026, 8, 19))
        self.assertEqual(len(refs), 2)
        self.assertIn("INSTITUTO NACIONAL DE METEOROLOGIA", refs[0])
        self.assertIn("19 ago. 2026", refs[0])


if __name__ == "__main__":
    unittest.main()
