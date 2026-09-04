# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from datetime import date

import pandas as pd

from sisclima.core.config import ENV_ALIASES
from sisclima.ingestion.esus_aps import (
    assert_read_only_sql,
    build_esus_aps_url,
    classify_esus_layout,
    credentials_ready,
    esus_aps_config,
    fetch_date_bounds,
    get_esus_engine,
    is_pii_column,
    probe_tcp_ports,
    reset_esus_engine,
    select_relevant_tables,
    suggest_indicators,
    use_esus_aps,
)

_ESUS_KEYS = (
    "USE_ESUS_APS",
    "ESUS_APS_HOST",
    "ESUS_HOST",
    "ESUS_APS_PORT",
    "ESUS_APS_DATABASE",
    "ESUS_APS_DB",
    "ESUS_DB",
    "ESUS_APS_USER",
    "ESUS_USER",
    "ESUS_APS_PASSWORD",
    "ESUS_PASSWORD",
    "ESUS_APS_SSLMODE",
    "ESUS_APS_CONNECT_TIMEOUT",
    "ESUS_APS_QUERY_TIMEOUT_SECONDS",
    "ESUS_APS_SCHEMA",
)


class _FakeSocket:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class EsusApsConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {k: os.environ.get(k) for k in _ESUS_KEYS}
        self._saved["DATABASE_URL"] = os.environ.get("DATABASE_URL")
        for k in _ESUS_KEYS:
            os.environ.pop(k, None)
        reset_esus_engine()

    def tearDown(self) -> None:
        reset_esus_engine()
        for k in _ESUS_KEYS:
            if self._saved.get(k) is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = self._saved[k]
        if self._saved.get("DATABASE_URL") is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._saved["DATABASE_URL"]

    def _fill_cfg(self) -> None:
        os.environ["ESUS_APS_HOST"] = "10.15.0.25"
        os.environ["ESUS_APS_PORT"] = "5432"
        os.environ["ESUS_APS_DATABASE"] = "esus2"
        os.environ["ESUS_APS_USER"] = "leitor"
        os.environ["ESUS_APS_PASSWORD"] = "s3cret!"
        os.environ["ESUS_APS_SSLMODE"] = "disable"
        os.environ["DATABASE_URL"] = (
            "postgresql+psycopg2://sisclima:ops@localhost:5432/sis_clima_saude"
        )

    def test_aliases_nao_colidem_com_database_url(self) -> None:
        db_aliases = set(ENV_ALIASES["DATABASE_URL"])
        esus_host = set(ENV_ALIASES["ESUS_APS_HOST"])
        esus_db = set(ENV_ALIASES["ESUS_APS_DATABASE"])
        self.assertTrue(esus_host.isdisjoint(db_aliases))
        self.assertTrue(esus_db.isdisjoint(db_aliases))
        self.assertNotIn("DB_HOST", ENV_ALIASES["ESUS_APS_HOST"])
        self.assertNotIn("DATABASE_URL", ENV_ALIASES["ESUS_APS_HOST"])

    def test_url_aponta_esus2_e_ignora_database_url(self) -> None:
        self._fill_cfg()
        cfg = esus_aps_config()
        self.assertEqual(cfg["host"], "10.15.0.25")
        self.assertEqual(cfg["database"], "esus2")
        self.assertEqual(cfg["port"], 5432)
        url = build_esus_aps_url(cfg)
        self.assertIn("10.15.0.25", url)
        self.assertIn("esus2", url)
        self.assertIn("sslmode=disable", url)
        self.assertIn("connect_timeout=15", url)
        self.assertNotIn("sis_clima_saude", url)
        self.assertNotIn("localhost", url)
        hidden = build_esus_aps_url(cfg, hide_password=True)
        self.assertNotIn("s3cret!", hidden)

    def test_alias_esus_host(self) -> None:
        os.environ["ESUS_HOST"] = "10.15.0.25"
        os.environ["ESUS_DB"] = "esus2"
        os.environ["ESUS_USER"] = "leitor"
        os.environ["ESUS_PASSWORD"] = "x"
        cfg = esus_aps_config()
        self.assertEqual(cfg["host"], "10.15.0.25")
        self.assertEqual(cfg["database"], "esus2")
        self.assertTrue(credentials_ready(cfg))

    def test_sem_host_falha(self) -> None:
        with self.assertRaises(ValueError):
            esus_aps_config()

    def test_use_esus_flag(self) -> None:
        self.assertFalse(use_esus_aps())
        os.environ["USE_ESUS_APS"] = "true"
        self.assertTrue(use_esus_aps())

    def test_engine_isolada_do_araras(self) -> None:
        self._fill_cfg()
        fake = MagicMock()
        with patch("sisclima.ingestion.esus_aps.create_engine", return_value=fake) as ce:
            engine = get_esus_engine()
        self.assertIs(engine, fake)
        url = ce.call_args[0][0]
        kwargs = ce.call_args.kwargs
        self.assertIn("10.15.0.25", url)
        self.assertIn("esus2", url)
        self.assertNotIn("sis_clima_saude", url)
        self.assertIn("default_transaction_read_only=on", kwargs["connect_args"]["options"])

    def test_sql_escrita_bloqueado(self) -> None:
        assert_read_only_sql("SELECT 1")
        assert_read_only_sql("-- comentario\nWITH x AS (SELECT 1) SELECT * FROM x")
        with self.assertRaises(ValueError):
            assert_read_only_sql("INSERT INTO tb_fat_x VALUES (1)")
        with self.assertRaises(ValueError):
            assert_read_only_sql("COPY tb_fat_x TO STDOUT")


class EsusApsLayoutTests(unittest.TestCase):
    def test_classifica_cubo_centralizador(self) -> None:
        tables = [
            "tb_fat_atendimento_individual",
            "tb_fat_procedimentos",
            "tb_dim_municipio",
            "tb_dim_tempo",
        ]
        layout = classify_esus_layout(tables)
        self.assertEqual(layout["kind"], "centralizador_cubo")
        self.assertIn("tb_fat_atendimento_individual", layout["facts"])
        self.assertIn("tb_dim_municipio", layout["dims"])
        self.assertEqual(layout["pec_hits"], [])

    def test_classifica_pec(self) -> None:
        layout = classify_esus_layout(["tb_cidadao", "tb_atend", "tb_lotacao"])
        self.assertEqual(layout["kind"], "pec_operacional")
        self.assertEqual(layout["pec_hits"], ["tb_atend", "tb_cidadao"])

    def test_classifica_desconhecido(self) -> None:
        layout = classify_esus_layout(["pg_stat_statements"])
        self.assertEqual(layout["kind"], "desconhecido")

    def test_pii_columns(self) -> None:
        self.assertTrue(is_pii_column("nu_cpf"))
        self.assertTrue(is_pii_column("no_cidadao"))
        self.assertTrue(is_pii_column("ds_logradouro"))
        self.assertFalse(is_pii_column("co_dim_tempo"))
        self.assertFalse(is_pii_column("co_seq_fat_atd_ind"))

    def test_indicadores_a_partir_de_fatos(self) -> None:
        tables = [
            "tb_fat_atendimento_individual",
            "tb_fat_procedimentos",
            "tb_dim_municipio",
        ]
        relevant = select_relevant_tables(tables)
        self.assertIn("tb_fat_atendimento_individual", relevant)
        hints = suggest_indicators(tables)
        by_id = {row["id"]: row for row in hints}
        self.assertEqual(by_id["atendimento_individual"]["status"], "candidato")
        self.assertEqual(by_id["visita_acs"]["status"], "nao_encontrado")

    def test_date_bounds_usa_reader_mock(self) -> None:
        def reader(sql, params=None):
            self.assertIn("MIN(dt_registro)", sql)
            self.assertNotIn("nu_cpf", sql.lower())
            return pd.DataFrame([{"dt_min": "2024-01-01", "dt_max": "2026-09-01"}])

        out = fetch_date_bounds(
            "public",
            "tb_fat_atendimento_individual",
            ["nu_cpf", "dt_registro", "no_cidadao"],
            reader,
        )
        self.assertEqual(out["coluna"], "dt_registro")
        self.assertEqual(out["max"], "2026-09-01")

    def test_tcp_fallback_5433(self) -> None:
        def connect(addr, timeout=None):
            _host, port = addr
            if port == 5432:
                raise OSError("refused")
            return _FakeSocket()

        with patch("sisclima.ingestion.esus_aps.socket.create_connection", side_effect=connect):
            result = probe_tcp_ports("10.15.0.25", [5432, 5433], timeout=0.1)
        self.assertEqual(result["open_port"], 5433)
        self.assertFalse(result["attempts"][0]["ok"])
        self.assertTrue(result["attempts"][1]["ok"])


class EsusApsClimaFilterTests(unittest.TestCase):
    def test_cid_grupos(self) -> None:
        from sisclima.ingestion.esus_aps_clima import (
            CID_CALOR_RE,
            CID_DDA_RE,
            CID_RESP_RE,
            match_cid_group,
        )

        self.assertTrue(match_cid_group("|J45|J30.1|", CID_RESP_RE))
        self.assertTrue(match_cid_group("J21", CID_RESP_RE))
        self.assertFalse(match_cid_group("|J18|", CID_RESP_RE))
        self.assertTrue(match_cid_group("|E86|T67|", CID_CALOR_RE))
        self.assertTrue(match_cid_group("A09", CID_DDA_RE))
        self.assertFalse(match_cid_group("|I10|", CID_CALOR_RE))

    def test_sigtap_nebulizacao(self) -> None:
        from sisclima.ingestion.esus_aps_clima import is_nebulizacao_sigtap

        self.assertTrue(is_nebulizacao_sigtap("0301100039"))
        self.assertTrue(is_nebulizacao_sigtap("03.01.10.003-9"))
        self.assertFalse(is_nebulizacao_sigtap("0301100012"))

    def test_recorte_uf_51(self) -> None:
        from sisclima.ingestion.esus_aps_clima import recorte_mt

        df = pd.DataFrame(
            {
                "cod_ibge": ["5103403", "5208707", "51", "5002704", "5107602"],
                "n": [1, 2, 3, 4, 5],
            }
        )
        out = recorte_mt(df)
        self.assertEqual(sorted(out["cod_ibge"].tolist()), ["5103403", "5107602"])

    def test_sql_templates_tem_placeholders(self) -> None:
        from sisclima.ingestion.esus_aps_clima import SQL_ATEND, SQL_CAD, _load_sql

        atend = _load_sql(SQL_ATEND)
        self.assertIn("0301100039", atend)
        self.assertIn("dt_inicial_atendimento", atend)
        self.assertIn("LIKE '51%'", atend)
        self.assertNotIn("nu_cpf_cidadao", atend)
        self.assertNotIn("no_cidadao", atend)
        cad = SQL_CAD.read_text(encoding="utf-8")
        self.assertIn("st_doenca_respira_asma", cad)
        self.assertIn("co_fat_cidadao_pec", cad)
        self.assertNotIn("no_nome", cad)

    def test_fetch_atendimentos_usa_reader(self) -> None:
        from sisclima.ingestion.esus_aps_clima import fetch_atendimentos_municipio

        captured = {}

        def reader(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            if "MAX(dt_inicial_atendimento)" in sql:
                return pd.DataFrame([{"max_dt": date(2026, 8, 8)}])
            return pd.DataFrame(
                [
                    {
                        "cod_ibge": "5103403",
                        "municipio": "Cuiabá",
                        "atendimentos_7d": 10,
                        "nebulizacao_7d": 2,
                    },
                    {
                        "cod_ibge": "5208707",
                        "municipio": "Goiânia",
                        "atendimentos_7d": 99,
                        "nebulizacao_7d": 9,
                    },
                ]
            )

        out = fetch_atendimentos_municipio(ref=date(2026, 9, 3), reader=reader)
        self.assertEqual(list(out["cod_ibge"]), ["5103403"])
        self.assertIn("dt_ini_7d", captured["params"])
        self.assertIn("tb_fat_atendimento_individual", captured["sql"])
        # Atraso > 3 dias ⇒ âncora em 08/08: janela 7d inicia em 02/08
        self.assertEqual(captured["params"]["dt_ini_7d"].date(), date(2026, 8, 2))
        self.assertTrue(bool(out.iloc[0]["janela_ancorada"]))
        self.assertEqual(int(out.iloc[0]["atraso_dias"]), 26)

    def test_janelas_sem_ancora_quando_fresco(self) -> None:
        from sisclima.ingestion.esus_aps_clima import _janelas

        jan = _janelas(date(2026, 9, 3), ancora=date(2026, 9, 2), max_lag_dias=3)
        self.assertFalse(jan["janela_ancorada"])
        self.assertEqual(jan["data_janela_fim"], date(2026, 9, 3))
        self.assertEqual(jan["dt_ini_7d"].date(), date(2026, 8, 28))

    def test_janelas_ancora_quando_atrasado(self) -> None:
        from sisclima.ingestion.esus_aps_clima import _janelas

        jan = _janelas(date(2026, 9, 3), ancora=date(2026, 8, 8), max_lag_dias=3)
        self.assertTrue(jan["janela_ancorada"])
        self.assertEqual(jan["atraso_dias"], 26)
        self.assertEqual(jan["data_janela_fim"], date(2026, 8, 8))
        self.assertEqual(jan["dt_ini_28d"].date(), date(2026, 7, 12))

    def test_cruzar_so_vermelho_roxo(self) -> None:
        from sisclima.ingestion.esus_aps_clima import cruzar_esus_classe_araras

        cad = pd.DataFrame(
            [
                {"cod_ibge": "5103403", "municipio": "Cuiabá", "asma": 10, "idoso_60mais": 100},
                {"cod_ibge": "5107602", "municipio": "Rondonópolis", "asma": 5, "idoso_60mais": 50},
            ]
        )
        atend = pd.DataFrame(
            [
                {"cod_ibge": "5103403", "atendimentos_7d": 20, "nebulizacao_7d": 3},
                {"cod_ibge": "5107602", "atendimentos_7d": 8, "nebulizacao_7d": 0},
            ]
        )
        resumo = pd.DataFrame(
            [
                {"cod_ibge": "510340", "municipio": "Cuiabá", "nivel": "vermelha"},
                {"cod_ibge": "5107602", "municipio": "Rondonópolis", "nivel": "verde"},
            ]
        )
        out = cruzar_esus_classe_araras(atend=atend, cad=cad, resumo=resumo)
        self.assertEqual(list(out["cod_ibge"]), ["5103403"])
        self.assertEqual(out.iloc[0]["classe_araras"], "vermelha")
        self.assertEqual(int(out.iloc[0]["asma"]), 10)
        self.assertEqual(int(out.iloc[0]["atendimentos_7d"]), 20)

    def test_cruzar_todos_municipios(self) -> None:
        from sisclima.ingestion.esus_aps_clima import cruzar_esus_classe_araras, resumo_esus_estadual

        cad = pd.DataFrame(
            [
                {"cod_ibge": "5103403", "municipio": "Cuiabá", "asma": 10, "cadastros": 100},
                {"cod_ibge": "5107602", "municipio": "Rondonópolis", "asma": 5, "cadastros": 80},
            ]
        )
        resumo = pd.DataFrame(
            [
                {"cod_ibge": "5103403", "nivel": "vermelha"},
                {"cod_ibge": "5107602", "nivel": "verde"},
            ]
        )
        out = cruzar_esus_classe_araras(cad=cad, atend=pd.DataFrame(), resumo=resumo, so_criticos=False)
        self.assertEqual(len(out), 2)
        tot = resumo_esus_estadual(out)
        self.assertEqual(tot["municipios"], 2)
        self.assertEqual(tot["municipios_vermelho_roxo"], 1)
        self.assertEqual(tot["asma"], 15)
        self.assertEqual(len(tot["municipais"]), 2)
        self.assertEqual(len(tot["por_classe"]), 2)


if __name__ == "__main__":
    unittest.main()
