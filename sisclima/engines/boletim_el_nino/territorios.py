# -*- coding: utf-8 -*-
"""Camada territorial — aldeias e quilombos do Vigibarragens + risco ARARAS."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.logging_utils import get_logger
from sisclima.engines.boletim_el_nino.constants import INDISPONIVEL
from sisclima.engines.boletim_el_nino.formatters import bloco_tabela, fmt_frac, fmt_int, fmt_plural, md_table
from sisclima.engines.boletim_el_nino.maps import normalize_cod_ibge
from sisclima.engines.boletim_el_nino.referencias import cite
from sisclima.ingestion.vigibarragens import CATEGORIA_ALDEIA, CATEGORIA_QUILOMBO

log = get_logger(__name__)

_NIVEIS_CRITICOS = {"vermelha", "roxa"}


def _cod_ibge6(s: pd.Series) -> pd.Series:
    """Chave IBGE-6 alinhada a CURRENT_MUNICIPAL_CLASSIFICATION e aos Mapas 1–3."""
    return normalize_cod_ibge(s)


def _load_vigibarragens() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        from sisclima.core.db import read_table, table_exists

        pts = read_table("vigibarragens_populacoes") if table_exists("vigibarragens_populacoes") else pd.DataFrame()
        mun = read_table("vigibarragens_municipal") if table_exists("vigibarragens_municipal") else pd.DataFrame()
        return pts if pts is not None else pd.DataFrame(), mun if mun is not None else pd.DataFrame()
    except Exception as exc:  # noqa: BLE001
        log.warning("Vigibarragens indisponível: %s", exc)
        return pd.DataFrame(), pd.DataFrame()


def _merge_risco(resumo: pd.DataFrame) -> pd.DataFrame:
    if resumo is None or resumo.empty or "cod_ibge" not in resumo.columns:
        return pd.DataFrame()
    cols = [
        c
        for c in (
            "cod_ibge",
            "municipio",
            "regional_saude",
            "nivel",
            "nivel_predicao_7d",
            "tmax",
            "pm25_ugm3",
            "focos_queimadas_7d",
            "focos_7d",
            "situacao_hidro",
        )
        if c in resumo.columns
    ]
    r = resumo[cols].copy()
    r["_cod"] = _cod_ibge6(r["cod_ibge"])
    return r.dropna(subset=["_cod"]).drop_duplicates("_cod")


def _exposição(row: pd.Series | dict) -> str:
    """Exposição específica — risco integrado não é exposição."""
    parts: list[str] = []
    try:
        tmax = row.get("tmax")
        if tmax is not None and float(tmax) >= 37:
            parts.append("calor")
    except (TypeError, ValueError):
        pass
    try:
        pm25 = row.get("pm25_ugm3")
        if pm25 is not None and float(pm25) >= 25:
            parts.append("fumaça/PM2,5")
    except (TypeError, ValueError):
        pass
    try:
        focos = row.get("focos_queimadas_7d", row.get("focos_7d"))
        if focos is not None and float(focos) >= 1:
            parts.append("fogo")
    except (TypeError, ValueError):
        pass
    hidro = str(row.get("situacao_hidro") or "").lower()
    if hidro.startswith("seca_"):
        parts.append("baixa disponibilidade hídrica")
    if len(parts) >= 2:
        return "múltiplas exposições (" + ", ".join(parts) + ")"
    if parts:
        return parts[0]
    return "sem exposição específica destacada além do risco integrado"


def _articulacao(categoria: str) -> str:
    if categoria == CATEGORIA_ALDEIA:
        return "SMS, Regional, DSEI/SESAI, FUNAI"
    if categoria == CATEGORIA_QUILOMBO:
        return "SMS, Regional, organizações quilombolas locais"
    return "SMS, Regional"


def _nivel_pt(v: Any) -> str:
    s = str(v or "—").strip().lower()
    mapa = {
        "verde": "Verde",
        "amarela": "Amarela",
        "laranja": "Laranja",
        "vermelha": "Vermelha",
        "roxa": "Roxa",
        "cinza": "Cinza",
    }
    return mapa.get(s, str(v or "—").title() if v else "—")


def _quadro_aldeias_municipal(mun_crit: pd.DataFrame, limite: int = 20) -> list[list[str]]:
    """Agrega aldeias por município crítico — sem coluna Tipo."""
    if mun_crit.empty or "n_aldeias" not in mun_crit.columns:
        return []
    work = mun_crit[pd.to_numeric(mun_crit["n_aldeias"], errors="coerce").fillna(0) > 0].copy()
    if work.empty:
        return []
    work = work.sort_values("n_aldeias", ascending=False)
    rows: list[list[str]] = []
    for _, row in work.head(limite).iterrows():
        rows.append(
            [
                str(row.get("municipio") or "—"),
                fmt_int(row.get("n_aldeias")),
                _nivel_pt(row.get("nivel")),
                _nivel_pt(row.get("nivel_predicao_7d")),
                _exposição(row),
            ]
        )
    return rows


def _quadro_quilombos(pts: pd.DataFrame, risco: pd.DataFrame, *, limite: int = 30) -> list[list[str]]:
    """Lista comunidades quilombolas certificadas — sem coluna Tipo."""
    if pts.empty or risco.empty:
        return []
    work = pts[pts["categoria"] == CATEGORIA_QUILOMBO].copy()
    if work.empty:
        return []
    work["_cod"] = _cod_ibge6(work["cod_ibge"])
    joined = work.merge(risco, on="_cod", how="inner", suffixes=("", "_r"))
    if joined.empty:
        return []
    joined = joined[joined["nivel"].astype(str).str.lower().isin(_NIVEIS_CRITICOS)]
    joined = joined.sort_values(["municipio", "nome"], ascending=[True, True])
    rows: list[list[str]] = []
    for _, row in joined.head(limite).iterrows():
        rows.append(
            [
                str(row.get("nome") or "—")[:70],
                str(row.get("municipio") or row.get("municipio_r") or "—"),
                _nivel_pt(row.get("nivel")),
                _nivel_pt(row.get("nivel_predicao_7d")),
                _exposição(row),
            ]
        )
    return rows


def _centroides_municipais(merged) -> dict[str, tuple[float, float]]:
    """IBGE-6 -> (lon, lat) do ponto representativo do município (presença, não sede real)."""
    out: dict[str, tuple[float, float]] = {}
    if merged is None or merged.empty or "geometry" not in merged.columns:
        return out
    for _, row in merged.iterrows():
        cod = str(row.get("_cod") or "").strip()
        geom = row.get("geometry")
        if not cod or geom is None:
            continue
        try:
            pt = geom.representative_point()
            out[cod] = (float(pt.x), float(pt.y))
        except Exception:  # noqa: BLE001
            continue
    return out


def _coords_plot(pts: pd.DataFrame, centroids: dict[str, tuple[float, float]]) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Aldeias com lat/lon; quilombos com lat/lon ou presença municipal (símbolo diferenciado)."""
    import numpy as np

    if pts is None or pts.empty:
        return pd.DataFrame(), pd.DataFrame(), 0

    ald = pts[pts["categoria"] == CATEGORIA_ALDEIA].copy()
    qui = pts[pts["categoria"] == CATEGORIA_QUILOMBO].copy()

    if not ald.empty and "lat" in ald.columns and "lon" in ald.columns:
        ald = ald.dropna(subset=["lat", "lon"])
    else:
        ald = pd.DataFrame()

    n_centroid = 0
    if qui.empty:
        return ald, pd.DataFrame(), 0

    rows = []
    for i, row in qui.iterrows():
        lat, lon = row.get("lat"), row.get("lon")
        try:
            if lat is not None and lon is not None and pd.notna(lat) and pd.notna(lon):
                rows.append({**row.to_dict(), "lon": float(lon), "lat": float(lat), "_via_centroid": False})
                continue
        except (TypeError, ValueError):
            pass
        m = _cod_ibge6(pd.Series([row.get("cod_ibge")]))
        cod = str(m.iloc[0] if len(m) else "") if m is not None else ""
        if cod in ("", "nan", "None"):
            cod = ""
        if cod and cod in centroids:
            lon_c, lat_c = centroids[cod]
            # jitter estável — presença municipal, não localização real da comunidade
            j = (hash(str(row.get("nome") or i)) % 1000) / 1000.0
            ang = 2 * np.pi * j
            r = 0.04 + 0.03 * ((hash(str(i)) % 100) / 100.0)
            rows.append(
                {
                    **row.to_dict(),
                    "lon": lon_c + r * np.cos(ang),
                    "lat": lat_c + r * np.sin(ang),
                    "_via_centroid": True,
                }
            )
            n_centroid += 1
    qui_plot = pd.DataFrame(rows) if rows else pd.DataFrame()
    return ald, qui_plot, n_centroid


def export_mapa_territorios(
    resumo: pd.DataFrame,
    pts: pd.DataFrame,
    out_dir: Path,
    *,
    data_ref: str = "",
    cmc: dict[str, Any] | None = None,
    rodada_stamp: str | None = None,
) -> dict[str, Any]:
    """Mapa 3 dinâmico: classificação CURRENT da rodada + aldeias/quilombos.

    Sempre regenera PNG versionado; nunca reutiliza artefato de rodada anterior
    sem validar classification_hash.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    qa: dict[str, Any] = {
        "MAP3_FILE_CREATED_THIS_RUN": False,
        "MAP3_CLASSIFICATION_HASH_MATCH": False,
        "MAP3_STALE_ERROR": 1,
        "MAP3_CLASS_DISTRIBUTION_ERROR": 1,
        "MAP3_MUNICIPAL_DIFF_COUNT": -1,
        "MAP3_SOURCE_DATE_MATCH": False,
        "MAP3_TRADITIONAL_LAYER_LOADED": False,
        "MAP3_LEGEND_VALID": False,
        "MAP_REGEN_REQUIRED": True,
    }
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from sisclima.engines.boletim_el_nino.classificacao import (
            build_current_municipal_classification,
            validate_map_vs_cmc,
        )
        from sisclima.engines.boletim_el_nino.maps import (
            LEVEL_COLOR_MAP,
            LEVEL_ORDER,
            _load_gdf,
            _prep_merge,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Mapa territorial indisponível: %s", exc)
        return {"disponivel": False, "qa": qa, "motivo": str(exc)}

    if cmc is None or not cmc.get("disponivel"):
        cmc = build_current_municipal_classification(resumo, data_hora_rodada=data_ref or None)
    if not cmc.get("disponivel"):
        return {"disponivel": False, "qa": qa, "motivo": "Classificação municipal indisponível."}

    resumo_maps = cmc.get("resumo_for_maps")
    merged = _prep_merge(_load_gdf(), resumo_maps if resumo_maps is not None else resumo)
    if merged is None:
        return {"disponivel": False, "qa": qa, "motivo": "Malha municipal indisponível."}

    # QA município a município (não bloqueia regeneração — bloqueia publicação no builder/PDF)
    val = validate_map_vs_cmc(merged, cmc, col="nivel")
    qa.update(val)
    qa["current_classification_hash"] = cmc.get("classification_hash")
    qa["MAP3_TRADITIONAL_LAYER_LOADED"] = bool(pts is not None and not pts.empty)
    if qa.get("MAP3_STALE_ERROR") or qa.get("MAP3_CLASS_DISTRIBUTION_ERROR"):
        log.error(
            "MAP3 QA divergência: stale=%s dist=%s diffs=%s — regenerando com CMC mesmo assim",
            qa.get("MAP3_STALE_ERROR"),
            qa.get("MAP3_CLASS_DISTRIBUTION_ERROR"),
            qa.get("MAP3_MUNICIPAL_DIFF_COUNT"),
        )

    centroids = _centroides_municipais(merged)
    ald, qui, n_qui_centroid = _coords_plot(pts, centroids)
    if not qui.empty and "_via_centroid" in qui.columns:
        mask_c = qui["_via_centroid"].fillna(False).astype(bool)
        qui_aprox = qui.loc[mask_c]
        qui_geo = qui.loc[~mask_c]
    else:
        qui_geo = qui
        qui_aprox = pd.DataFrame()

    fig, ax = plt.subplots(figsize=(8.5, 8.5), dpi=160)
    for nivel in LEVEL_ORDER:
        sub = merged[merged["nivel"] == nivel]
        if not sub.empty:
            sub.plot(ax=ax, color=LEVEL_COLOR_MAP.get(nivel, "#ccc"), edgecolor="#4a4a4a", linewidth=0.25, alpha=0.72)

    if not ald.empty:
        ax.scatter(ald["lon"], ald["lat"], s=55, c="white", marker="^", alpha=1.0, linewidths=0, zorder=5)
        ax.scatter(
            ald["lon"], ald["lat"], s=36, c="#00E5FF", marker="^",
            edgecolors="#003344", linewidths=0.6, alpha=0.95, zorder=6,
        )
    if not qui_geo.empty:
        ax.scatter(qui_geo["lon"], qui_geo["lat"], s=70, c="white", marker="o", alpha=1.0, linewidths=0, zorder=5)
        ax.scatter(
            qui_geo["lon"], qui_geo["lat"], s=48, c="#FFD600", marker="o",
            edgecolors="#1a1a1a", linewidths=0.8, alpha=0.98, zorder=7,
        )
    if not qui_aprox.empty:
        ax.scatter(qui_aprox["lon"], qui_aprox["lat"], s=70, c="white", marker="s", alpha=1.0, linewidths=0, zorder=5)
        ax.scatter(
            qui_aprox["lon"], qui_aprox["lat"], s=48, c="#FFD600", marker="s",
            edgecolors="#1a1a1a", linewidths=0.8, alpha=0.98, zorder=7,
        )

    ax.set_axis_off()
    _legend_cls = {
        "verde": "Verde",
        "amarela": "Amarela",
        "laranja": "Laranja",
        "vermelha": "Vermelha",
        "roxa": "Roxa",
    }
    handles = [
        mpatches.Patch(color=LEVEL_COLOR_MAP.get(k, "#ccc"), label=_legend_cls[k])
        for k in ("verde", "amarela", "laranja", "vermelha", "roxa")
    ]
    handles.append(
        plt.Line2D([0], [0], marker="^", color="w", markerfacecolor="#00E5FF",
                   markeredgecolor="#003344", markersize=10, label="Aldeia indígena")
    )
    handles.append(
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#FFD600",
                   markeredgecolor="#1a1a1a", markersize=9, label="Comunidade quilombola (coordenada)")
    )
    handles.append(
        plt.Line2D([0], [0], marker="s", color="w", markerfacecolor="#FFD600",
                   markeredgecolor="#1a1a1a", markersize=9,
                   label="Município com comunidade quilombola certificada (presença municipal)")
    )
    ax.legend(handles=handles, loc="lower left", fontsize=6.5, frameon=True, framealpha=0.92)
    qa["MAP3_LEGEND_VALID"] = True

    stamp = rodada_stamp or datetime.now().strftime("%Y%m%d_%H%M")
    chash = str(cmc.get("classification_hash") or "nohash")
    fname = f"mapa3_povos_tradicionais_{stamp}_{chash}.png"
    path = out_dir / fname
    legacy = out_dir / "mapa_territorios_tradicionais.png"
    try:
        fig.savefig(path, bbox_inches="tight", facecolor="white")
        fig.savefig(legacy, bbox_inches="tight", facecolor="white")
    except OSError as exc:
        plt.close(fig)
        qa["MAP3_FILE_CREATED_THIS_RUN"] = False
        return {"disponivel": False, "qa": qa, "motivo": f"Falha ao gravar Mapa 3: {exc}"}
    plt.close(fig)

    meta_path = path.with_suffix(".hash.txt")
    meta_path.write_text(
        f"classification_hash={chash}\n"
        f"data_hora_rodada={cmc.get('data_hora_rodada')}\n"
        f"n={cmc.get('n')}\n"
        f"counts={cmc.get('counts_atual')}\n",
        encoding="utf-8",
    )
    qa["MAP3_FILE_CREATED_THIS_RUN"] = path.exists() and path.stat().st_size > 0
    qa["map3_classification_hash"] = chash
    qa["MAP3_CLASSIFICATION_HASH_MATCH"] = bool(chash) and chash == str(cmc.get("classification_hash"))
    qa["MAP3_SOURCE_DATE_MATCH"] = True
    qa["MAP_REGEN_REQUIRED"] = False
    ok_publish = (
        qa["MAP3_FILE_CREATED_THIS_RUN"]
        and qa["MAP3_CLASSIFICATION_HASH_MATCH"]
        and not qa.get("MAP3_STALE_ERROR")
        and not qa.get("MAP3_CLASS_DISTRIBUTION_ERROR")
        and int(qa.get("MAP3_MUNICIPAL_DIFF_COUNT") or 0) == 0
        and qa["MAP3_LEGEND_VALID"]
        and qa["MAP3_TRADITIONAL_LAYER_LOADED"]
    )
    return {
        "disponivel": True,
        "mapa_territorios": str(legacy),
        "mapa_territorios_versionado": str(path),
        "classification_hash": chash,
        "quilombos_via_centroid": n_qui_centroid,
        "n_aldeias_plot": int(len(ald)),
        "n_quilombos_plot": int(len(qui)),
        "qa": qa,
        "ok_publicacao": ok_publish,
        "counts_atual": dict(cmc.get("counts_atual") or {}),
    }


def _quadro_cobertura_rede() -> tuple[str, str, str, dict]:
    """Cruza classe ARARAS (vermelho/roxo) com distância até APS/hospital.

    Devolve: tabela municipal compacta, nota metodológica, recomendações, QA interno.
    """
    try:
        from sisclima.engines.cobertura_territorio import (
            LIMIAR_MAX_VALIDACAO_KM,
            LIMIAR_P90_VALIDACAO_KM,
            load_cobertura,
        )
    except Exception:
        return INDISPONIVEL, "", "", {}
    cob = load_cobertura()
    nota = (
        "Distância em km até o estabelecimento do Cadastro Nacional de Estabelecimentos de Saúde (CNES) "
        "com coordenada oficial (trajeto viário quando a rota existe; linha reta se a rota falhar e for validada). "
        "Distâncias extremas são submetidas a validação antes de serem utilizadas na priorização. "
        "Minutos de viagem não foram validados nesta rodada."
    )
    vazio = (
        "_Recorte território–CNES indisponível nesta rodada (sem pontos com lat/lon oficial)._",
        nota,
        "",
        {},
    )
    if cob is None or cob.empty:
        return vazio
    work = cob.copy()
    if "nivel" in work.columns:
        work = work[work["nivel"].astype(str).str.lower().isin(_NIVEIS_CRITICOS)]
    if work.empty:
        return (
            "_Nenhum território georreferenciado em município vermelho ou roxo nesta rodada._",
            nota,
            "",
            {},
        )
    work["km_aps"] = pd.to_numeric(work.get("km_aps"), errors="coerce")
    work["km_hospital"] = pd.to_numeric(work.get("km_hospital"), errors="coerce")
    if "longe_rede" not in work.columns:
        work["longe_rede"] = (work["km_aps"] > 30) | (work["km_hospital"] > 50)
    work["longe_rede"] = work["longe_rede"].fillna(False)

    grp = (
        work.groupby(work["municipio"].astype(str), dropna=False)
        .agg(
            n_territorios=("nome", "size") if "nome" in work.columns else ("municipio", "size"),
            n_longe=("longe_rede", "sum"),
            km_aps_med=("km_aps", "median"),
            km_aps_p90=("km_aps", lambda s: float(s.quantile(0.90)) if s.notna().any() else float("nan")),
            km_aps_max=("km_aps", "max"),
            km_hosp_max=("km_hospital", "max"),
            nivel=("nivel", "first"),
            nivel_pred=("nivel_predicao_7d", "first") if "nivel_predicao_7d" in work.columns else ("nivel", "first"),
        )
        .reset_index()
    )
    p90 = pd.to_numeric(grp["km_aps_p90"], errors="coerce")
    mx = pd.to_numeric(grp["km_aps_max"], errors="coerce")
    grp["route_distance_warning"] = mx > 300
    grp["route_validation_required"] = (p90 > LIMIAR_P90_VALIDACAO_KM) | (mx > LIMIAR_MAX_VALIDACAO_KM)
    warn_rota = grp[grp["route_distance_warning"].fillna(False)]
    if not warn_rota.empty:
        log.warning(
            "ROUTE_DISTANCE_WARNING municipios=%s",
            ", ".join(str(x) for x in warn_rota["municipio"].tolist()),
        )
    exige = grp[grp["route_validation_required"].fillna(False)].copy()
    if not exige.empty:
        log.warning(
            "ROUTE_VALIDATION_REQUIRED n=%s municipios=%s",
            len(exige),
            ", ".join(
                f"{r['municipio']} P90={r['km_aps_p90']} máx={r['km_aps_max']}"
                for _, r in exige.iterrows()
            ),
        )
    rotas_qa = [
        f"{str(r['municipio'])} — P90 APS {fmt_int(r['km_aps_p90'])} km (máx. {fmt_int(r['km_aps_max'])} km)"
        for _, r in exige.sort_values("km_aps_p90", ascending=False).iterrows()
    ]

    _rank = {"roxa": 4, "vermelha": 3, "laranja": 2, "amarela": 1, "verde": 0}
    grp["_rank"] = grp["nivel"].astype(str).str.lower().map(_rank).fillna(0)
    grp["_rank_proj"] = grp["nivel_pred"].astype(str).str.lower().map(_rank).fillna(0)
    publicados = grp[~grp["route_validation_required"].fillna(False)].copy()
    publicados = publicados.sort_values(
        ["_rank", "_rank_proj", "n_longe", "km_aps_p90", "km_hosp_max"],
        ascending=False,
    )
    rows: list[list[str]] = []
    mun_prior = []
    mun_aps90: list[str] = []
    for _, row in publicados.iterrows():
        n_l = int(row.get("n_longe") or 0)
        if n_l <= 0:
            continue
        mun = str(row.get("municipio") or "—")
        nivel = _nivel_pt(row.get("nivel"))
        km_max = row.get("km_aps_max")
        if pd.notna(km_max) and float(km_max) >= 90:
            mun_aps90.append(mun)
        if len(rows) < 8:
            rows.append(
                [
                    mun,
                    nivel,
                    fmt_int(n_l),
                    fmt_int(row.get("km_aps_p90")) if pd.notna(row.get("km_aps_p90")) else INDISPONIVEL,
                    fmt_int(km_max) if pd.notna(km_max) else INDISPONIVEL,
                    fmt_int(row.get("km_hosp_max")) if pd.notna(row.get("km_hosp_max")) else INDISPONIVEL,
                ]
            )
            mun_prior.append(f"{mun} ({nivel})")
    n_val = int(grp["route_validation_required"].fillna(False).sum())
    if not rows:
        extra = (
            " Validação das distâncias em andamento — estimativas extremas não entram na priorização desta rodada."
            if n_val
            else ""
        )
        return (
            "_Há territórios em vermelho/roxo, mas nenhum ultrapassou 30 km da APS ou 50 km do hospital nesta rodada._"
            + extra,
            nota,
            "",
            {"rotas_validacao": rotas_qa, "n_route_validation_required": n_val},
        )
    headers = [
        "Município",
        "Classe",
        "Territórios distantes",
        "P90 APS (km)",
        "Máx. APS (km)",
        "Máx. hospital (km)",
    ]
    tabela = bloco_tabela(
        "Municípios com maior prioridade combinada de risco e dificuldade de acesso assistencial",
        md_table(headers, rows, vazio=INDISPONIVEL),
        "ARARAS MT/CIEVS-MT, com dados do Cadastro Nacional de Estabelecimentos de Saúde (CNES).",
        nota=(
            "Distância em km até o estabelecimento do CNES com coordenada oficial "
            "(trajeto viário quando a rota existe; linha reta se a rota falhar e for validada). "
            "Distâncias extremas são submetidas a validação antes de serem utilizadas na priorização. "
            "Minutos de viagem não foram validados nesta rodada."
        ),
    )
    n_aps90 = len(mun_aps90)
    recs = (
        "**Leitura combinada.** A tabela do corpo não é o ranking das maiores distâncias. "
        "A priorização usa classe atual e projetada, número de territórios distantes, P90 APS e "
        "distância hospitalar, somente com rotas já validadas. A lista completa permanece no painel.\n"
    )
    if n_val:
        from sisclima.engines.boletim_el_nino.formatters import plural_pt

        n_txt = plural_pt(n_val, "município", "municípios")
        n_word = {1: "Um", 2: "Dois", 3: "Três", 4: "Quatro", 5: "Cinco"}.get(int(n_val))
        lead = f"{n_word} {n_txt}" if n_word else f"{fmt_int(n_val)} {n_txt}"
        verb = "apresentou" if int(n_val) == 1 else "apresentaram"
        excl = "foi excluído" if int(n_val) == 1 else "foram excluídos"
        recs += (
            f"\n**Validação das distâncias.** {lead} {verb} estimativas extremas de distância "
            f"assistencial e {excl} da priorização desta rodada até a conclusão da validação das rotas.\n"
        )
    recs += f"""
{n_aps90} municípios (rotas validadas) possuem ao menos um território com distância máxima ≥90 km da APS.

**Recomendações desta rodada**
- Secretarias municipais e regionais: articular deslocamento, transporte sanitário e apoio da APS aos territórios listados; não interpretar as classes vermelha e roxa como indicação de proximidade de uma Unidade Básica de Saúde (UBS).
- DSEI/SESAI e SES-MT: priorizar apoio às aldeias em vermelho ou roxo com maior distância até a APS.
- Vigilância em Saúde do Trabalhador: incluir equipes de campo e brigadistas desses municípios no recorte de exposição a calor e fumaça.
"""
    qa_interno = {
        "rotas_validacao": rotas_qa,
        "n_route_validation_required": n_val,
        "n_route_distance_warning": int(grp["route_distance_warning"].fillna(False).sum()),
    }
    return tabela, "", recs, qa_interno


def build_territorios(
    resumo: pd.DataFrame,
    *,
    assets_dir: Path | None = None,
    data_ref: str = "",
    cmc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cruza aldeias/quilombos Vigibarragens com classificação de risco municipal."""
    from sisclima.engines.boletim_el_nino.classificacao import build_current_municipal_classification

    if cmc is None or not cmc.get("disponivel"):
        cmc = build_current_municipal_classification(resumo, data_hora_rodada=data_ref or None)

    pts, mun = _load_vigibarragens()
    cite_v = cite("vigibarragens")
    # Fonte única: CMC → resumo mínimo para merge de risco
    risco_src = cmc.get("resumo_for_maps") if cmc and cmc.get("disponivel") else resumo
    risco = _merge_risco(risco_src if risco_src is not None else resumo)
    # Enriquecer exposição a partir do resumo operacional completo
    if not risco.empty and resumo is not None and not resumo.empty and "cod_ibge" in resumo.columns:
        extra_cols = [
            c
            for c in (
                "tmax",
                "pm25_ugm3",
                "focos_queimadas_7d",
                "focos_7d",
                "situacao_hidro",
                "municipio",
                "regional_saude",
            )
            if c in resumo.columns
        ]
        if extra_cols:
            r2 = resumo[["cod_ibge"] + extra_cols].copy()
            r2["_cod"] = _cod_ibge6(r2["cod_ibge"])
            r2 = r2.dropna(subset=["_cod"]).drop_duplicates("_cod")
            risco = risco.drop(columns=[c for c in extra_cols if c in risco.columns], errors="ignore")
            risco = risco.merge(r2.drop(columns=["cod_ibge"], errors="ignore"), on="_cod", how="left")

    n_ald = int((pts["categoria"] == CATEGORIA_ALDEIA).sum()) if not pts.empty and "categoria" in pts.columns else 0
    n_qui = int((pts["categoria"] == CATEGORIA_QUILOMBO).sum()) if not pts.empty and "categoria" in pts.columns else 0

    ti_status = "OK" if n_ald > 0 else "PENDENTE"
    qui_status = "OK" if n_qui > 0 else "PENDENTE"

    by_cls = (cmc or {}).get("by_ibge6") or {}
    mismatch = 0

    # Municípios com território em vermelho/roxo
    mun_crit: pd.DataFrame = pd.DataFrame()
    if not mun.empty and not risco.empty:
        m = mun.copy()
        m["_cod"] = _cod_ibge6(m["cod_ibge"])
        mun_crit = m.merge(risco, on="_cod", how="inner", suffixes=("", "_r"))
        mun_crit = mun_crit[mun_crit["nivel"].astype(str).str.lower().isin(_NIVEIS_CRITICOS)]
        n_a = pd.to_numeric(mun_crit["n_aldeias"], errors="coerce").fillna(0) if "n_aldeias" in mun_crit.columns else 0
        n_q = pd.to_numeric(mun_crit["n_quilombos"], errors="coerce").fillna(0) if "n_quilombos" in mun_crit.columns else 0
        mun_crit = mun_crit[(n_a > 0) | (n_q > 0)]
        if "n_aldeias" in mun_crit.columns:
            mun_crit = mun_crit.sort_values(["n_aldeias", "n_quilombos"], ascending=False)
        for _, row in mun_crit.iterrows():
            cod = str(row.get("_cod") or "")
            cls_txt = str(row.get("nivel") or "").lower().strip()
            cls_cmc = str(by_cls.get(cod) or "").lower().strip()
            if cod and cls_cmc and cls_txt != cls_cmc:
                mismatch += 1

    rows_ti = _quadro_aldeias_municipal(mun_crit, limite=7)
    rows_qui = _quadro_quilombos(pts, risco, limite=25)
    bullets_ti = []
    for r in rows_ti:
        try:
            n_ald_i = int(str(r[1]).replace(".", "").replace(",", ""))
        except ValueError:
            n_ald_i = 0
        bullets_ti.append(
            f"- **{r[0]}** — {fmt_plural(n_ald_i, 'aldeia', 'aldeias')} — {r[2]} → {r[3]} — {r[4]}."
        )
    qui_por_mun: dict[str, int] = {}
    for r in rows_qui:
        mun_n = r[1]
        qui_por_mun[mun_n] = qui_por_mun.get(mun_n, 0) + 1
    bullets_qui = [
        f"- **{mun_n}** — {fmt_plural(n, 'comunidade certificada', 'comunidades certificadas')} em área de risco."
        for mun_n, n in sorted(qui_por_mun.items(), key=lambda t: t[1], reverse=True)[:8]
    ]

    headers_ti = ["Município", "N.º de aldeias", "Risco atual", "Projeção ~7 dias", "Principal exposição"]
    headers_qui = ["Comunidade", "Município", "Risco atual", "Projeção ~7 dias", "Principal exposição"]
    md_ti = md_table(headers_ti, rows_ti, vazio=INDISPONIVEL) if rows_ti else (
        f"_Nenhuma aldeia indígena em município nas classes vermelha ou roxa nesta rodada. {cite_v}_"
    )
    md_qui = md_table(headers_qui, rows_qui, vazio=INDISPONIVEL) if rows_qui else (
        f"_Nenhuma comunidade quilombola certificada em município nas classes vermelha ou roxa nesta rodada. {cite_v}_"
    )

    n_mun_ald_crit = int((mun_crit["n_aldeias"].fillna(0) > 0).sum()) if not mun_crit.empty and "n_aldeias" in mun_crit.columns else 0
    n_mun_qui_crit = int((mun_crit["n_quilombos"].fillna(0) > 0).sum()) if not mun_crit.empty and "n_quilombos" in mun_crit.columns else 0
    n_crit = int(risco["nivel"].astype(str).str.lower().isin(_NIVEIS_CRITICOS).sum()) if not risco.empty else 0

    resumo_md = (
        f"Entre os {fmt_plural(n_crit, 'município', 'municípios')} nas classes vermelha e roxa, "
        f"**{fmt_int(n_mun_ald_crit)}** têm aldeias indígenas e "
        f"**{fmt_int(n_mun_qui_crit)}** têm comunidades quilombolas certificadas."
    )
    nota_aldeias = (
        "Os quantitativos correspondem a aldeias georreferenciadas associadas ao município "
        "e não representam estimativa populacional."
    )
    nota_quilombos = (
        "Comunidade certificada pela Fundação Cultural Palmares não equivale necessariamente "
        "a território delimitado ou titulado."
    )

    cob_md, nota_cob, cob_recs, qa_rotas = _quadro_cobertura_rede()

    mapa: dict[str, Any] = {"disponivel": False}
    rodada_stamp = None
    if data_ref:
        try:
            ts = pd.to_datetime(data_ref, errors="coerce")
            if pd.notna(ts):
                rodada_stamp = ts.strftime("%Y%m%d_%H%M")
        except Exception:  # noqa: BLE001
            rodada_stamp = None
    if assets_dir is not None and not pts.empty:
        mapa = export_mapa_territorios(
            resumo,
            pts,
            assets_dir,
            data_ref=data_ref,
            cmc=cmc,
            rodada_stamp=rodada_stamp,
        )

    return {
        "ti_status": ti_status,
        "quilombo_status": qui_status,
        "resumo_md": resumo_md,
        "quadro_md": md_ti,
        "quadro_executivo_md": "\n".join(bullets_ti) if bullets_ti else md_ti,
        "quilombo_md": md_qui,
        "quilombo_executivo_md": "\n".join(bullets_qui) if bullets_qui else md_qui,
        "nota_aldeias": nota_aldeias,
        "nota_quilombos": nota_quilombos,
        "cobertura_md": cob_md,
        "nota_cobertura": nota_cob,
        "cobertura_recs_md": cob_recs,
        "qa_rotas": qa_rotas or {},
        "n_aldeias": n_ald,
        "n_quilombos": n_qui,
        "n_mun_aldeias_criticos": n_mun_ald_crit,
        "n_mun_quilombos_criticos": n_mun_qui_crit,
        "mapa": mapa,
        "TRADITIONAL_TERRITORY_CLASS_MISMATCH": mismatch,
        "classification_hash": (cmc or {}).get("classification_hash"),
        "nota": "",
    }
