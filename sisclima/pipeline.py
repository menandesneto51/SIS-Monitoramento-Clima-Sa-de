from __future__ import annotations
import uuid
import pandas as pd
import numpy as np
from sisclima.core.config import SETTINGS, APP_CONFIG, env, as_bool
from sisclima.core.db import write_df, sqlite_conn
from sisclima.core.logging_utils import get_logger
from sisclima.utils.dates import now_iso
from sisclima.utils.municipios import ensure_municipality, municipality_cols, latest_by_municipio
from sisclima.ingestion.local_csv import load_all_inputs, load_csv
from sisclima.ingestion.openmeteo import fetch_openmeteo_for_municipios
from sisclima.ingestion.inmet import fetch_inmet_alerts, normalize_inmet_alerts
from sisclima.ingestion.indicasus import load_indicasus_leitos
from sisclima.ingestion.dw_sources import load_dw_sinan_agravos, load_dw_sim_obitos, load_dw_gal_lacen
from sisclima.ingestion.sivep_local import load_sivep_local
from sisclima.ingestion.copernicus_air_quality import fetch_cams_air_quality_municipal
from sisclima.ingestion.ibge_municipios import get_municipios_operacionais
from sisclima.engines.biometeo import add_biometeo_indicators
from sisclima.engines.air_quality import add_air_quality_indicators
from sisclima.engines.epidemiology import pressure_assistencial, sivep_summary, lacen_summary, sinan_summary, sim_heat_deaths
from sisclima.engines.hospital import hospital_capacity, aggregate_capacity
from sisclima.engines.operations import stock_autonomy, infrastructure_status, active_search, communication_latency
from sisclima.engines.sentinel import score_rumors
from sisclima.engines.resilience import resilience_index, vulnerability_index
from sisclima.engines.stages import classify_stage
from sisclima.engines.recommendations import recommendations_for_stage
from sisclima.alerts.change_detector import get_previous_level, update_current_level, maybe_send_level_change

log = get_logger(__name__)


def _safe_float(x, default=np.nan):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def _ensure_all(df: pd.DataFrame) -> pd.DataFrame:
    return ensure_municipality(df) if df is not None and not df.empty else pd.DataFrame()


def _latest_value_by_mun(df: pd.DataFrame, value_cols: list[str], how: str = 'last') -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = _ensure_all(df)
    if 'data' in out.columns:
        out['data'] = pd.to_datetime(out['data'], errors='coerce')
    keys = municipality_cols(out)
    if not keys:
        if 'data' in out.columns:
            out = out.sort_values('data').tail(1)
        return out[[c for c in ['data'] + value_cols if c in out.columns]]
    if how == 'min':
        # pega último dia por município e mínimo dos indicadores no dia
        last_dates = out.groupby(keys, dropna=False)['data'].max().reset_index().rename(columns={'data':'_last_data'})
        tmp = out.merge(last_dates, on=keys, how='inner')
        tmp = tmp[tmp['data'].eq(tmp['_last_data'])]
        agg = {c:'min' for c in value_cols if c in tmp.columns}
        res = tmp.groupby(keys, dropna=False, as_index=False).agg(**{c:(c,'min') for c in agg})
        res['data'] = tmp.groupby(keys, dropna=False)['data'].max().values
        return res
    if how == 'max':
        last_dates = out.groupby(keys, dropna=False)['data'].max().reset_index().rename(columns={'data':'_last_data'})
        tmp = out.merge(last_dates, on=keys, how='inner')
        tmp = tmp[tmp['data'].eq(tmp['_last_data'])]
        agg = {c:'max' for c in value_cols if c in tmp.columns}
        res = tmp.groupby(keys, dropna=False, as_index=False).agg(**{c:(c,'max') for c in agg})
        res['data'] = tmp.groupby(keys, dropna=False)['data'].max().values
        return res
    return latest_by_municipio(out)


def _merge(base: pd.DataFrame, other: pd.DataFrame, suffix: str = "") -> pd.DataFrame:
    if other is None or other.empty:
        return base

    if base is None or base.empty:
        return other

    base = base.copy()
    other = other.copy()

    for _df in (base, other):
        if "cod_ibge" in _df.columns:
            _df["cod_ibge"] = (
                _df["cod_ibge"]
                .astype(str)
                .str.replace(r"\.0$", "", regex=True)
                .str.strip()
            )
            _df.loc[_df["cod_ibge"].isin(["nan", "None", "NaT", "<NA>"]), "cod_ibge"] = ""

        if "data" in _df.columns:
            _df["data"] = pd.to_datetime(_df["data"], errors="coerce").dt.date.astype(str)
            _df.loc[_df["data"].isin(["NaT", "nan", "None", "<NA>"]), "data"] = ""

    if "data" in base.columns and "data" in other.columns and "cod_ibge" in base.columns and "cod_ibge" in other.columns:
        keys = ["data", "cod_ibge"]
    elif "cod_ibge" in base.columns and "cod_ibge" in other.columns:
        keys = ["cod_ibge"]
    elif "data" in base.columns and "data" in other.columns:
        keys = ["data"]
    else:
        return base

    return base.merge(other, on=keys, how="left", suffixes=("", suffix or "_y"))

def _inmet_municipio_has_alert(alerts: pd.DataFrame, municipio: str | None) -> str | None:
    if alerts is None or alerts.empty:
        return None
    txtdf = alerts.copy()
    if municipio and 'municipio' in txtdf.columns:
        mask = txtdf['municipio'].astype(str).str.lower().eq(str(municipio).lower())
        # alertas sem município explícito valem para o estado/área
        if mask.any():
            txt = ' '.join(txtdf.loc[mask].astype(str).tail(5).values.ravel()).lower()
        else:
            txt = ' '.join(txtdf.astype(str).tail(5).values.ravel()).lower()
    else:
        txt = ' '.join(txtdf.astype(str).tail(5).values.ravel()).lower()
    if 'vermelho' in txt or 'grande perigo' in txt:
        return 'Alerta INMET vermelho/grande perigo detectado'
    if 'laranja' in txt or 'perigo' in txt:
        return 'Alerta INMET laranja/perigo detectado'
    if 'amarelo' in txt or 'perigo potencial' in txt:
        return 'Alerta INMET amarelo/perigo potencial detectado'
    return None



def _read_sqlite_table_safe(table_name: str) -> pd.DataFrame:
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path("data/output/sis_integrado.db")
        if not db_path.exists():
            return pd.DataFrame()
        with sqlite3.connect(db_path) as con:
            exists = pd.read_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                con,
                params=(table_name,),
            )
            if exists.empty:
                return pd.DataFrame()
            return pd.read_sql(f"SELECT * FROM {table_name}", con)
    except Exception as exc:
        print(f"[AVISO] Não foi possível ler {table_name} do SQLite: {exc}")
        return pd.DataFrame()


def _run_indicasus_occupancy_update() -> None:
    try:
        import subprocess
        import sys
        from pathlib import Path

        script = Path("atualizar_ocupacao_indicasus.py")
        if not script.exists():
            print("[AVISO] atualizar_ocupacao_indicasus.py não encontrado; ocupação real será ignorada nesta rodada.")
            return

        proc = subprocess.run(
            [sys.executable, str(script)],
            check=False,
            capture_output=True,
            text=True,
        )

        if proc.stdout:
            print(proc.stdout)
        if proc.stderr:
            print(proc.stderr)

        if proc.returncode != 0:
            print(f"[AVISO] atualizar_ocupacao_indicasus.py retornou código {proc.returncode}.")
    except Exception as exc:
        print(f"[AVISO] Falha ao executar atualizador de ocupação IndicaSUS: {exc}")


def _prepare_ocupacao_cap_agg(cap_agg_fallback: pd.DataFrame) -> pd.DataFrame:
    occ = _read_sqlite_table_safe("hospital_ocupacao_municipio")
    if occ.empty:
        return cap_agg_fallback

    out = occ.copy()

    if "municipio" not in out.columns:
        if "municipio_base" in out.columns:
            out = out.rename(columns={"municipio_base": "municipio"})
        elif "municipio_indicasus" in out.columns:
            out = out.rename(columns={"municipio_indicasus": "municipio"})

    if "leitos_total" not in out.columns and "leitos_existentes" in out.columns:
        out["leitos_total"] = pd.to_numeric(out["leitos_existentes"], errors="coerce")

    if "leitos_livres" not in out.columns:
        total = pd.to_numeric(out.get("leitos_total"), errors="coerce")
        ocup = pd.to_numeric(out.get("leitos_ocupados"), errors="coerce")
        out["leitos_livres"] = (total - ocup).clip(lower=0)

    if "ocupacao_pct" in out.columns:
        out["ocupacao_pct"] = pd.to_numeric(out["ocupacao_pct"], errors="coerce").clip(lower=0, upper=100)

    keep = [
        "cod_ibge",
        "municipio",
        "ocupacao_pct",
        "leitos_total",
        "leitos_ocupados",
        "leitos_livres",
        "ultima_movimentacao",
        "fonte",
    ]
    keep = [c for c in keep if c in out.columns]
    out = out[keep].copy()

    if "data" not in out.columns:
        if "ultima_movimentacao" in out.columns:
            out["data"] = out["ultima_movimentacao"]
        else:
            out["data"] = pd.Timestamp.now().strftime("%Y-%m-%d")

    return out


def _get_ocupacao_estado_fallback() -> float | None:
    estado = _read_sqlite_table_safe("hospital_ocupacao_estado")
    if estado.empty or "ocupacao_pct" not in estado.columns:
        return None
    valor = pd.to_numeric(estado["ocupacao_pct"], errors="coerce").dropna()
    if valor.empty:
        return None
    return float(valor.iloc[0])



def _inject_ocupacao_into_summary(summary: pd.DataFrame) -> pd.DataFrame:
    # Injeta ocupação real do IndicaSUS no resumo_municipal_atual antes da gravação.
    # Prioridade: município por cod_ibge; fallback estadual quando município não tiver dado.
    if summary is None or summary.empty:
        return summary

    out = summary.copy()

    cols_ocup = [
        "ocupacao_leitos_pct",
        "leitos_total",
        "leitos_ocupados",
        "leitos_livres",
        "leitos_sus",
        "ultima_movimentacao_ocupacao",
        "fonte_ocupacao",
        "leitos_bloqueados_movimento",
        "leitos_higienizacao",
        "leitos_reservados",
    ]
    for col in cols_ocup:
        if col in out.columns:
            out = out.drop(columns=[col])

    occ = _read_sqlite_table_safe("hospital_ocupacao_municipio")

    if not occ.empty and "cod_ibge" in occ.columns:
        occ = occ.copy()
        occ["cod_ibge"] = occ["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)

        rename_map = {
            "ocupacao_pct": "ocupacao_leitos_pct",
            "leitos_existentes": "leitos_total",
            "ultima_movimentacao": "ultima_movimentacao_ocupacao",
            "fonte": "fonte_ocupacao",
        }
        occ = occ.rename(columns={k: v for k, v in rename_map.items() if k in occ.columns})

        keep = [
            "cod_ibge",
            "ocupacao_leitos_pct",
            "leitos_total",
            "leitos_sus",
            "leitos_ocupados",
            "leitos_bloqueados_movimento",
            "leitos_higienizacao",
            "leitos_reservados",
            "ultima_movimentacao_ocupacao",
            "fonte_ocupacao",
        ]
        keep = [c for c in keep if c in occ.columns]
        occ = occ[keep].drop_duplicates("cod_ibge")

        if "leitos_total" in occ.columns and "leitos_ocupados" in occ.columns:
            total = pd.to_numeric(occ["leitos_total"], errors="coerce")
            ocup = pd.to_numeric(occ["leitos_ocupados"], errors="coerce")
            occ["leitos_livres"] = (total - ocup).clip(lower=0)

        if "ocupacao_leitos_pct" in occ.columns:
            occ["ocupacao_leitos_pct"] = pd.to_numeric(
                occ["ocupacao_leitos_pct"],
                errors="coerce"
            ).clip(lower=0, upper=100)

        if "cod_ibge" in out.columns:
            out["cod_ibge"] = out["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
            out = out.merge(occ, on="cod_ibge", how="left")

    estado = _read_sqlite_table_safe("hospital_ocupacao_estado")
    if not estado.empty and "ocupacao_pct" in estado.columns:
        valor_estado = pd.to_numeric(estado["ocupacao_pct"], errors="coerce").dropna()
        if not valor_estado.empty:
            if "ocupacao_leitos_pct" not in out.columns:
                out["ocupacao_leitos_pct"] = pd.NA
            out["ocupacao_leitos_pct"] = pd.to_numeric(
                out["ocupacao_leitos_pct"],
                errors="coerce"
            ).fillna(float(valor_estado.iloc[0])).clip(lower=0, upper=100)
            if "fonte_ocupacao" not in out.columns:
                out["fonte_ocupacao"] = pd.NA
            out["fonte_ocupacao"] = out["fonte_ocupacao"].fillna("INDICASUS_TEMPO_REAL_ESTADUAL_FALLBACK")

    return out


def _build_municipal_summary(met_ind, press, cap_agg, stock, infra, busca, com, sivep, lacen, sim, rumors, aq, vuln, inmet_alerts) -> pd.DataFrame:
    # Base municipal preferencial: vulnerabilidade/metadata; se não houver, usa bases com dados.
    base_candidates = [vuln, met_ind, press, cap_agg, aq]
    base = pd.DataFrame()
    for b in base_candidates:
        if b is not None and not b.empty and 'municipio' in b.columns:
            cols = [c for c in ['cod_ibge','municipio','lat','lon','indice_vulnerabilidade_calor','populacao'] if c in b.columns]
            base = b[cols].drop_duplicates(subset=[c for c in ['cod_ibge','municipio'] if c in cols]).copy()
            if not base.empty:
                break
    if base.empty:
        base = pd.DataFrame([{'cod_ibge': None, 'municipio': APP_CONFIG.municipio, 'lat': APP_CONFIG.lat, 'lon': APP_CONFIG.lon}])

    latest_met = latest_by_municipio(met_ind) if not met_ind.empty else pd.DataFrame()
    latest_press = latest_by_municipio(press) if not press.empty else pd.DataFrame()
    latest_cap = _latest_value_by_mun(cap_agg, ['ocupacao_pct','leitos_total','leitos_ocupados','leitos_livres'], how='max') if not cap_agg.empty else pd.DataFrame()
    latest_cap = latest_cap.rename(columns={'ocupacao_pct':'ocupacao_leitos_pct'}) if not latest_cap.empty else latest_cap
    latest_stock = _latest_value_by_mun(stock, ['autonomia_dias'], how='min') if not stock.empty else pd.DataFrame()
    latest_stock = latest_stock.rename(columns={'autonomia_dias':'autonomia_min_dias'}) if not latest_stock.empty else latest_stock
    latest_infra = latest_by_municipio(infra) if not infra.empty else pd.DataFrame()
    latest_busca = _latest_value_by_mun(busca, ['cobertura_pct'], how='min') if not busca.empty else pd.DataFrame()
    latest_busca = latest_busca.rename(columns={'cobertura_pct':'cobertura_busca_pct'}) if not latest_busca.empty else latest_busca
    latest_com = latest_by_municipio(com) if not com.empty else pd.DataFrame()
    latest_sivep = latest_by_municipio(sivep) if not sivep.empty else pd.DataFrame()
    latest_lacen = latest_by_municipio(lacen) if not lacen.empty else pd.DataFrame()
    latest_sim = latest_by_municipio(sim) if not sim.empty else pd.DataFrame()
    latest_rumors = latest_by_municipio(rumors) if not rumors.empty else pd.DataFrame()
    latest_aq = latest_by_municipio(aq) if not aq.empty else pd.DataFrame()

    merged = base.copy()
    for d, suf in [
        (latest_met, '_met'), (latest_press, '_press'), (latest_cap, '_cap'), (latest_stock, '_stock'),
        (latest_infra, '_infra'), (latest_busca, '_busca'), (latest_com, '_com'), (latest_sivep, '_sivep'),
        (latest_lacen, '_lacen'), (latest_sim, '_sim'), (latest_rumors, '_rum'), (latest_aq, '_ar')
    ]:
        merged = _merge(merged, d, suffix=suf)

    # Ocupação real IndicaSUS: usa município quando houver e estado como fallback.
    ocup_estado_fallback = _get_ocupacao_estado_fallback()
    if ocup_estado_fallback is not None:
        if 'ocupacao_leitos_pct' not in merged.columns:
            merged['ocupacao_leitos_pct'] = np.nan
        merged['ocupacao_leitos_pct'] = pd.to_numeric(
            merged['ocupacao_leitos_pct'],
            errors='coerce'
        ).fillna(ocup_estado_fallback)

    rows = []
    for _, r in merged.iterrows():
        latest = r.to_dict()
        # Normalizações esperadas pelo classificador
        latest['latencia_comunicacao_horas'] = _safe_float(latest.get('latencia_horas'))
        latest['casos_srag'] = _safe_float(latest.get('casos_srag'), 0)
        latest['positividade_lacen_pct'] = _safe_float(latest.get('positividade_pct'), 0)
        latest['obitos_calor_suspeitos'] = _safe_float(latest.get('obitos_calor_suspeitos'), 0)
        latest['score_sentinela'] = _safe_float(latest.get('score_sentinela'), 0)
        latest['iq_ar_score'] = _safe_float(latest.get('iq_ar_score'), np.nan)
        stage = classify_stage(latest, SETTINGS)
        extra_motivos = []
        if latest.get('obitos_calor_suspeitos', 0) and latest.get('obitos_calor_suspeitos', 0) >= 1:
            if stage.score < 3:
                stage.score = 3; stage.nivel = 'vermelha'
            extra_motivos.append('Óbito suspeito relacionado ao calor registrado no SIM/proxy')
        if latest.get('score_sentinela', 0) and latest.get('score_sentinela', 0) >= 10 and stage.score < 2:
            stage.score = 2; stage.nivel = 'laranja'
            extra_motivos.append('SENTINELA detectou concentração de rumores críticos')
        motivo_inmet = _inmet_municipio_has_alert(inmet_alerts, latest.get('municipio'))
        if motivo_inmet:
            if 'vermelho' in motivo_inmet and stage.score < 3:
                stage.score = 3; stage.nivel = 'vermelha'
            elif 'laranja' in motivo_inmet and stage.score < 2:
                stage.score = 2; stage.nivel = 'laranja'
            elif 'amarelo' in motivo_inmet and stage.score < 1:
                stage.score = 1; stage.nivel = 'amarela'
            extra_motivos.append(motivo_inmet)
        if latest.get('motivo_qualidade_ar') and pd.notna(latest.get('motivo_qualidade_ar')):
            extra_motivos.append(str(latest.get('motivo_qualidade_ar')))
        stage.motivos.extend(extra_motivos)
        resil = resilience_index(latest, SETTINGS.get('pesos_resiliencia', {}))
        datas = [latest.get(c) for c in latest if str(c).startswith('data') and pd.notna(latest.get(c))]
        data_ref = None
        if datas:
            try:
                data_ref = max(pd.to_datetime(datas, errors='coerce')).date().isoformat()
            except Exception:
                data_ref = pd.Timestamp.today().date().isoformat()
        else:
            data_ref = pd.Timestamp.today().date().isoformat()
        row = {**latest, **resil, 'nivel': stage.nivel, 'score': stage.score, 'motivo': '; '.join(stage.motivos[:14]), 'data_referencia': data_ref}
        rows.append(row)
    out = pd.DataFrame(rows)
    # Limpa colunas auxiliares excessivas para painel/CSV
    return out


def run_pipeline(send_alerts: bool = True) -> dict:
    run_id = str(uuid.uuid4())
    with sqlite_conn() as conn:
        conn.execute('INSERT INTO pipeline_runs (run_id, started_at, status, message) VALUES (?, ?, ?, ?)', (run_id, now_iso(), 'running', 'Início'))
    try:
        inputs = load_all_inputs()
        municipios = ensure_municipality(inputs.get('municipios', pd.DataFrame()))
        populacao = inputs.get('populacao', pd.DataFrame())
        # Em produção real, municipaliza automaticamente por IBGE quando o CSV local não existir.
        if municipios.empty or str(env('MUNICIPIOS_SOURCE', 'ibge')).lower() == 'ibge':
            ibge_mun = ensure_municipality(get_municipios_operacionais())
            if not ibge_mun.empty:
                municipios = ibge_mun
        if municipios.empty:
            municipios = pd.DataFrame([{'cod_ibge': None, 'municipio': APP_CONFIG.municipio, 'lat': APP_CONFIG.lat, 'lon': APP_CONFIG.lon}])

        # Meteorologia municipal: CSV + previsão em tempo real por município quando habilitada.
        met = ensure_municipality(inputs['meteorologia']) if not inputs['meteorologia'].empty else pd.DataFrame()
        om = pd.DataFrame()
        # Em produção, ligue REFRESH_OPENMETEO=true para complementar CSV com previsão municipal em tempo real.
        # Se houver CSV local e REFRESH_OPENMETEO=false, evita demora por indisponibilidade de rede/API.
        if as_bool(env('USE_OPENMETEO', 'false')) and (met.empty or as_bool(env('REFRESH_OPENMETEO', 'false'))):
            om = fetch_openmeteo_for_municipios(municipios)
        if met.empty and not om.empty:
            met = om
        elif not met.empty and not om.empty:
            met['data'] = pd.to_datetime(met['data'], errors='coerce').dt.date.astype(str)
            om['data'] = pd.to_datetime(om['data'], errors='coerce').dt.date.astype(str)
            keys = ['data','municipio'] + (['cod_ibge'] if 'cod_ibge' in met.columns and 'cod_ibge' in om.columns else [])
            existing = set(map(tuple, met[keys].astype(str).values))
            add = om[~om[keys].astype(str).apply(tuple, axis=1).isin(existing)]
            met = pd.concat([met, add], ignore_index=True)
        met_ind = add_biometeo_indicators(met, SETTINGS)
        write_df(met_ind, 'met_biometeo')

        inmet_alerts = normalize_inmet_alerts(fetch_inmet_alerts())
        if inmet_alerts.empty:
            inmet_alerts = inputs['inmet_alertas']
        inmet_alerts = ensure_municipality(inmet_alerts) if not inmet_alerts.empty else inmet_alerts
        write_df(inmet_alerts, 'inmet_alertas')

        # Qualidade do ar: Copernicus/CAMS em tempo real; fallback CSV local.
        aq_raw = fetch_cams_air_quality_municipal(municipios)
        if aq_raw.empty:
            aq_raw = inputs.get('qualidade_ar', pd.DataFrame())
        aq = add_air_quality_indicators(aq_raw, SETTINGS)
        write_df(aq_raw if aq_raw is not None else pd.DataFrame(), 'raw_qualidade_ar_copernicus')
        write_df(aq, 'qualidade_ar_municipal')

        leitos_raw = load_indicasus_leitos()
        leitos_raw = ensure_municipality(leitos_raw) if not leitos_raw.empty else inputs['indicasus_leitos']
        cap = hospital_capacity(leitos_raw)
        cap_agg = aggregate_capacity(cap)
        write_df(leitos_raw, 'raw_indicasus_leitos')
        write_df(cap, 'hospital_capacidade_unidade')
        write_df(cap_agg, 'hospital_capacidade_agregada')

        # Ocupação real IndicaSUS/BdSES em tempo quase real.
        # Mantém hospital_capacidade_agregada como fallback, mas usa hospital_ocupacao_municipio
        # para o cálculo do estágio quando disponível.
        _run_indicasus_occupancy_update()
        cap_agg = _prepare_ocupacao_cap_agg(cap_agg)

        press = pressure_assistencial(leitos_raw)
        write_df(press, 'epi_pressao_assistencial')

        # V4: SIVEP/SRAG vem do banco local; SINAN, SIM e GAL/LACEN vêm preferencialmente do DW.
        sivep_raw = load_sivep_local()
        if sivep_raw.empty:
            sivep_raw = inputs['sivep_srag']
        lacen_raw = load_dw_gal_lacen()
        if lacen_raw.empty:
            lacen_raw = inputs['lacen_gal']
        sinan_raw = load_dw_sinan_agravos()
        if sinan_raw.empty:
            sinan_raw = inputs['sinan_agravos']
        sim_raw = load_dw_sim_obitos()
        if sim_raw.empty:
            sim_raw = inputs['sim_obitos']

        sivep = sivep_summary(sivep_raw)
        lacen = lacen_summary(lacen_raw)
        sinan = sinan_summary(sinan_raw)
        sim = sim_heat_deaths(sim_raw)
        rumors = score_rumors(inputs['sentinela_rumores'])
        write_df(sivep, 'epi_sivep_srag')
        write_df(lacen, 'lab_lacen_gal')
        write_df(sinan, 'epi_sinan_agravos')
        write_df(sim, 'epi_sim_obitos_calor')
        write_df(rumors, 'sentinela_rumores_score')

        stock = stock_autonomy(inputs['estoque'])
        infra_unit, infra = infrastructure_status(inputs['infraestrutura'])
        busca = active_search(inputs['busca_ativa'])
        com = communication_latency(inputs.get('comunicacao', pd.DataFrame()))
        if com.empty:
            try:
                com = communication_latency(load_csv('comunicacao_csv', []))
            except Exception:
                pass
        write_df(stock, 'ops_estoque_autonomia')
        write_df(infra_unit, 'ops_infraestrutura_unidade')
        write_df(infra, 'ops_infraestrutura_resumo')
        write_df(busca, 'ops_busca_ativa')
        write_df(com, 'ops_comunicacao')

        vuln = vulnerability_index(municipios, populacao)
        write_df(vuln, 'geo_vulnerabilidade_municipal')

        resumo_mun = _build_municipal_summary(met_ind, press, cap_agg, stock, infra, busca, com, sivep, lacen, sim, rumors, aq, vuln, inmet_alerts)
        resumo_mun = _inject_ocupacao_into_summary(resumo_mun)
        write_df(resumo_mun, 'resumo_municipal_atual')
        if not resumo_mun.empty:
            resumo_estado = resumo_mun.sort_values(['score','indice_vulnerabilidade_calor'] if 'indice_vulnerabilidade_calor' in resumo_mun.columns else ['score'], ascending=False).head(1).copy()
            resumo_estado['municipios_monitorados'] = resumo_mun['municipio'].nunique() if 'municipio' in resumo_mun.columns else len(resumo_mun)
            resumo_estado['municipios_laranja_ou_mais'] = int((resumo_mun['score'] >= 2).sum()) if 'score' in resumo_mun.columns else 0
        else:
            resumo_estado = pd.DataFrame([{'municipio': APP_CONFIG.municipio, 'nivel':'verde', 'score':0, 'motivo':'sem dados municipais', 'data_referencia': pd.Timestamp.today().date().isoformat()}])
        write_df(resumo_estado, 'resumo_situacao_atual')

        indicador_row = resumo_estado.tail(1).iloc[0].to_dict()
        # Auditoria dos indicadores municipais principais
        with sqlite_conn() as conn:
            for _, mr in resumo_mun.iterrows():
                for k, v in mr.to_dict().items():
                    if k in ['nivel','motivo','data_referencia','municipio','cod_ibge'] or str(k).startswith('data'):
                        continue
                    try:
                        val = float(v)
                    except Exception:
                        continue
                    conn.execute('INSERT INTO auditoria_indicadores (data_referencia, indicador, valor, nivel, fonte, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                                 (mr.get('data_referencia'), f'{mr.get("municipio","NA")}.{k}', val, mr.get('nivel'), 'pipeline_municipal_integrado', now_iso()))
            for eixo, rec in recommendations_for_stage(str(indicador_row.get('nivel','verde'))):
                conn.execute('INSERT INTO recomendacoes_operacionais (data_referencia, nivel, eixo, recomendacao, created_at) VALUES (?, ?, ?, ?, ?)',
                             (indicador_row.get('data_referencia'), indicador_row.get('nivel'), eixo, rec, now_iso()))

        old = get_previous_level()
        update_current_level(indicador_row.get('data_referencia'), indicador_row.get('nivel'), int(indicador_row.get('score', 0)), indicador_row.get('motivo',''))
        if send_alerts:
            motivos = str(indicador_row.get('motivo','')).split('; ')
            maybe_send_level_change(indicador_row.get('data_referencia'), old, indicador_row.get('nivel'), motivos, indicador_row)

        with sqlite_conn() as conn:
            conn.execute('UPDATE pipeline_runs SET finished_at=?, status=?, message=? WHERE run_id=?', (now_iso(), 'success', f'Nível {indicador_row.get("nivel")}', run_id))
        log.info('Pipeline finalizado. Nível: %s', indicador_row.get('nivel'))
        return {'run_id': run_id, 'status': 'success', 'nivel': indicador_row.get('nivel'), 'score': int(indicador_row.get('score', 0)), 'motivos': str(indicador_row.get('motivo','')).split('; '), 'indicadores': indicador_row}
    except Exception as e:
        log.exception('Erro no pipeline')
        with sqlite_conn() as conn:
            conn.execute('UPDATE pipeline_runs SET finished_at=?, status=?, message=? WHERE run_id=?', (now_iso(), 'error', str(e), run_id))
        raise
