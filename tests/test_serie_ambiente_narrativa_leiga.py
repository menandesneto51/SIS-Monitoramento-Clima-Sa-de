# -*- coding: utf-8 -*-
"""Narrativa legível da comparação sazonal ambiental (mesmo período calendário)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from sisclima.engines.serie_historica_ambiente import comparar_janela_atual


def _serie_sintetica(*, tmax_setembro_atual: float = 33.0, umid_setembro_atual: float = 70.0) -> pd.DataFrame:
    rows: list[dict] = []
    # Histórico: setembros 2020–2025 mais quentes e mais secos (com dispersão)
    for ano in range(2020, 2026):
        for dia in range(1, 31):
            jitter = ((ano - 2020) * 0.15) + (dia % 5) * 0.1
            rows.append(
                {
                    "data": date(ano, 9, min(dia, 30)),
                    "tmax_media": 35.5 + jitter,
                    "tmax_max": 38.0 + jitter,
                    "utci_proxy_media": 34.0 + jitter * 0.5,
                    "umidade_media_media": 55.0 - jitter,
                    "risco_cumulativo_3d_media": 2.0,
                }
            )
    # Setembro atual (parcial) + janela recente
    hoje = date.today()
    for i in range(20):
        d = hoje - timedelta(days=i + 1)
        rows.append(
            {
                "data": d,
                "tmax_media": tmax_setembro_atual if d.month == 9 else 31.0,
                "tmax_max": 39.0 if d.month == 9 else 33.0,
                "utci_proxy_media": 32.0,
                "umidade_media_media": umid_setembro_atual if d.month == 9 else 50.0,
                "risco_cumulativo_3d_media": 3.0,
            }
        )
    return pd.DataFrame(rows)


def test_narrativa_mesmo_periodo_e_mes():
    out = comparar_janela_atual(_serie_sintetica())
    assert out["ok"] is True
    assert out.get("comparacao_mesmo_periodo") is True
    periodo = out["periodo_cmp"]
    assert periodo.get("ok") is True
    assert len(periodo.get("anos_historico") or []) >= 2
    narr = out["narrativa"]
    assert "mesmo período" in narr.lower() or "mesmos dias do calendário" in narr.lower()
    assert "restante da série" not in narr.lower()
    assert "meses misturados" not in narr.lower() or "Não** se usa" in narr or "Não se usa" in narr

    mes = out["mes_cmp"]
    assert mes.get("ok") is True
    assert mes.get("houve_desvio") is True
    assert "Tmáx média (°C)" in mes.get("variaveis_com_desvio", [])
    assert "Houve desvio de sazonalidade?" in narr
    assert "**Sim**" in narr


def test_sem_anos_anteriores_nao_mistura_meses():
    # Só 2026 — sem histórico multi-anual
    hoje = date.today()
    rows = []
    for i in range(40):
        d = hoje - timedelta(days=i + 1)
        rows.append(
            {
                "data": d,
                "tmax_media": 34.0,
                "tmax_max": 38.0,
                "utci_proxy_media": 33.0,
                "umidade_media_media": 50.0,
                "risco_cumulativo_3d_media": 2.0,
            }
        )
    out = comparar_janela_atual(pd.DataFrame(rows))
    assert out["ok"] is True
    assert out.get("comparacao_mesmo_periodo") is False
    narr = out["narrativa"].lower()
    assert "indisponível" in narr
    assert "restante da série" not in narr
    assert "meses misturados" in narr


def test_ytd_historico_agrega_por_ano_nao_por_dia():
    """Bugbot: YTD não pode ponderar anos com mais dias diários."""
    from sisclima.engines.serie_historica_ambiente import _agg_atual_hist, _zscore_atual_hist

    rows: list[dict] = []
    rows += [
        {"data": date(2024, 1, 1), "tmax_media": 10.0},
        {"data": date(2024, 1, 2), "tmax_media": 30.0},
    ]
    rows += [{"data": date(2025, 1, d), "tmax_media": 40.0} for d in range(1, 31)]
    hist = pd.DataFrame(rows)
    atual = pd.DataFrame([{"data": date(2026, 1, 1), "tmax_media": 25.0}])
    pool = _agg_atual_hist(atual, hist, "tmax_media", hist_por_ano=False)
    ano = _agg_atual_hist(atual, hist, "tmax_media", hist_por_ano=True)
    assert pool is not None and ano is not None
    assert abs(ano[1] - 30.0) < 0.01
    assert abs(pool[1] - 38.75) < 0.01
    z = _zscore_atual_hist(atual, hist, "tmax_media", hist_por_ano=True)
    assert z is not None
    assert abs(z["media_historica_mesmo_periodo"] - 30.0) < 0.01


def test_tmax_max_z_alinha_com_historico_exibido():
    """z de Tmáx máxima usa média dos picos anuais (mesmo μ do valor histórico)."""
    from sisclima.engines.serie_historica_ambiente import _agg_atual_hist, _zscore_atual_hist

    rows: list[dict] = []
    # Picos anuais no recorte: 41, 40, 39 → μ=40
    for ano, pico in ((2023, 41.0), (2024, 40.0), (2025, 39.0)):
        for d in range(1, 8):
            rows.append({"data": date(ano, 9, d), "tmax_max": pico - 2.0 + d * 0.1})
        rows.append({"data": date(ano, 9, 8), "tmax_max": pico})
    hist = pd.DataFrame(rows)
    atual = pd.DataFrame([{"data": date(2026, 9, d), "tmax_max": 39.5} for d in range(1, 8)])
    pair = _agg_atual_hist(atual, hist, "tmax_max")
    z = _zscore_atual_hist(atual, hist, "tmax_max")
    assert pair is not None and z is not None
    assert abs(pair[1] - 40.0) < 0.01
    assert abs(z["media_historica_mesmo_periodo"] - 40.0) < 0.01
    # 39.5 < 40 → z negativo
    assert z["zscore"] < 0
    assert abs(pair[0] - z["atual"]) < 0.01


def test_mensagem_operacional_quando_sem_desvio():
    out = comparar_janela_atual(_serie_sintetica(tmax_setembro_atual=35.5, umid_setembro_atual=55.0))
    assert out["ok"] is True
    periodo = out.get("periodo_cmp") or {}
    narr = out.get("narrativa") or ""
    lamina = out.get("markdown_lamina") or ""
    assert "baseline operacional recente" in narr.lower() or "Mensagem operacional" in narr
    assert "Semáforo analítico" in narr or "semaforo" in narr.lower()
    if periodo.get("ok") and not periodo.get("houve_desvio"):
        assert "|z| < 1" in narr or "dentro da variabilidade" in narr.lower()
    assert "Atenção à interpretação" in narr or "não substitui" in lamina.lower()
    assert "saúde" in narr.lower()
    assert lamina  # lâmina compacta para Sala
    assert "Indicadores-chave" in lamina
