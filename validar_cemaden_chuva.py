# -*- coding: utf-8 -*-
"""Validação rápida: Cemaden + precipitação Open-Meteo."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"), override=True)

from sisclima.core.config import as_bool, env
from sisclima.ingestion.cemaden import fetch_cemaden_alerts, normalize_cemaden_alerts
from sisclima.ingestion.openmeteo import fetch_openmeteo_forecast


def main() -> int:
    print("USE_CEMADEN=", env("USE_CEMADEN", "true"))
    print("CEMADEN_SSL_VERIFY=", env("CEMADEN_SSL_VERIFY", env("ALERT_SSL_VERIFY", "true")))
    raw = fetch_cemaden_alerts()
    print("cemaden_raw_rows=", len(raw))
    norm = normalize_cemaden_alerts(raw)
    print("cemaden_norm_rows=", len(norm))
    if not norm.empty:
        print(norm[["municipio", "uf", "tipo_risco", "nivel_alerta", "nivel_sis"]].head(10).to_string(index=False))
    else:
        print("Sem alertas Cemaden para a UF (pode ser normal se não houver alerta aberto).")

    if as_bool(env("USE_OPENMETEO", "false"), False):
        om = fetch_openmeteo_forecast(days=3)
        print("openmeteo_rows=", len(om))
        cols = [c for c in ["data", "tmax", "precipitacao_mm", "chuva_mm"] if c in om.columns]
        if cols:
            print(om[cols].head(5).to_string(index=False))
        assert "precipitacao_mm" in om.columns or om.empty, "Open-Meteo sem precipitacao_mm"
    else:
        print("Open-Meteo desligado (USE_OPENMETEO=false); pulando teste de chuva.")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
