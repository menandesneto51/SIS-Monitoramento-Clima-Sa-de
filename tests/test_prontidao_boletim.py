from __future__ import annotations

import unittest

import pandas as pd

from sisclima.engines.boletim_el_nino.prontidao import compute_prontidao


class ProntidaoV2Tests(unittest.TestCase):
    def test_nao_satura_todas_as_linhas_em_100(self) -> None:
        df = pd.DataFrame(
            [
                {"municipio": "A", "nivel": "roxa", "indice_prioridade_global": 52},
                {"municipio": "B", "nivel": "roxa", "indice_prioridade_global": 61},
                {"municipio": "C", "nivel": "amarela", "indice_prioridade_global": 20},
            ]
        )
        out = compute_prontidao(df)
        self.assertTrue(out["validado"])
        vals = [t["prontidao"] for t in out["top"]]
        self.assertGreater(len(vals), 1)
        self.assertLess(max(vals) - min(vals), 80)
        self.assertTrue(any(v < 99.5 for v in vals))
        self.assertIn("Índice", out["tabela_md"])
        self.assertNotIn("prioridade global", out["tabela_md"].lower())
        self.assertNotIn("| 100 | 100 | 100 |", out["tabela_md"].replace(",0", ""))
