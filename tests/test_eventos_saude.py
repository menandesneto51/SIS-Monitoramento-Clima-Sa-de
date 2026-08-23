from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class EventosSaudeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "eventos.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
        from sisclima.core.config import APP_CONFIG
        from sisclima.core.db import reset_engine

        APP_CONFIG.database_url = os.environ["DATABASE_URL"]
        reset_engine()
        from sisclima.engines import eventos_saude as ev

        self.ev = ev
        ev.ensure_schema()
        self.mun = {
            "email": "sms@exemplo.mt.gov.br",
            "nome": "Vigilância Municipal",
            "nivel": "municipal",
            "status": "ativo",
            "municipio": "Cuiabá",
            "regional_saude": "Baixada Cuiabana",
            "cod_ibge": "5103403",
        }
        self.ses = {
            "email": "cievs@ses.mt.gov.br",
            "nome": "CIEVS",
            "nivel": "ses",
            "status": "ativo",
        }

    def tearDown(self) -> None:
        from sisclima.core.db import reset_engine

        reset_engine()
        os.environ.pop("DATABASE_URL", None)
        self._tmp.cleanup()

    def test_publico_nao_notifica(self) -> None:
        ok, msg, uid = self.ev.criar_evento(
            user={"email": "a@x.com", "nivel": "publico", "status": "ativo"},
            municipio="Cuiabá",
            tipo="calor",
            descricao="Onda de calor com aumento de atendimentos na UPA centro.",
            data_evento="2026-08-22",
        )
        self.assertFalse(ok)
        self.assertFalse(uid)
        self.assertIn("permissão", msg.lower())

    def test_municipal_cria_e_ses_tria(self) -> None:
        ok, msg, uid = self.ev.criar_evento(
            user=self.mun,
            municipio="Cuiabá",
            tipo="fumaca_ar",
            descricao="Fumaça densa na zona rural com queixa respiratória em escola.",
            data_evento="2026-08-21",
            n_afetados_aprox=12,
        )
        self.assertTrue(ok, msg)
        self.assertTrue(uid)
        df = self.ev.listar_eventos(self.mun)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["situacao"], "rumor")
        ok, msg = self.ev.triar_evento(user=self.ses, uid=uid, situacao="confirmado", nota="Checado com SMS.")
        self.assertTrue(ok, msg)
        df = self.ev.listar_eventos(self.ses)
        self.assertEqual(df.iloc[0]["situacao"], "confirmado")

    def test_municipal_nao_notifica_outro_municipio(self) -> None:
        ok, msg, _uid = self.ev.criar_evento(
            user=self.mun,
            municipio="Várzea Grande",
            tipo="calor",
            descricao="Onda de calor relatada pela vigilância da sede municipal.",
            data_evento="2026-08-22",
        )
        self.assertFalse(ok)
        self.assertIn("próprio município", msg.lower())


if __name__ == "__main__":
    unittest.main()
