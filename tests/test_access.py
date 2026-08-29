from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class AccessCadastroTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "access.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
        from sisclima.core.db import reset_engine

        reset_engine()
        from sisclima.auth import access as acc

        self.acc = acc
        acc.ensure_schema()

    def tearDown(self) -> None:
        from sisclima.core.db import reset_engine

        reset_engine()
        os.environ.pop("DATABASE_URL", None)
        self._tmp.cleanup()

    def test_publico_fica_ativo_na_hora(self) -> None:
        ok, msg = self.acc.register_user(
            email="cidadao_ativo@example.com",
            nome="Cidadao Teste",
            password="senha1234",
            nivel_solicitado="publico",
        )
        self.assertTrue(ok, msg)
        user, auth_msg = self.acc.authenticate("cidadao_ativo@example.com", "senha1234")
        self.assertIsNotNone(user, auth_msg)
        self.assertEqual(user["nivel"], "publico")
        self.assertEqual(user["status"], "ativo")

    def test_municipal_fica_pendente_e_exige_municipio(self) -> None:
        ok, msg = self.acc.register_user(
            email="sms@cuiaba.mt.gov.br",
            nome="Vigilancia SMS",
            password="senha1234",
            nivel_solicitado="municipal",
        )
        self.assertFalse(ok)
        self.assertIn("município", msg.lower())

        ok, msg = self.acc.register_user(
            email="sms@cuiaba.mt.gov.br",
            nome="Vigilancia SMS",
            password="senha1234",
            nivel_solicitado="municipal",
            municipio="Cuiabá",
        )
        self.assertTrue(ok, msg)
        user, auth_msg = self.acc.authenticate("sms@cuiaba.mt.gov.br", "senha1234")
        self.assertIsNone(user)
        self.assertIn("pendente", auth_msg.lower())
        row = self.acc.get_user_by_email("sms@cuiaba.mt.gov.br")
        self.assertEqual(row["status"], "pendente")
        self.assertEqual(row["nivel"], "publico")
        self.assertEqual(row["nivel_solicitado"], "municipal")
        self.assertTrue(row.get("cod_ibge"))
        self.assertTrue(row.get("regional_saude"))

    def test_admin_nao_e_autoatribuido(self) -> None:
        ok, msg = self.acc.register_user(
            email="hack@example.com",
            nome="Tentativa Admin",
            password="senha1234",
            nivel_solicitado="admin",
        )
        self.assertFalse(ok)
        self.assertIn("Administração", msg)

    def test_recorte_municipal_trava_territorio(self) -> None:
        self.acc.register_user(
            email="sms@cuiaba.mt.gov.br",
            nome="Vigilancia SMS",
            password="senha1234",
            nivel_solicitado="municipal",
            municipio="Cuiabá",
        )
        self.acc.set_user_status("sms@cuiaba.mt.gov.br", status="ativo", nivel="municipal", aprovado_por="admin")
        row = self.acc._row_public(self.acc.get_user_by_email("sms@cuiaba.mt.gov.br"))
        recorte = self.acc.recorte_usuario(row)
        self.assertTrue(recorte["lock_municipal"])
        self.assertTrue(recorte["lock_regional"])
        self.assertEqual(recorte["municipios"], ["Cuiabá"])
        self.assertTrue(recorte["regionais"])

    def test_matriz_sala_so_ses_admin(self) -> None:
        from sisclima.plano.acesso import MATRIZ_ACESSO_PAINEL, pode_abrir_sala

        by_nivel = {r["nivel"]: r for r in MATRIZ_ACESSO_PAINEL}
        self.assertEqual(by_nivel["municipal"]["abre_sala"], "não")
        self.assertEqual(by_nivel["ses"]["abre_sala"], "sim")
        self.assertFalse(pode_abrir_sala({"email": "a@b.c", "nivel": "publico", "status": "ativo"}))
        self.assertTrue(pode_abrir_sala({"email": "a@b.c", "nivel": "ses", "status": "ativo"}))
        self.assertFalse(pode_abrir_sala({"email": "a@b.c", "nivel": "ses", "status": "pendente"}))


    def test_rate_limit_login_apos_falhas(self) -> None:
        self.acc.register_user(
            email="rate@example.com",
            nome="Cidadao Teste",
            password="senha1234",
            nivel_solicitado="publico",
        )
        for _ in range(self.acc._LOGIN_MAX_FAILS):
            user, msg = self.acc.authenticate("rate@example.com", "errada")
            self.assertIsNone(user)
        user, msg = self.acc.authenticate("rate@example.com", "senha1234")
        self.assertIsNone(user)
        self.assertIn("tentativas", msg.lower())

    def test_current_user_revoga_se_suspenso(self) -> None:
        self.acc.register_user(
            email="suspenso@example.com",
            nome="Cidadao Teste",
            password="senha1234",
            nivel_solicitado="publico",
        )
        user, _ = self.acc.authenticate("suspenso@example.com", "senha1234")
        session: dict = {}
        self.acc.login_to_session(user, session)
        self.assertIsNotNone(self.acc.current_user(session))
        self.acc.set_user_status("suspenso@example.com", status="suspenso", aprovado_por="admin")
        self.assertIsNone(self.acc.current_user(session))

    def test_preview_interno_desligado_por_padrao(self) -> None:
        os.environ.pop("ARARAS_ALLOW_LOCAL_PREVIEW", None)
        session: dict = {}
        self.assertFalse(self.acc.apply_local_interno_preview(session))
        self.assertIsNone(session.get(self.acc.SESSION_KEY))


if __name__ == "__main__":
    unittest.main()
