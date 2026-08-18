# -*- coding: utf-8 -*-
"""Exporta tabelas essenciais do Postgres operacional para SQLite de demo no Cloud.

Uso:
  .\\.venv\\Scripts\\python.exe exportar_snapshot_cloud.py

Gera: data/cloud/sis_cloud_seed.db
No Streamlit Cloud, sem DATABASE_URL público, o painel usa este arquivo.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)

OUT = ROOT / "data" / "cloud" / "sis_cloud_seed.db"

# Tabelas que alimentam o painel completo (KPIs + abas). Ordem irrelevante.
TABLES = [
    "resumo_municipal_atual",
    "met_biometeo",
    "predicao_calor_7d_municipal_v6",
    "predicao_calor_7d_regional_v6",
    "ops_sisreg_municipio",
    "alerta_integrado_sis_titan",
    "solo_saturacao_municipal",
    "hidro_risco_municipal",
    "inmet_alertas",
    "cemaden_alertas",
    "ana_risco_municipal",
    "ana_telemetria",
    "ana_estacoes",
    "qualidade_ar_municipal",
    "qualidade_ar_estado_serie_v6",
    "queimadas_focos_municipal",
    "predicao_calor_7d_skill_resumo_v1",
    "predicao_calor_7d_ml_aux_v1",
    "epi_nowcast_municipal_v1",
    "epi_nowcast_skill_resumo_v1",
    "wash_municipal",
    "hospital_ocupacao_municipio",
    "epi_pressao_assistencial",
    "epi_arboviroses",
    "epi_arboviroses_municipal",
    "epi_sivep_srag",
    "epi_sivep_se_municipal",
    "epi_sivep_virus_se",
    "epi_sivep_qualidade_ms",
    "epi_sivep_indicadores_ms",
    "dicionario_indicadores_ms_sivep",
    "epi_sentinela_sg_indicadores",
    "epi_sentinela_sg_semanal",
    "epi_sentinela_sg_virus_se",
    "epi_sentinela_sg_faixa_etaria",
    "dicionario_indicadores_ms_sentinela_sg",
    "saude_calor_municipio",
    "saude_calor_serie_estado",
    "dicionario_monitoramento_saude_v6",
    "gal_positividade_municipal_v6",
    "gal_positividade_estado_serie_v6",
    "sim_obitos_calor_municipal_v6",
    "sim_obitos_calor_estado_serie_v6",
    "geocalor_status_modelagem_v11_12",
    "geocalor_cardioresp_rr_municipal_v11_12",
    "adaptasus_risco_estado",
    "adaptasus_risco_municipal",
    "geo_vulnerabilidade_municipal",
    "ops_estoque_autonomia",
    "ops_infraestrutura_resumo",
    "ops_resumo_operacional_proxy",
    "ops_resumo_operacional_cnes",
    "alerta_inteligente_municipal_v6",
    "alerta_inteligente_regional_v6",
    "analise_clima_saude_base_municipal_v8",
    "analise_clima_saude_correlacoes_v8",
    "analise_clima_saude_odds_ratio_v1",
    "analise_clima_saude_alertas_estatisticos_v8",
    "sazonalidade_indice_mensal_v1",
    "sazonalidade_heatmap_semana_ano_v1",
    "sazonalidade_perfil_semana_epi_v1",
    "sazonalidade_picos_v1",
    "clima_desfecho_lags_v1",
    "v9_status_modelagem_temporal",
    "v9_validacao",
    "v9_painel_saude_municipal_mensal",
    "v9_painel_clima_saude_mensal",
    "v9_lags_clima_saude",
    "v9_modelos_temporais",
    "v9_priorizacao_epidemiologica",
    "prontidao_municipal",
    "prontidao_redistribuicao_regional",
    "prontidao_plano_acao",
    "vigibarragens_populacoes",
    "vigibarragens_municipal",
]


def main() -> None:
    """Exporta a base operacional ativa (Postgres ou SQLite) para o seed Cloud."""
    import os
    import shutil
    import tempfile

    from sisclima.core.db import get_engine, is_sqlite, reset_engine, table_exists

    # Garante que .env / seed fallback já foram resolvidos pelo core.
    reset_engine()
    src = get_engine()
    src_url = str(src.url)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    # Se a fonte já é o próprio seed, copia via temp para evitar lock no Windows.
    if is_sqlite() and Path(str(src.url).replace("sqlite:///", "")).resolve() == OUT.resolve():
        print(f"[INFO] Fonte já é {OUT} — regenerando via leitura das tabelas.")

    tmp_path = OUT.with_suffix(".tmp.db")
    if tmp_path.exists():
        tmp_path.unlink()
    dst = create_engine(f"sqlite:///{tmp_path.as_posix()}")

    exported = []
    skipped = []
    with src.connect() as conn:
        if "postgres" in src_url:
            existing = {
                r[0]
                for r in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).fetchall()
            }
        else:
            existing = {
                r[0]
                for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
            }
        for table in TABLES:
            if table not in existing and not table_exists(table):
                skipped.append(table)
                continue
            try:
                df = pd.read_sql(text(f'SELECT * FROM "{table}"'), conn)
            except Exception:
                skipped.append(table)
                continue
            df.to_sql(table, dst, index=False, if_exists="replace")
            exported.append((table, len(df)))

    dst.dispose()
    # Windows: Streamlit/OneDrive podem manter lock no seed — tenta várias vezes
    last_err: Exception | None = None
    for attempt in range(1, 8):
        try:
            if OUT.exists():
                try:
                    OUT.unlink()
                except OSError:
                    # rename costuma funcionar quando unlink falha (handle compartilhado)
                    bak = OUT.with_suffix(f".old{attempt}.db")
                    if bak.exists():
                        bak.unlink(missing_ok=True)
                    OUT.rename(bak)
            shutil.move(str(tmp_path), str(OUT))
            # limpa backups residuais
            for bak in OUT.parent.glob("sis_cloud_seed.old*.db"):
                try:
                    bak.unlink()
                except OSError:
                    pass
            last_err = None
            break
        except OSError as exc:
            last_err = exc
            time.sleep(0.4 * attempt)
    if last_err is not None:
        raise OSError(
            f"Não foi possível substituir {OUT} (arquivo em uso). "
            f"Feche o painel Streamlit local e rode de novo. tmp={tmp_path}. "
            f"Causa: {last_err}"
        ) from last_err

    mb = OUT.stat().st_size / (1024 * 1024)
    print(f"OK {OUT} ({mb:.1f} MB) · fonte={src_url.split('://')[0]}")
    print(f"exportadas {len(exported)} · ausentes {len(skipped)}")
    for t, n in exported[:15]:
        print(f"  {t}: {n}")
    if len(exported) > 15:
        print(f"  ... +{len(exported) - 15} tabelas")
    if mb > 90:
        print("AVISO: arquivo grande para GitHub (>90 MB). Considere Postgres público no Cloud.")
    if not exported:
        raise SystemExit("Nenhuma tabela exportada — verifique DATABASE_URL / seed.")


if __name__ == "__main__":
    main()
