# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class PlanoElNinoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "plano.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
        from sisclima.core import config as cfg
        from sisclima.core.db import reset_engine

        cfg.APP_CONFIG.database_url = f"sqlite:///{db.as_posix()}"
        reset_engine()
        from sisclima.plano.schema import garantir_schema

        garantir_schema()

    def tearDown(self) -> None:
        from sisclima.core.db import reset_engine

        reset_engine()
        os.environ.pop("DATABASE_URL", None)
        self._tmp.cleanup()

    def test_percentual_15_de_20_e_75(self) -> None:
        from sisclima.plano.operacao import percentual_implementacao

        self.assertEqual(percentual_implementacao(15, 20), 75.0)

    def test_cores_de_status(self) -> None:
        from sisclima.plano.constants import STATUS_COR
        from sisclima.plano.operacao import status_cor

        self.assertEqual(status_cor("concluida"), "#16803c")
        self.assertEqual(status_cor("impedida"), "#dc2626")
        self.assertEqual(status_cor("em_andamento"), STATUS_COR["em_andamento"])

    def test_isolamento_area_farmacia_nao_edita_visa(self) -> None:
        from sisclima.plano.acesso import pode_editar_area

        farm = {
            "email": "af@ses.mt.gov.br",
            "nivel": "ses",
            "status": "ativo",
            "perfil_plano": "coordenador_area",
            "area_id": "assistencia_farmaceutica",
        }
        self.assertTrue(pode_editar_area(farm, "assistencia_farmaceutica"))
        self.assertFalse(pode_editar_area(farm, "vigilancia_sanitaria"))
        publico = {
            "email": "x@x",
            "nivel": "publico",
            "status": "ativo",
            "perfil_plano": "coordenador_area",
            "area_id": "assistencia_farmaceutica",
        }
        self.assertFalse(pode_editar_area(publico, "assistencia_farmaceutica"))

    def test_historico_append_nao_overwrite(self) -> None:
        from sisclima.core.db import db_conn, fetchall
        from sisclima.plano import operacao as op

        acao = {"id": "A01", "area_id": "assistencia_farmaceutica", "status_inicial": "nao_iniciada"}
        user = {
            "email": "af@ses.mt.gov.br",
            "nivel": "ses",
            "status": "ativo",
            "perfil_plano": "coordenador_area",
            "area_id": "assistencia_farmaceutica",
        }
        with patch.object(op, "acao_por_id", return_value=acao):
            ok1, _, id1 = op.registrar_atualizacao(user=user, acao_codigo="A01", status="em_andamento", observacao="inicio")
            self.assertTrue(ok1, msg="primeira atualização")
            ok2, _, id2 = op.registrar_atualizacao(user=user, acao_codigo="A01", status="em_validacao", observacao="envio")
            self.assertTrue(ok2)
            self.assertNotEqual(id1, id2)
        with db_conn() as conn:
            rows = fetchall(conn, "SELECT id, status, observacao FROM atualizacao WHERE alvo_codigo = ? ORDER BY id", ("A01",))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "em_andamento")
        self.assertEqual(rows[1]["status"], "em_validacao")
        self.assertEqual(rows[0]["observacao"], "inicio")

    def test_cem_por_cento_nao_oficial_sem_validacao(self) -> None:
        from sisclima.plano.operacao import percentual_oficial

        out = percentual_oficial(concluidos_validados=20, total=20, pendente_validacao=1)
        self.assertEqual(out["percentual"], 100.0)
        self.assertFalse(out["oficial"])
        ok = percentual_oficial(concluidos_validados=20, total=20, pendente_validacao=0)
        self.assertTrue(ok["oficial"])

    def test_recusa_atualizacao_de_outra_area(self) -> None:
        from sisclima.plano import operacao as op

        visa = {"id": "A99", "area_id": "vigilancia_sanitaria", "status_inicial": "nao_iniciada"}
        farm = {
            "email": "af@ses.mt.gov.br",
            "nivel": "ses",
            "status": "ativo",
            "perfil_plano": "tecnico_area",
            "area_id": "assistencia_farmaceutica",
        }
        with patch.object(op, "acao_por_id", return_value=visa):
            ok, msg, _ = op.registrar_atualizacao(user=farm, acao_codigo="A99", status="em_andamento")
        self.assertFalse(ok)
        self.assertIn("Área isolada", msg)

    def test_indicador_15_de_20_e_75_e_nao_oficial_sem_validacao(self) -> None:
        from sisclima.plano.indicadores import avaliar_indicador, parse_denominador, progresso, semaforo

        self.assertEqual(progresso(15, 20), 75.0)
        ind = {
            "id": "IND-X",
            "modo_atualizacao": "semiautomatico",
            "meta_numerica": "100% (20/20)",
            "semaforo": "Verde=100%; Amarelo=80–99%; Vermelho<80%",
            "entra_no_indice": True,
            "tipo": "execucao",
        }
        self.assertEqual(parse_denominador(ind), 20)
        av = avaliar_indicador(ind, {"valor": "15/20", "situacao_validacao": "informado"})
        self.assertEqual(av["percentual"], 75.0)
        self.assertEqual(av["semaforo"], "atraso_risco")
        self.assertFalse(av["oficial"])
        ok = avaliar_indicador(ind, {"valor": "20/20", "situacao_validacao": "validado"})
        self.assertEqual(ok["semaforo"], "meta_atingida")
        self.assertTrue(ok["oficial"])
        self.assertEqual(semaforo(None, ind), "nao_informado")

    def test_indicador_automatico_recusa_digitacao(self) -> None:
        from sisclima.plano import indicadores as indmod

        user = {
            "email": "af@ses.mt.gov.br",
            "nivel": "ses",
            "status": "ativo",
            "perfil_plano": "coordenador_area",
            "area_id": "assistencia_farmaceutica",
        }
        fake = {
            "id": "IND-AUTO",
            "acao_id": "A01",
            "area_id": "assistencia_farmaceutica",
            "modo_atualizacao": "automatico",
        }
        with patch.object(indmod, "indicador_por_id", return_value=fake):
            ok, msg, _ = indmod.registrar_leitura(user=user, indicador_id="IND-AUTO", numerador=1, denominador=1)
        self.assertFalse(ok)
        self.assertIn("automático", msg.casefold())

    def test_conector_resumo_nao_inventa_se_vazio(self) -> None:
        from sisclima.plano import conectores as con

        with patch.object(con, "_resumo", return_value=__import__("pandas").DataFrame()):
            out = con.coletor_resumo_risco("IND-006")
        self.assertEqual(out["status"], "aguardando_fonte")
        self.assertIsNone(out["numerador"])

    def test_conector_resumo_conta_vermelho_roxo(self) -> None:
        import pandas as pd

        from sisclima.plano.conectores import coletor_resumo_risco

        df = pd.DataFrame({"nivel": ["roxa", "vermelha", "amarela", "verde"]})
        with patch("sisclima.plano.conectores._resumo", return_value=df):
            out = coletor_resumo_risco("IND-007")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["numerador"], 2)
        self.assertEqual(out["denominador"], 4)

    def test_sti_rejeita_email_fora_do_dominio(self) -> None:
        from sisclima.auth.sti_oidc import email_institucional, sti_ativado

        self.assertFalse(sti_ativado())
        self.assertTrue(email_institucional("joao@saude.mt.gov.br"))
        self.assertFalse(email_institucional("joao@gmail.com"))

    def test_catalogo_tem_88_indicadores_se_arquivo_existir(self) -> None:
        from sisclima.core.config import ROOT
        from sisclima.plano.catalogo import carregar_catalogo

        path = ROOT / "config" / "plano_el_nino_2026_catalogo.yaml"
        if not path.exists():
            self.skipTest("catálogo ainda não gerado")
        cat = carregar_catalogo()
        self.assertEqual(len(cat.get("indicadores") or []), 88)
        self.assertGreaterEqual(len(cat.get("acoes") or []), 40)

    def test_indicador_em_andamento_permite_segunda_coleta(self) -> None:
        from sisclima.core.db import db_conn, fetchall
        from sisclima.plano import operacao as op
        from sisclima.plano.conectores import USUARIO_SISTEMA

        acao = {"id": "A01", "area_id": "vigilancia_ambiental", "status_inicial": "nao_iniciada"}
        with patch.object(op, "acao_por_id", return_value=acao):
            ok1, msg1, id1 = op.registrar_atualizacao(
                user=USUARIO_SISTEMA,
                acao_codigo="A01",
                status="em_andamento",
                valor="10/142",
                alvo="indicador",
                alvo_codigo="IND-006",
            )
            self.assertTrue(ok1, msg1)
            ok2, msg2, id2 = op.registrar_atualizacao(
                user=USUARIO_SISTEMA,
                acao_codigo="A01",
                status="em_andamento",
                valor="12/142",
                alvo="indicador",
                alvo_codigo="IND-006",
            )
            self.assertTrue(ok2, msg2)
            self.assertNotEqual(id1, id2)
        with db_conn() as conn:
            rows = fetchall(
                conn,
                "SELECT valor, status FROM atualizacao WHERE alvo = ? AND alvo_codigo = ? ORDER BY id",
                ("indicador", "IND-006"),
            )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["valor"], "10/142")
        self.assertEqual(rows[1]["valor"], "12/142")
        self.assertEqual(rows[1]["status"], "em_andamento")

    def test_acao_em_andamento_ainda_nao_repete(self) -> None:
        from sisclima.plano import operacao as op
        from sisclima.plano.conectores import USUARIO_SISTEMA

        acao = {"id": "A01", "area_id": "vigilancia_ambiental", "status_inicial": "nao_iniciada"}
        with patch.object(op, "acao_por_id", return_value=acao):
            ok1, _, _ = op.registrar_atualizacao(
                user=USUARIO_SISTEMA, acao_codigo="A01", status="em_andamento"
            )
            self.assertTrue(ok1)
            ok2, msg2, _ = op.registrar_atualizacao(
                user=USUARIO_SISTEMA, acao_codigo="A01", status="em_andamento"
            )
        self.assertFalse(ok2)
        self.assertIn("não permitida", msg2)

    def test_valor_igual_marca_inalterado_sem_duplicar(self) -> None:
        from sisclima.core.db import db_conn, fetchall
        from sisclima.plano import indicadores as indmod
        from sisclima.plano import operacao as op

        fake = {
            "id": "IND-006",
            "acao_id": "A01",
            "area_id": "vigilancia_ambiental",
            "modo_atualizacao": "automatico",
        }
        acao = {"id": "A01", "area_id": "vigilancia_ambiental", "status_inicial": "nao_iniciada"}
        leitura = {
            "indicador_id": "IND-006",
            "numerador": 10,
            "denominador": 142,
            "fonte": "resumo_municipal_atual.nivel",
            "status": "ok",
        }
        with patch.object(indmod, "indicador_por_id", return_value=fake), patch.object(
            op, "acao_por_id", return_value=acao
        ):
            ok1, msg1, id1 = indmod._gravar_automatico(leitura)
            ok2, msg2, id2 = indmod._gravar_automatico(leitura)
        self.assertTrue(ok1, msg1)
        self.assertNotEqual(msg1, "inalterado")
        self.assertTrue(ok2)
        self.assertEqual(msg2, "inalterado")
        self.assertEqual(id1, id2)
        with db_conn() as conn:
            rows = fetchall(
                conn,
                "SELECT id FROM atualizacao WHERE alvo = ? AND alvo_codigo = ?",
                ("indicador", "IND-006"),
            )
        self.assertEqual(len(rows), 1)

    def test_coletores_leem_tabelas_do_pipeline(self) -> None:
        import pandas as pd

        from sisclima.plano import conectores as con

        tables = {
            "resumo_municipal_atual": pd.DataFrame(
                {
                    "nivel": ["vermelha", "verde"],
                    "pm25_ugm3": [30.0, 8.0],
                    "populacao": [1000, 500],
                    "ocupacao_leitos_pct": [90.0, 40.0],
                    "data_referencia": ["2026-08-24", "2026-08-24"],
                }
            ),
            "epi_sinan_agravos": pd.DataFrame(
                {
                    "cod_ibge": ["5103403", "5102504"],
                    "agravo": ["dengue", "malaria"],
                    "acima_esperado": [1, 0],
                }
            ),
            "ops_estoque_autonomia": pd.DataFrame(
                {
                    "estoque_total": [100.0, 20.0],
                    "consumo_medio_diario": [10.0, 10.0],
                    "autonomia_dias": [10.0, 2.0],
                }
            ),
            "qualidade_ar_municipal": pd.DataFrame({"cod_ibge": ["5103403", "5102504"]}),
            "ops_comunicacao": pd.DataFrame(
                {"cod_ibge": ["5103403"], "latencia_horas": [12.0]}
            ),
            "hospital_capacidade_unidade": pd.DataFrame(
                {"leitos_total": [20, 8], "grupo_tipo": ["hospital", "ubs"]}
            ),
        }
        lidas: list[str] = []

        def fake_exists(nome: str) -> bool:
            return nome in tables and not tables[nome].empty

        def fake_read(nome: str):
            lidas.append(nome)
            return tables[nome]

        con.limpar_cache_coleta()
        with (
            patch.object(con, "table_exists", side_effect=fake_exists),
            patch.object(con, "read_table", side_effect=fake_read),
        ):
            estoque = con.coletor_estoque("IND-024")
            sinan = con.coletor_sinan("IND-015")
            qualidade = con.coletor_qualidade("IND-012")
            com = con.coletor_comunicacao("IND-029")
            cnes = con.coletor_cnes("IND-083")
            risco = con.coletor_resumo_risco("IND-007")

        self.assertEqual(estoque["status"], "ok")
        self.assertIn("ops_estoque_autonomia", estoque["fonte"])
        self.assertEqual(estoque["numerador"], 1)
        self.assertEqual(estoque["denominador"], 2)
        self.assertNotIn("estoque_saf", lidas)

        self.assertEqual(sinan["status"], "ok")
        self.assertEqual(sinan["fonte"], "epi_sinan_agravos")

        self.assertEqual(qualidade["status"], "ok")
        self.assertIn("qualidade_ar_municipal", qualidade["fonte"])

        self.assertEqual(com["status"], "ok")
        self.assertIn("ops_comunicacao", com["fonte"])

        self.assertEqual(cnes["status"], "ok")
        self.assertIn("hospital_capacidade_unidade", cnes["fonte"])

        self.assertEqual(risco["status"], "ok")
        self.assertEqual(risco["numerador"], 1)

    def test_rotina_diaria_chama_coleta_do_plano(self) -> None:
        import inspect

        import rotina_diaria_ops as rot

        self.assertTrue(callable(rot.step_plano_indicadores))
        self.assertIn("step_plano_indicadores", inspect.getsource(rot.main))
        fake = {
            "gravados": 2,
            "inalterados": 1,
            "aguardando_fonte": 8,
            "erros": 0,
            "n": 11,
            "ok": 3,
        }
        with (
            patch("sisclima.plano.indicadores.atualizar_automaticos", return_value=fake),
            patch(
                "sisclima.plano.cobranca.resumo_cobranca",
                return_value={"n_pendencias": 0, "n_cobrar_area": 0, "n_aguardar_fonte": 0},
            ),
            patch("sisclima.plano.relatorio_pdf.gerar_pdf_cobranca", return_value=Path("cobranca.pdf")),
            patch("sisclima.plano.cobranca.exportar_rascunhos", return_value=Path("emails")),
        ):
            out = rot.step_plano_indicadores()
        self.assertEqual(out["gravados"], 2)
        self.assertEqual(out["inalterados"], 1)
        self.assertEqual(out["cobranca"]["n_pendencias"], 0)

    def test_sinan_ignora_municipio_510000_e_nao_passa_de_142(self) -> None:
        import pandas as pd

        from sisclima.plano import conectores as con

        df = pd.DataFrame(
            {
                "cod_ibge": ["510000", "510340", "510340", "510250"],
                "agravo": ["dengue", "dengue", "dengue", "dengue"],
                "data": ["2026-08-01"] * 4,
            }
        )
        con.limpar_cache_coleta()
        with (
            patch.object(con, "table_exists", return_value=True),
            patch.object(con, "read_table", return_value=df),
        ):
            out = con.coletor_sinan("IND-073")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["numerador"], 2)
        self.assertEqual(out["denominador"], 142)
        self.assertLessEqual(out["numerador"], out["denominador"])

    def test_ind016_usa_alerta_aumento_do_pipeline(self) -> None:
        import pandas as pd

        from sisclima.plano import conectores as con

        arbo = pd.DataFrame(
            {
                "cod_ibge": ["510340", "510250", "510000"],
                "data": ["2026-08-24"] * 3,
                "alerta_aumento": [1, 0, 1],
                "zscore_arbovirus": [2.1, 0.2, 4.0],
            }
        )
        tables = {"epi_arboviroses": arbo, "epi_sinan_agravos": pd.DataFrame({"cod_ibge": ["510340"]})}

        def fake_read(nome: str):
            return tables.get(nome, pd.DataFrame())

        con.limpar_cache_coleta()
        with (
            patch.object(con, "table_exists", side_effect=lambda n: n in tables and not tables[n].empty),
            patch.object(con, "read_table", side_effect=fake_read),
        ):
            out = con.coletor_sinan("IND-016")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["numerador"], 1)
        self.assertEqual(out["denominador"], 142)
        self.assertIn("alerta_aumento", out["fonte"])

    def test_catalogo_sala_mapeia_vigiagua_e_cievs(self) -> None:
        from sisclima.plano.participantes import area_id_do_catalogo, participantes_com_email

        self.assertEqual(area_id_do_catalogo(area_texto="VIGIÁGUA", sigla="COVAM"), "vigiagua")
        self.assertEqual(area_id_do_catalogo(sigla="COVSAN"), "vigilancia_sanitaria")
        rows = {r["email"]: r for r in participantes_com_email()}
        self.assertEqual(rows["robertaorrigo@ses.mt.gov.br"]["area_id"], "vigiagua")
        self.assertEqual(rows["menandesneto@ses.mt.gov.br"]["perfil_sugerido"], "secretaria_executiva_cievs")
        self.assertEqual(rows["suzicruz@ses.mt.gov.br"]["perfil_sugerido"], "tecnico_area")

    def test_aplicar_catalogo_grava_vinculo_sem_criar_usuario(self) -> None:
        from sisclima.auth.access import get_user_by_email
        from sisclima.plano.acesso import perfil_plano_efetivo, pode_editar_area
        from sisclima.plano.participantes import aplicar_vinculos_catalogo

        cat = {
            "participantes": [
                {
                    "nome": "SAF Teste",
                    "email": "saf@ses.mt.gov.br",
                    "area_id": "assistencia_farmaceutica",
                    "papel": "grupo_tecnico",
                    "perfil_sugerido": "tecnico_area",
                }
            ]
        }
        out = aplicar_vinculos_catalogo(cat=cat, ator_email="admin@ses.mt.gov.br")
        self.assertEqual(out["gravados"], 1, out)
        self.assertIsNone(get_user_by_email("saf@ses.mt.gov.br"))
        user = {"email": "saf@ses.mt.gov.br", "nivel": "ses", "status": "ativo"}
        self.assertEqual(perfil_plano_efetivo(user), "tecnico_area")
        self.assertTrue(pode_editar_area(user, "assistencia_farmaceutica"))
        self.assertFalse(pode_editar_area(user, "vigilancia_sanitaria"))

    def test_pdf_automaticos_nao_inventa_aguardando_fonte(self) -> None:
        from sisclima.plano.relatorio_pdf import pdf_bytes_indicadores_automaticos

        linhas = [
            {
                "id": "IND-006",
                "nome": "Cobertura de classificação",
                "area": "Vigilância ambiental",
                "modo": "automatico",
                "situacao": "coletado",
                "leitura": "142/142",
                "fonte": "resumo_municipal_atual",
                "nota": "",
                "bloco_pendente": "",
            },
            {
                "id": "IND-008",
                "nome": "Monitoramento da água",
                "area": "Vigiágua",
                "modo": "automatico",
                "situacao": "aguardando_fonte",
                "leitura": "—",
                "fonte": "Sem carga SISAGUA",
                "nota": "",
                "bloco_pendente": "VIGIÁGUA / SISAGUA",
            },
        ]
        raw = pdf_bytes_indicadores_automaticos(linhas, coletado_em="25/08/2026 15:00")
        self.assertTrue(raw.startswith(b"%PDF"))
        self.assertGreater(len(raw), 2000)
        self.assertNotIn(b"0/142", raw)

    def test_municipal_abre_interno_e_nao_abre_sala(self) -> None:
        from sisclima.plano.acesso import capacidades_usuario, pode_abrir_interno, pode_abrir_sala

        mun = {
            "email": "sms@cuiaba.mt.gov.br",
            "nivel": "municipal",
            "status": "ativo",
            "municipio": "Cuiabá",
        }
        self.assertTrue(pode_abrir_interno(mun))
        self.assertFalse(pode_abrir_sala(mun))
        cap = capacidades_usuario(mun)
        self.assertFalse(cap["abre_sala"])
        self.assertEqual(cap["perfil_plano"], "")

    def test_ses_sem_vinculo_entra_como_consulta(self) -> None:
        from sisclima.plano.acesso import perfil_plano_efetivo, pode_abrir_sala, pode_validar

        ses = {"email": "ses@ses.mt.gov.br", "nivel": "ses", "status": "ativo"}
        self.assertTrue(pode_abrir_sala(ses))
        self.assertEqual(perfil_plano_efetivo(ses), "consulta")
        self.assertFalse(pode_validar(ses))

    def test_vinculo_plano_define_area_e_perfil(self) -> None:
        from sisclima.plano.acesso import gravar_vinculo, perfil_plano_efetivo, pode_editar_area

        ok, msg = gravar_vinculo(
            email="af@ses.mt.gov.br",
            perfil_plano="coordenador_area",
            area_id="assistencia_farmaceutica",
            ator_email="admin@ses.mt.gov.br",
        )
        self.assertTrue(ok, msg)
        user = {"email": "af@ses.mt.gov.br", "nivel": "ses", "status": "ativo"}
        self.assertEqual(perfil_plano_efetivo(user), "coordenador_area")
        self.assertTrue(pode_editar_area(user, "assistencia_farmaceutica"))
        self.assertFalse(pode_editar_area(user, "vigilancia_sanitaria"))

    def test_linhas_painel_nao_inventa_aguardando_fonte(self) -> None:
        from sisclima.plano.indicadores import csv_painel_indicadores, linhas_painel_indicadores, resumo_painel_indicadores

        quadro = [
            {
                "id": "IND-008",
                "nome": "Monitoramento da água",
                "area_id": "vigiagua",
                "modo": "automatico",
                "numerador": None,
                "denominador": 142,
                "percentual": None,
                "rotulo": "Automático (fonte)",
                "entra_no_indice": True,
                "editavel": False,
            },
            {
                "id": "IND-006",
                "nome": "Cobertura de classificação",
                "area_id": "vigilancia_ambiental",
                "modo": "automatico",
                "numerador": 142,
                "denominador": 142,
                "percentual": 100.0,
                "rotulo": "Meta atingida",
                "entra_no_indice": True,
                "editavel": False,
            },
        ]
        leituras = [
            {"indicador_id": "IND-008", "status": "aguardando_fonte", "motivo": "Sem carga SISAGUA"},
            {"indicador_id": "IND-006", "status": "ok", "numerador": 142, "denominador": 142, "fonte": "resumo_municipal_atual"},
        ]
        linhas = linhas_painel_indicadores(quadro=quadro, leituras_auto=leituras)
        self.assertEqual(linhas[0]["situacao"], "aguardando_fonte")
        self.assertEqual(linhas[0]["leitura"], "—")
        self.assertEqual(linhas[0]["bloco_pendente"], "VIGIÁGUA / SISAGUA")
        self.assertEqual(linhas[1]["situacao"], "coletado")
        self.assertEqual(linhas[1]["leitura"], "142/142")
        resumo = resumo_painel_indicadores(linhas)
        self.assertEqual(resumo["n_coletados"], 1)
        self.assertEqual(resumo["n_aguardando"], 1)
        csv_txt = csv_painel_indicadores(linhas)
        self.assertIn("IND-008", csv_txt)
        self.assertIn("aguardando_fonte", csv_txt)

    def test_onda_a_portaria_infra_sinan_e_sugestao_cnes(self) -> None:
        import pandas as pd

        from sisclima.plano.catalogo import carregar_catalogo, indicador_por_id
        from sisclima.plano import conectores as con

        carregar_catalogo.cache_clear()
        for iid in ("IND-001", "IND-023", "IND-062", "IND-064", "IND-066"):
            self.assertEqual(indicador_por_id(iid)["modo_atualizacao"], "automatico", iid)
        self.assertEqual(indicador_por_id("IND-003")["modo_atualizacao"], "semiautomatico")

        portaria = con.coletor_portaria("IND-001")
        self.assertEqual(portaria["status"], "ok")
        self.assertGreater(portaria["numerador"], 0)
        self.assertEqual(portaria["denominador"], 11)
        self.assertLessEqual(portaria["numerador"], portaria["denominador"])

        con.limpar_cache_coleta()
        with patch.object(con, "table_exists", return_value=False):
            vazio = con.coletor_infra("IND-023")
        self.assertEqual(vazio["status"], "aguardando_fonte")
        self.assertIsNone(vazio["numerador"])

        infra = pd.DataFrame({"falha_critica": [1, 0, 1], "unidade": ["A", "B", "C"]})
        con.limpar_cache_coleta()
        with (
            patch.object(con, "table_exists", side_effect=lambda n: n == "ops_infraestrutura_unidade"),
            patch.object(con, "read_table", return_value=infra),
        ):
            out_inf = con.coletor_infra("IND-023")
        self.assertEqual(out_inf["status"], "ok")
        self.assertEqual(out_inf["numerador"], 2)
        self.assertEqual(out_inf["denominador"], 3)

        sinan = pd.DataFrame(
            {
                "cod_ibge": ["510340", "510250", "510760"],
                "agravo": ["leishmaniose visceral canina", "doença de chagas", "malaria"],
            }
        )
        con.limpar_cache_coleta()
        with (
            patch.object(con, "table_exists", return_value=True),
            patch.object(con, "read_table", return_value=sinan),
        ):
            leish = con.coletor_sinan("IND-064")
            triat = con.coletor_sinan("IND-062")
            anoph = con.coletor_sinan("IND-066")
        self.assertEqual(leish["numerador"], 1)
        self.assertEqual(triat["numerador"], 1)
        self.assertEqual(anoph["numerador"], 1)

        hosp = pd.DataFrame({"grupo_tipo": ["hospital", "hospital", "ubs"], "leitos_total": [10, 8, 2]})
        con.limpar_cache_coleta()
        with (
            patch.object(con, "table_exists", side_effect=lambda n: n == "hospital_capacidade_unidade"),
            patch.object(con, "read_table", return_value=hosp),
        ):
            sug = con.sugerir_leitura("IND-082")
        self.assertIsNotNone(sug)
        self.assertIsNone(sug["numerador"])
        self.assertEqual(sug["denominador"], 2)
        self.assertIn("hospitais", sug["nota"])

        resumo = pd.DataFrame({"regional_saude": ["Sinop", "Sinop", "Baixada Cuiabana", "Regional não informada"]})
        with patch.object(con, "_resumo", return_value=resumo):
            sug_ers = con.sugerir_leitura("IND-003")
        self.assertEqual(sug_ers["numerador"], 2)
        self.assertEqual(sug_ers["denominador"], 16)

    def test_cobranca_separa_area_fonte_e_rascunho(self) -> None:
        from sisclima.plano.cobranca import classificar_pendencia, rascunho_email_area, relatorio_cobranca

        doc = classificar_pendencia(
            {
                "id": "IND-035",
                "modo": "documental",
                "situacao": "nao_informado",
                "entra_no_indice": True,
            }
        )
        fonte = classificar_pendencia(
            {
                "id": "IND-008",
                "modo": "automatico",
                "situacao": "aguardando_fonte",
                "bloco_pendente": "VIGIÁGUA / SISAGUA",
            }
        )
        ok = classificar_pendencia({"id": "IND-006", "modo": "automatico", "situacao": "coletado"})
        self.assertEqual(doc["classe"], "area")
        self.assertEqual(doc["prioridade"], 1)
        self.assertEqual(fonte["classe"], "fonte")
        self.assertIsNone(ok)

        linhas = [
            {
                "id": "IND-035",
                "nome": "NT água",
                "area_id": "vigilancia_sanitaria",
                "area": "Vigilância Sanitária",
                "modo": "documental",
                "situacao": "nao_informado",
                "leitura": "—",
                "entra_no_indice": True,
                "sugestao": "",
                "fonte": "área ainda não informou",
            },
            {
                "id": "IND-008",
                "nome": "água válida",
                "area_id": "vigiagua",
                "area": "Vigiágua",
                "modo": "automatico",
                "situacao": "aguardando_fonte",
                "leitura": "—",
                "entra_no_indice": True,
                "bloco_pendente": "VIGIÁGUA / SISAGUA",
                "sugestao": "",
                "fonte": "sem SISAGUA",
            },
        ]
        rel = relatorio_cobranca(linhas, coletado_em="25/08/2026")
        self.assertEqual(rel["n_cobrar_area"], 1)
        self.assertEqual(rel["n_aguardar_fonte"], 1)
        visa = next(a for a in rel["areas"] if a["area_id"] == "vigilancia_sanitaria")
        draft = rascunho_email_area(visa, coletado_em="25/08/2026")
        self.assertTrue(visa["contatos"])
        self.assertIn("IND-035", draft["corpo"])
        self.assertIn("menandesneto@ses.mt.gov.br", draft["cc"])

    def test_sugestao_nao_grava_atualizacao(self) -> None:
        from unittest.mock import patch

        from sisclima.plano.sugestoes import SEM_NUMERADOR, sugerir_indicador

        with patch("sisclima.plano.operacao.registrar_atualizacao") as mocked:
            sug = sugerir_indicador("IND-003")
            mocked.assert_not_called()
        self.assertIsNotNone(sug)
        self.assertEqual(sug.get("status"), "sugerido")
        self.assertEqual(sug.get("denominador"), 16)

        for iid in SEM_NUMERADOR:
            self.assertIsNone(sugerir_indicador(iid), iid)

        doc = sugerir_indicador("IND-002")
        self.assertIsNotNone(doc)
        self.assertIsNone(doc["numerador"])
        self.assertEqual(doc["status"], "sugerido")

        ind031 = sugerir_indicador("IND-031")
        self.assertIsNotNone(ind031)
        self.assertIsNone(ind031["numerador"])
        self.assertIn("estratégia", ind031["nota"].lower())

    def test_fila_indice_agrupa_onda1_documental(self) -> None:
        from sisclima.plano.sugestoes import fila_para_indice

        linhas = [
            {
                "id": "IND-002",
                "nome": "Fluxo estadual",
                "modo": "documental",
                "situacao": "nao_informado",
                "entra_no_indice": True,
            },
            {
                "id": "IND-006",
                "nome": "Cobertura",
                "modo": "automatico",
                "situacao": "coletado",
                "entra_no_indice": True,
            },
            {
                "id": "IND-008",
                "nome": "Água",
                "modo": "automatico",
                "situacao": "aguardando_fonte",
                "entra_no_indice": True,
            },
        ]
        fila = fila_para_indice(linhas)
        self.assertEqual([r["id"] for r in fila["onda1"]], ["IND-002"])
        self.assertEqual([r["id"] for r in fila["fonte"]], ["IND-008"])
        self.assertEqual(fila["n_pendentes_indice"], 2)

        from sisclima.plano.cobranca import rascunho_email_area

        draft = rascunho_email_area(
            {
                "area": "CIEVS",
                "area_id": "cievs",
                "n_area": 1,
                "n_fonte": 0,
                "n_carga": 0,
                "n_documental": 1,
                "ids": ["IND-002"],
                "itens": [
                    {
                        "id": "IND-002",
                        "nome": "Fluxo estadual",
                        "acao": "Anexar evidência",
                        "onda": "1",
                    }
                ],
                "contatos": [{"email": "cievs@ses.mt.gov.br"}],
            },
            coletado_em="26/08/2026",
        )
        self.assertIn("Prioridade desta semana", draft["corpo"])
        self.assertIn("IND-002", draft["corpo"])

    def test_oito_aguardando_continuam_sem_numero(self) -> None:
        from sisclima.plano.conectores import coletar_indicador
        from sisclima.plano.sugestoes import SEM_NUMERADOR

        for iid in SEM_NUMERADOR:
            leitura = coletar_indicador(iid)
            self.assertNotEqual(leitura.get("status"), "ok", iid)
            self.assertIsNone(leitura.get("numerador"), iid)

    def test_onda_b_le_tabela_quando_existe_e_nao_inventa_vazia(self) -> None:
        import pandas as pd

        from sisclima.plano import conectores as con

        con.limpar_cache_coleta()
        with (
            patch.object(con, "table_exists", return_value=False),
            patch.object(con, "read_table", return_value=pd.DataFrame()),
        ):
            vazio = con.coletor_sisagua("IND-008")
        self.assertEqual(vazio["status"], "aguardando_fonte")
        self.assertIsNone(vazio["numerador"])

        sisagua = pd.DataFrame(
            {
                "cod_ibge": ["510340", "510250", "510760"],
                "monitoramento_valido": [1, 0, 1],
                "amostras_realizadas": [10, 0, 5],
                "amostras_planejadas": [10, 10, 10],
                "saa_mapeadas": [2, 1, 0],
                "saa_identificadas": [2, 2, 1],
            }
        )
        entom = pd.DataFrame(
            {
                "cod_ibge": ["510340", "510250"],
                "ovitrampas_positivas": [4, 1],
                "ovitrampas_examinadas": [8, 4],
                "ido": [60, 10],
                "iip": [5.0, 1.0],
            }
        )
        den = pd.DataFrame(
            {
                "status": ["respondida", "aberta", "encerrada"],
                "prioritaria": [1, 1, 0],
                "dentro_sla": [1, 0, 1],
            }
        )

        def fake_read(nome: str):
            return {"ops_sisagua": sisagua, "ops_entomologia": entom, "ops_denuncias": den}.get(
                nome, pd.DataFrame()
            )

        con.limpar_cache_coleta()
        with (
            patch.object(con, "table_exists", return_value=True),
            patch.object(con, "read_table", side_effect=fake_read),
        ):
            i008 = con.coletor_sisagua("IND-008")
            i069 = con.coletor_sisagua("IND-069")
            i070 = con.coletor_sisagua("IND-070")
            i075 = con.coletor_entomologia("IND-075")
            i076 = con.coletor_entomologia("IND-076")
            i077 = con.coletor_entomologia("IND-077")
            i052 = con.coletor_denuncias("IND-052")
            i053 = con.coletor_denuncias("IND-053")
        self.assertEqual(i008["status"], "ok")
        self.assertEqual(i008["numerador"], 2)
        self.assertEqual(i008["denominador"], 3)
        self.assertEqual(i069["numerador"], 15)
        self.assertEqual(i069["denominador"], 30)
        self.assertEqual(i070["numerador"], 3)
        self.assertEqual(i070["denominador"], 5)
        self.assertEqual(i075["numerador"], 5)
        self.assertEqual(i075["denominador"], 12)
        self.assertEqual(i076["numerador"], 1)
        self.assertEqual(i077["numerador"], 1)
        self.assertEqual(i052["numerador"], 2)
        self.assertEqual(i052["denominador"], 3)
        self.assertEqual(i053["numerador"], 1)
        self.assertEqual(i053["denominador"], 2)

    def test_escalonamento_88_com_classe_e_duplicidades(self) -> None:
        from collections import Counter

        from sisclima.plano.catalogo import carregar_catalogo
        from sisclima.plano.escalonamento import carregar_escalonamento, mapa_indicadores

        carregar_catalogo.cache_clear()
        from sisclima.plano.escalonamento import limpar_cache_escalonamento

        limpar_cache_escalonamento()
        inds = mapa_indicadores()
        self.assertEqual(len(inds), 88)
        c = Counter(v["classe_emergencia"] for v in inds.values())
        self.assertEqual(c["A"], 57)
        self.assertEqual(c["B"], 7)
        self.assertEqual(c["C"], 21)
        self.assertEqual(c["D"], 3)
        self.assertEqual(inds["IND-068"]["id_canonico"], "IND-006")
        self.assertEqual(inds["IND-073"]["id_canonico"], "IND-015")
        self.assertEqual(inds["IND-074"]["id_canonico"], "IND-029")
        cat = carregar_catalogo()
        item = next(i for i in cat["indicadores"] if i["id"] == "IND-001")
        self.assertEqual(inds["IND-001"]["classe_emergencia"], "C")
        self.assertTrue(inds["IND-001"]["gate_prontidao"])
        self.assertEqual(item["papel_operacional"], "hibrido")
        self.assertEqual(item["perfil_s"], "S1")
        self.assertFalse(item["gate_prontidao"])
        cievs = carregar_escalonamento().get("indicadores_cievs") or []
        self.assertEqual(len(cievs), 30)

    def test_adequacao_28_08_papeis_e_aliases(self) -> None:
        from sisclima.plano.catalogo import carregar_catalogo, resumo_adequacao
        from sisclima.plano.escalonamento import cadencia, limpar_cache_escalonamento

        carregar_catalogo.cache_clear()
        limpar_cache_escalonamento()
        resumo = resumo_adequacao()
        self.assertEqual(resumo["n"], 88)
        self.assertEqual(resumo["por_papel"]["operacional"], 44)
        self.assertEqual(resumo["por_papel"]["preparacao"], 17)
        self.assertEqual(resumo["por_papel"]["gatilho"], 16)
        self.assertEqual(resumo["por_papel"]["hibrido"], 8)
        self.assertEqual(resumo["por_papel"]["alias"], 3)
        self.assertEqual(resumo["n_ativos"], 85)
        cat = carregar_catalogo()
        by_id = {i["id"]: i for i in cat["indicadores"]}
        self.assertFalse(by_id["IND-068"]["entra_no_indice"])
        self.assertEqual(by_id["IND-068"]["id_canonico"], "IND-006")
        self.assertEqual(by_id["IND-073"]["id_canonico"], "IND-015")
        self.assertEqual(by_id["IND-074"]["id_canonico"], "IND-029")
        self.assertFalse(by_id["IND-007"]["entra_no_indice"])
        self.assertEqual(by_id["IND-007"]["tipo"], "risco_gatilho")
        self.assertTrue(by_id["IND-002"]["gate_prontidao"])
        self.assertEqual(by_id["IND-002"]["papel_operacional"], "preparacao")
        self.assertEqual(len(by_id["IND-062"]["subindicadores"]), 2)
        self.assertEqual(cadencia("IND-004", "laranja"), "diario_24h")

    def test_gatilho_nao_vira_meta_e_denom_zero_e_na(self) -> None:
        from sisclima.plano.completude import pontuar_completude
        from sisclima.plano.indicadores import avaliar_indicador

        gatilho = avaliar_indicador(
            {
                "id": "IND-007",
                "nome": "risco elevado",
                "papel_operacional": "gatilho",
                "tipo": "risco_gatilho",
                "modo_atualizacao": "automatico",
                "entra_no_indice": False,
                "semaforo": "Verde=100%",
            },
            {"valor": "10/16", "situacao_validacao": "validado"},
        )
        self.assertEqual(gatilho["semaforo"], "sinal_gatilho")
        self.assertFalse(gatilho["oficial"])
        self.assertFalse(gatilho["entra_no_indice"])

        alias = avaliar_indicador(
            {
                "id": "IND-068",
                "papel_operacional": "alias",
                "id_canonico": "IND-006",
                "modo_atualizacao": "automatico",
                "entra_no_indice": False,
            },
            {"valor": "142/142"},
        )
        self.assertEqual(alias["semaforo"], "alias")

        na = avaliar_indicador(
            {
                "id": "IND-009",
                "papel_operacional": "operacional",
                "modo_atualizacao": "semiautomatico",
                "entra_no_indice": True,
            },
            {"valor": "0/0"},
        )
        self.assertEqual(na["semaforo"], "nao_aplicavel")
        self.assertIsNone(na["percentual"])

        comp = pontuar_completude({"id": "IND-009", "denominador": 0, "numerador": 0, "situacao": "informado"})
        self.assertEqual(comp["status_completude"], "nao_aplicavel")

    def test_completude_sem_fonte_nao_e_zero_de_meta(self) -> None:
        from sisclima.plano.completude import pontuar_completude

        out = pontuar_completude(
            {
                "id": "IND-008",
                "situacao": "aguardando_fonte",
                "modo": "automatico",
                "numerador": None,
                "denominador": 142,
                "area_id": "vigiagua",
            }
        )
        self.assertEqual(out["status_completude"], "sem_dado_valido")
        self.assertFalse(out["fonte_ok"])
        self.assertLess(out["completude"], 95)

    def test_cobranca_nao_trata_prontidao_como_atraso_de_crise(self) -> None:
        from sisclima.plano.cobranca import classificar_pendencia

        pend = classificar_pendencia(
            {
                "id": "IND-001",
                "modo": "semiautomatico",
                "situacao": "nao_informado",
                "classe_emergencia": "C",
                "gate_prontidao": True,
                "entra_no_indice": True,
            }
        )
        self.assertEqual(pend["classe"], "prontidao")
        self.assertGreaterEqual(pend["prioridade"], 6)

    def test_ativacao_nao_altera_nivel_de_risco(self) -> None:
        from sisclima.plano.ativacao import estagio_atual, quadro_dois_estados, registrar_estagio

        user = {"email": "cievs@ses.mt.gov.br", "nivel": "ses"}
        antes = quadro_dois_estados()
        ok, msg = registrar_estagio(user=user, estagio="laranja", observacao="PAI simplificado")
        self.assertTrue(ok, msg)
        depois = quadro_dois_estados()
        self.assertEqual(depois["estagio_ativacao"], "laranja")
        self.assertEqual(depois["nivel_risco"], antes["nivel_risco"])
        self.assertEqual(estagio_atual()["estagio"], "laranja")

    def test_pai_so_a_partir_do_amarelo(self) -> None:
        from sisclima.plano.ativacao import registrar_estagio
        from sisclima.plano.pai import pode_abrir_pai, registrar_acao_pai

        user = {"email": "cievs@ses.mt.gov.br", "nivel": "ses"}
        ok, msg, _ = registrar_acao_pai(
            user=user,
            indicador_id="IND-007",
            descricao="Abrir PAI",
        )
        self.assertFalse(ok)
        self.assertIn("Amarelo", msg)
        registrar_estagio(user=user, estagio="amarelo", observacao="teste")
        ok2, motivo = pode_abrir_pai("IND-007", estagio="amarelo")
        self.assertTrue(ok2, motivo)
        ok3, msg3, nid = registrar_acao_pai(user=user, indicador_id="IND-007", descricao="Monitorar persistência")
        self.assertTrue(ok3, msg3)
        self.assertIsNotNone(nid)

    def test_or_timeline_e_sazonalidade_sem_inventar_vazio(self) -> None:
        import pandas as pd

        from sisclima.engines.odds_ratio import compute_or_timeline, or_binary
        from sisclima.plano.analise_clima_sala import sazonalidade_mensal

        daily = pd.DataFrame(
            {
                "data": pd.date_range("2026-01-01", periods=60, freq="D"),
                "tmax": [28] * 30 + [36] * 30,
                "casos_srag": [2] * 30 + [9] * 30,
            }
        )
        or_t = compute_or_timeline(daily, "tmax", "casos_srag", window_days=28, step_days=7)
        self.assertFalse(or_t.empty)
        self.assertIn("or", or_t.columns)
        self.assertTrue((or_t["or"] > 1).any())

        snap = pd.DataFrame({"tmax": [30, 38, 29, 40, 31, 39, 28, 37, 32, 41, 33, 42], "casos_srag": [1, 8, 2, 9, 1, 7, 2, 8, 1, 9, 2, 10]})
        item = or_binary(snap, "tmax", "casos_srag")
        self.assertIsNotNone(item)
        self.assertGreater(item["or"], 1)

        saz = sazonalidade_mensal(daily.rename(columns={"tmax": "tmax"}))
        self.assertFalse(saz.empty)
        self.assertIn("indice_sazonal", saz.columns)

    def test_quadro_criticos_nao_inventa_leitura(self) -> None:
        from sisclima.plano.criticos import LIMIARES_HOMOLOGAR, quadro_criticos
        from sisclima.plano.escalonamento import limpar_cache_escalonamento
        from sisclima.plano.catalogo import carregar_catalogo

        carregar_catalogo.cache_clear()
        limpar_cache_escalonamento()
        quadro = quadro_criticos()
        self.assertEqual(quadro["n_limiar"], len(LIMIARES_HOMOLOGAR))
        self.assertEqual(quadro["n_gatilho"], 16)
        self.assertEqual(quadro["n_sem_fonte"], 8)
        ids_limiar = {r["id"] for r in quadro["limiares"]}
        self.assertEqual(ids_limiar, set(LIMIARES_HOMOLOGAR))
        for r in quadro["sem_fonte"]:
            if r.get("situacao") != "coletado":
                self.assertEqual(r["leitura"], "—")
        pdf = __import__("sisclima.plano.relatorio_criticos", fromlist=["pdf_bytes_relatorio_criticos"])
        rel = pdf.pdf_bytes_relatorio_criticos(coletado_em="27/08/2026")
        apr = pdf.pdf_bytes_apresentacao_criticos(coletado_em="27/08/2026")
        self.assertGreater(len(rel), 2000)
        self.assertGreater(len(apr), 2000)
        self.assertTrue(rel.startswith(b"%PDF"))
        self.assertTrue(apr.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
