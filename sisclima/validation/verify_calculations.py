# -*- coding: utf-8 -*-
"""
Verificação de cálculos dos módulos sisclima.

Uso:
    python -m sisclima.validation.verify_calculations
    python -m sisclima.validation.verify_calculations --pipeline
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sisclima.core.config import SETTINGS
from sisclima.engines.air_quality import add_air_quality_indicators, pollutant_stage
from sisclima.engines.biometeo import (
    add_biometeo_indicators,
    cumulative_heat_risk,
    heat_index_celsius,
    utci_proxy,
)
from sisclima.engines.epidemiology import pressure_assistencial, sim_heat_deaths
from sisclima.engines.hospital import aggregate_capacity, hospital_capacity
from sisclima.engines.operations import infrastructure_status, stock_autonomy
from sisclima.engines.resilience import resilience_index
from sisclima.engines.sentinel import score_rumors
from sisclima.engines.stages import classify_stage, stage_from_tmax, stage_from_utci


@dataclass
class CheckResult:
    module: str
    test: str
    passed: bool
    expected: str
    actual: str
    note: str = ""


@dataclass
class VerificationReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, module: str, test: str, passed: bool, expected, actual, note: str = ""):
        self.results.append(
            CheckResult(
                module=module,
                test=test,
                passed=passed,
                expected=str(expected),
                actual=str(actual),
                note=note,
            )
        )

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def print_report(self):
        print("=" * 72)
        print("RELATÓRIO DE VERIFICAÇÃO DE CÁLCULOS — SIS Clima-Saúde MT")
        print("=" * 72)
        current = None
        for r in self.results:
            if r.module != current:
                current = r.module
                print(f"\n## {current}")
            status = "OK" if r.passed else "FALHA"
            print(f"  [{status}] {r.test}")
            if not r.passed or r.note:
                print(f"         esperado: {r.expected}")
                print(f"         obtido:   {r.actual}")
                if r.note:
                    print(f"         nota:     {r.note}")
        print("\n" + "=" * 72)
        print(f"TOTAL: {self.passed} OK | {self.failed} FALHA | {len(self.results)} testes")
        print("=" * 72)
        return self.failed == 0


def _approx(a, b, tol=0.15) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, float) and (math.isnan(a) or math.isinf(a)):
        return False
    return abs(float(a) - float(b)) <= tol


def verify_biometeo(report: VerificationReport):
    mod = "biometeo"

    # Heat Index abaixo do limiar NOAA
    hi_low = heat_index_celsius(25.0, 80.0)
    report.add(mod, "Heat Index < 26.7°C retorna Tmax", hi_low == 25.0, 25.0, hi_low)

    # Heat Index conhecido (NOAA, ~30°C / 60% RH → ~33.5°C)
    hi = heat_index_celsius(30.0, 60.0)
    report.add(mod, "Heat Index 30°C/60%RH plausível (32-35°C)", 32 <= hi <= 35, "32-35", round(hi, 2))

    # UTCI proxy manual
    utci = utci_proxy(40.0, 50.0, wind_ms=2.0, radiation_wm2=600.0)
    expected_utci = 40.0 + 0.4 + 1.2 - 1.2
    report.add(mod, "UTCI proxy fórmula manual", _approx(utci, expected_utci), expected_utci, round(utci, 2))

    # Pipeline biometeo com dados sintéticos
    met = pd.DataFrame([
        {"data": "2026-07-01", "municipio": "Teste", "cod_ibge": "5103403",
         "tmax": 42.0, "tmin": 28.0, "umidade_media": 55, "vento_max": 1.5, "radiacao": 700},
        {"data": "2026-07-02", "municipio": "Teste", "cod_ibge": "5103403",
         "tmax": 43.0, "tmin": 29.0, "umidade_media": 50, "vento_max": 1.0, "radiacao": 720},
        {"data": "2026-07-03", "municipio": "Teste", "cod_ibge": "5103403",
         "tmax": 44.0, "tmin": 30.0, "umidade_media": 48, "vento_max": 0.8, "radiacao": 750},
    ])
    out = add_biometeo_indicators(met, SETTINGS)
    report.add(mod, "tmedia calculada (tmax+tmin)/2", "tmedia" in out.columns, True, "tmedia" in out.columns)
    tmedia_d3 = float(out.loc[2, "tmedia"])
    report.add(mod, "tmedia dia 3 = 37.0", _approx(tmedia_d3, 37.0), 37.0, tmedia_d3)

    risco = float(out.loc[2, "risco_cumulativo_3d"])
    report.add(mod, "risco_cumulativo_3d > 0 com Tmax alta", risco > 0, ">0", risco)

    hi_d3 = float(out.loc[2, "heat_index"])
    report.add(mod, "heat_index dia 3 > tmax", hi_d3 > 44.0, ">44", round(hi_d3, 2))


def verify_stages(report: VerificationReport):
    mod = "stages"
    lim_utci = SETTINGS["limiares_calor"]["utci"]
    lim_tmax = SETTINGS["limiares_calor"]["tmax_fallback"]

    s, _ = stage_from_utci(33.0, lim_utci)
    report.add(mod, "UTCI 33 → laranja (score 2)", s == 2, 2, s,
               note="limiar: amarela_max=32, laranja até 38")

    s, _ = stage_from_utci(40.0, lim_utci)
    report.add(mod, "UTCI 40 → vermelha (score 3)", s == 3, 3, s)

    s, _ = stage_from_utci(48.0, lim_utci)
    report.add(mod, "UTCI 48 → roxa (score 4)", s == 4, 4, s)

    s, _ = stage_from_tmax(42.0, lim_tmax)
    report.add(mod, "Tmax 42 → vermelha (score 3)", s == 3, 3, s)

    s, _ = stage_from_tmax(44.0, lim_tmax)
    report.add(mod, "Tmax 44 → roxa (score 4)", s == 4, 4, s)

    # Sem dados essenciais → cinza
    r = classify_stage({}, SETTINGS)
    report.add(mod, "Sem dados → cinza", r.nivel == "cinza", "cinza", r.nivel)

    # Com bloco climático válido
    r = classify_stage({"utci_proxy": 33.0, "tmax": 36.0, "risco_cumulativo_3d": 1.0}, SETTINGS)
    report.add(mod, "UTCI 33 com dados → amarela+", r.score >= 1, ">=1", r.score)

    # Ocupação crítica eleva estágio
    r = classify_stage({
        "utci_proxy": 28.0, "tmax": 35.0, "risco_cumulativo_3d": 0,
        "ocupacao_leitos_pct": 96.0, "pressao_calor_pct": 1.0,
    }, SETTINGS)
    report.add(mod, "Ocupação 96% → vermelha+", r.score >= 3, ">=3", f"{r.score} ({r.nivel})")

    r_proxy = classify_stage({
        "utci_proxy": 28.0, "tmax": 35.0,
        "pressao_calor_pct": 35.0,
        "fonte_pressao": "PROXY_OCUPACAO_INDICASUS_CLIMA",
        "ocupacao_leitos_pct": 50.0,
    }, SETTINGS)
    report.add(mod, "Proxy pressao ignorado na classificação", r_proxy.score < 3, "<3", f"{r_proxy.score} ({r_proxy.nivel})")


def verify_air_quality(report: VerificationReport):
    mod = "air_quality"
    th = SETTINGS["qualidade_ar"]["pm25_ugm3"]

    s, lvl = pollutant_stage(20.0, th)
    report.add(mod, "PM2.5 20 → amarela", s == 1 and lvl == "amarela", "amarela/1", f"{lvl}/{s}")

    s, lvl = pollutant_stage(60.0, th)
    report.add(mod, "PM2.5 60 → vermelha", s == 3 and lvl == "vermelha", "vermelha/3", f"{lvl}/{s}")

    aq = add_air_quality_indicators(pd.DataFrame([{
        "data": "2026-07-01", "municipio": "Teste", "cod_ibge": "5103403",
        "pm25_ugm3": 30.0, "pm10_ugm3": 80.0, "o3_ugm3": 50.0,
    }]), SETTINGS)
    report.add(mod, "iq_ar_score = 2 (laranja) para PM2.5=30", int(aq.iloc[0]["iq_ar_score"]) == 2, 2, int(aq.iloc[0]["iq_ar_score"]))
    report.add(mod, "poluente dominante = PM2.5", aq.iloc[0]["poluente_dominante"] == "PM2.5", "PM2.5", aq.iloc[0]["poluente_dominante"])


def verify_hospital(report: VerificationReport):
    mod = "hospital"
    df = pd.DataFrame([{
        "data": "2026-07-01", "municipio": "Teste", "cod_ibge": "5103403",
        "unidade": "Hosp A", "tipo_leito": "clinico",
        "leitos_sus": 100, "leitos_ocupados": 90,
    }])
    cap = hospital_capacity(df)
    occ = float(cap.iloc[0]["ocupacao_pct"])
    report.add(mod, "ocupacao_pct = 90%", _approx(occ, 90.0), 90.0, occ)
    report.add(mod, "nivel_ocupacao = laranja (85-95%)", cap.iloc[0]["nivel_ocupacao"] == "laranja", "laranja", cap.iloc[0]["nivel_ocupacao"])

    agg = aggregate_capacity(cap)
    report.add(mod, "agregação preserva leitos_total=100", float(agg.iloc[0]["leitos_total"]) == 100, 100, agg.iloc[0]["leitos_total"])

    # Sem ocupação → NaN, não zero forçado
    df2 = pd.DataFrame([{
        "data": "2026-07-01", "municipio": "Teste", "cod_ibge": "5103403",
        "unidade": "Hosp B", "tipo_leito": "clinico", "leitos_sus": 50,
    }])
    cap2 = hospital_capacity(df2)
    report.add(mod, "sem ocupação → ocupacao_pct NaN", pd.isna(cap2.iloc[0]["ocupacao_pct"]), "NaN", cap2.iloc[0]["ocupacao_pct"])


def verify_epidemiology(report: VerificationReport):
    mod = "epidemiology"
    df = pd.DataFrame([{
        "data": "2026-07-01", "municipio": "Cuiabá", "cod_ibge": "5103403",
        "atendimentos_total": 100, "atendimentos_calor": 8,
    }])
    press = pressure_assistencial(df)
    pct = float(press.iloc[0]["pressao_calor_pct"])
    report.add(mod, "pressao_calor_pct = 8%", _approx(pct, 8.0), 8.0, pct)

    sim = sim_heat_deaths(pd.DataFrame([{
        "data_obito": "2026-07-01", "municipio": "Cuiabá", "cod_ibge": "5103403",
        "cid": "T67", "numero_obitos": 2,
    }]))
    report.add(mod, "CID T67 → obitos_calor_suspeitos=2", int(sim.iloc[0]["obitos_calor_suspeitos"]) == 2, 2, sim.iloc[0]["obitos_calor_suspeitos"])

    sim2 = sim_heat_deaths(pd.DataFrame([{
        "data_obito": "2026-07-01", "municipio": "Cuiabá", "cod_ibge": "5103403",
        "cid": "J18", "numero_obitos": 1,
    }]))
    report.add(mod, "CID J18 → obitos_calor_suspeitos=1", int(sim2.iloc[0]["obitos_calor_suspeitos"]) == 1, 1, sim2.iloc[0]["obitos_calor_suspeitos"])


def verify_operations(report: VerificationReport):
    mod = "operations"
    stock = stock_autonomy(pd.DataFrame([{
        "data": "2026-07-01", "municipio": "Teste", "cod_ibge": "5103403",
        "item": "soro", "estoque_total": 70, "consumo_medio_diario": 10,
    }]))
    aut = float(stock.iloc[0]["autonomia_dias"])
    report.add(mod, "autonomia = estoque/consumo = 7 dias", _approx(aut, 7.0), 7.0, aut)

    _, infra = infrastructure_status(pd.DataFrame([
        {"data": "2026-07-01", "municipio": "Teste", "cod_ibge": "5103403", "unidade": "A",
         "energia_ok": 1, "agua_ok": 1, "climatizacao_ok": 1, "gerador_ok": 1},
        {"data": "2026-07-01", "municipio": "Teste", "cod_ibge": "5103403", "unidade": "B",
         "energia_ok": 0, "agua_ok": 1, "climatizacao_ok": 1, "gerador_ok": 1},
    ]))
    pct = float(infra.iloc[0]["falhas_infra_pct"])
    report.add(mod, "falhas_infra_pct = 50% (1/2 unidades)", _approx(pct, 50.0), 50.0, pct)


def verify_resilience(report: VerificationReport):
    mod = "resilience"
    r = resilience_index({
        "ocupacao_leitos_pct": 80.0,
        "autonomia_min_dias": 14.0,
        "falhas_infra_pct": 0.0,
        "cobertura_busca_pct": 100.0,
        "latencia_comunicacao_horas": 1.5,
    }, SETTINGS["pesos_resiliencia"])
    report.add(mod, "indice_resiliencia alto com bons indicadores", r["indice_resiliencia"] >= 80, ">=80", r["indice_resiliencia"],
               note="ocupação 80% pesa 20 pts em capacidade_leitos")

    r2 = resilience_index({
        "ocupacao_leitos_pct": 98.0,
        "autonomia_min_dias": 2.0,
        "falhas_infra_pct": 30.0,
        "cobertura_busca_pct": 20.0,
        "latencia_comunicacao_horas": 8.0,
    }, SETTINGS["pesos_resiliencia"])
    report.add(mod, "indice_resiliencia baixo com indicadores ruins", r2["indice_resiliencia"] < 40, "<40", r2["indice_resiliencia"])


def verify_sentinel(report: VerificationReport):
    mod = "sentinel"
    df = pd.DataFrame([{
        "data_captura": "2026-07-01", "municipio": "Cuiabá", "cod_ibge": "5103403",
        "texto": "Hospital lotado e óbito por calor na UPA",
    }])
    out = score_rumors(df)
    score = int(out.iloc[0]["score_sentinela"])
    report.add(mod, "rumor crítico score >= 9", score >= 9, ">=9", score,
               note="keywords: hospital lotado(4) + obito(5)")


def verify_sample_data_integration(report: VerificationReport):
    mod = "integração (data/sample)"
    input_dir = ROOT / "data" / "input"
    if not (input_dir / "meteorologia.csv").exists():
        report.add(mod, "data/input preparado", False, "existe", "ausente",
                   note="Execute: cp data/sample/*.csv data/input/")
        return

    met = pd.read_csv(input_dir / "meteorologia.csv")
    cuiaba = met[met["municipio"].str.contains("Cuiab", case=False, na=False)].copy()
    report.add(mod, "meteorologia Cuiabá tem registros", len(cuiaba) > 0, ">0", len(cuiaba))

    out = add_biometeo_indicators(cuiaba, SETTINGS)
    report.add(mod, "biometeo produz utci_proxy", out["utci_proxy"].notna().any(), True, out["utci_proxy"].notna().sum())

    max_tmax = float(out["tmax"].max())
    max_utci = float(out["utci_proxy"].max())
    max_risco = float(out["risco_cumulativo_3d"].max())
    report.add(mod, "Tmax máxima plausível (30-45°C)", 30 <= max_tmax <= 45, "30-45", round(max_tmax, 1))
    report.add(mod, "UTCI máx plausível (30-50)", 30 <= max_utci <= 50, "30-50", round(max_utci, 1))
    report.add(mod, "risco_cumulativo_3d não zerado globalmente", max_risco > 0, ">0", round(max_risco, 2))

    leitos = pd.read_csv(input_dir / "indicasus_leitos.csv")
    cap = hospital_capacity(leitos)
    report.add(mod, "hospital_capacity processa indicasus", len(cap) > 0, ">0", len(cap))

    occ_valid = cap["ocupacao_pct"].notna().sum()
    report.add(mod, "ocupacao_pct disponível em indicasus", occ_valid > 0, ">0", occ_valid)

    press = pressure_assistencial(leitos)
    max_pressao = float(press["pressao_calor_pct"].max()) if not press.empty else 0
    report.add(mod, "pressao_calor_pct calculada", max_pressao > 0, ">0", round(max_pressao, 2))


def verify_public_csv_stage_recalc(report: VerificationReport):
    """Recalcula estágio a partir do CSV publicado e compara com nivel gravado."""
    mod = "revalidação estágios (data/public)"
    public = ROOT / "data" / "public" / "resumo_municipal_atual.csv"
    if not public.exists():
        return

    df = pd.read_csv(public)
    nivel_map = {"cinza": 0, "verde": 0, "amarela": 1, "laranja": 2, "vermelha": 3, "roxa": 4}
    mismatches = []

    for _, row in df.iterrows():
        from sisclima.pipeline import _prepare_latest_for_stage
        latest = _prepare_latest_for_stage(row.to_dict())
        recalc = classify_stage(latest, SETTINGS)
        stored_score = int(row.get("score", -1))
        stored_nivel = str(row.get("nivel", ""))
        if nivel_map.get(stored_nivel, -1) != recalc.score:
            mismatches.append(row.get("municipio"))

    report.add(
        mod,
        "estágios recalculados batem com CSV publicado",
        len(mismatches) <= 5,
        f"<=5 divergências",
        f"{len(mismatches)} divergências",
        note=f"Exemplos: {mismatches[:3]}" if mismatches else "consistente",
    )

    proxy_count = 0
    if "fonte_pressao" in df.columns:
        proxy_count = df["fonte_pressao"].astype(str).str.contains("PROXY", case=False, na=False).sum()
    report.add(
        mod,
        "sem fonte_pressao proxy ativa",
        proxy_count == 0,
        0,
        proxy_count,
    )


def verify_pipeline_integration(report: VerificationReport):
    mod = "pipeline (end-to-end)"
    try:
        from sisclima.pipeline import run_pipeline
        from sisclima.core.db import read_table, sqlite_path_from_url

        db_backup = ROOT / "data" / "output" / "sis_integrado_verify_backup.db"
        db_target = sqlite_path_from_url()
        if db_target.exists():
            import shutil
            shutil.copy2(db_target, db_backup)

        result = run_pipeline(send_alerts=False)
        report.add(mod, "run_pipeline status success", result.get("status") == "success", "success", result.get("status"))
        report.add(mod, "nivel retornado válido", result.get("nivel") in {"verde", "amarela", "laranja", "vermelha", "roxa", "cinza"},
                   "nível válido", result.get("nivel"))

        resumo = read_table("resumo_municipal_atual")
        report.add(mod, "resumo_municipal_atual gerado", not resumo.empty, ">0 linhas", len(resumo))

        if not resumo.empty:
            niveis = set(resumo["nivel"].dropna().unique())
            report.add(mod, "níveis no resumo são válidos", niveis.issubset({"verde", "amarela", "laranja", "vermelha", "roxa", "cinza"}),
                       "válidos", niveis)
            report.add(mod, "score entre 0-4", resumo["score"].between(0, 4).all(), "0-4", f"min={resumo['score'].min()} max={resumo['score'].max()}")

            # Consistência: score deve corresponder ao nível
            nivel_score_map = {"cinza": 0, "verde": 0, "amarela": 1, "laranja": 2, "vermelha": 3, "roxa": 4}
            inconsistent = resumo[resumo.apply(
                lambda r: nivel_score_map.get(str(r["nivel"]), -1) != int(r["score"]), axis=1
            )]
            report.add(mod, "nível ↔ score consistentes", inconsistent.empty, "0 inconsistências",
                       f"{len(inconsistent)} inconsistências")

        met = read_table("met_biometeo")
        report.add(mod, "met_biometeo gravado", not met.empty, ">0", len(met))

        if db_backup.exists():
            import shutil
            shutil.move(db_backup, db_target)

    except Exception as exc:
        report.add(mod, "run_pipeline sem exceção", False, "ok", type(exc).__name__, note=str(exc))


def verify_public_csv_consistency(report: VerificationReport):
    mod = "consistência data/public"
    public = ROOT / "data" / "public"
    resumo = public / "resumo_municipal_atual.csv"
    if not resumo.exists():
        report.add(mod, "resumo_municipal_atual.csv existe", False, True, False)
        return

    df = pd.read_csv(resumo)
    report.add(mod, "142 municípios no resumo publicado", len(df) == 142, 142, len(df))

    if "nivel" in df.columns:
        dist = df["nivel"].value_counts().to_dict()
        report.add(mod, "distribuição de níveis presente", len(dist) > 0, ">0", dist)

    if {"utci_proxy", "tmax", "risco_cumulativo_3d"}.issubset(df.columns):
        climate_ok = df["utci_proxy"].notna().sum()
        report.add(mod, "utci_proxy preenchido no CSV publicado", climate_ok > 100, ">100", climate_ok)

    if "ocupacao_leitos_pct" in df.columns:
        occ = df["ocupacao_leitos_pct"].dropna()
        report.add(mod, "ocupacao_leitos_pct entre 0-150%", occ.between(0, 150).all() if not occ.empty else True,
                   "0-150%", f"min={occ.min():.1f} max={occ.max():.1f}" if not occ.empty else "vazio")


def run_all(include_pipeline: bool = False) -> bool:
    report = VerificationReport()
    verify_biometeo(report)
    verify_stages(report)
    verify_air_quality(report)
    verify_hospital(report)
    verify_epidemiology(report)
    verify_operations(report)
    verify_resilience(report)
    verify_sentinel(report)
    verify_sample_data_integration(report)
    verify_public_csv_consistency(report)
    verify_public_csv_stage_recalc(report)
    if include_pipeline:
        verify_pipeline_integration(report)
    return report.print_report()


def main():
    parser = argparse.ArgumentParser(description="Verifica cálculos dos módulos sisclima")
    parser.add_argument("--pipeline", action="store_true", help="Inclui teste end-to-end do pipeline")
    args = parser.parse_args()
    ok = run_all(include_pipeline=args.pipeline)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
