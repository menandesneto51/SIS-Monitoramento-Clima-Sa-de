# -*- coding: utf-8 -*-
"""Relatório completo de validação municipal — Sorriso (todas as camadas)."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env", override=True)

from sisclima.core.db import read_table, table_exists
from sisclima.reporting.institutional_pdf import (
    CONTENT_BOTTOM_MARGIN,
    CONTENT_TOP_MARGIN,
    SES_NAVY,
    page_callbacks,
    register_institutional_fonts,
)

COD = "5107925"
MUNICIPIO = "Sorriso"
OUT_DIR = ROOT / "data" / "output" / "validacao_ocupacao_sieges"
GEO_CSV = ROOT / "data" / "output" / "validacao_geo_indicasus" / "geo_hospitais_upas_indicasus.csv"


def _esc(v) -> str:
    return str(v if v is not None else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt(v, nd=1, suf="") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        x = float(v)
        s = f"{x:.{nd}f}".replace(".", ",") if nd else f"{x:.0f}".replace(".", ",")
        return s + suf
    except Exception:
        return str(v)


def _styles():
    font, font_bold = register_institutional_fonts()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "t", parent=base["Heading1"], fontName=font_bold, fontSize=14, textColor=SES_NAVY, spaceAfter=8
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName=font_bold, fontSize=11, textColor=SES_NAVY, spaceBefore=10, spaceAfter=5
        ),
        "body": ParagraphStyle(
            "b", parent=base["Normal"], fontName=font, fontSize=9.2, leading=12.5, alignment=TA_JUSTIFY, spaceAfter=5
        ),
        "small": ParagraphStyle(
            "s", parent=base["Normal"], fontName=font, fontSize=8.2, leading=11, textColor=colors.HexColor("#334155")
        ),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontName=font, fontSize=7.5, leading=9.5, alignment=TA_LEFT),
        "cell_b": ParagraphStyle(
            "cb", parent=base["Normal"], fontName=font_bold, fontSize=7.5, leading=9.5, textColor=colors.white
        ),
    }


def _kv(pairs, styles, c1=5.2 * cm, c2=11.8 * cm):
    font, _ = register_institutional_fonts()
    data = [[Paragraph(_esc(k), styles["cell"]), Paragraph(_esc(v), styles["cell"])] for k, v in pairs]
    t = Table(data, colWidths=[c1, c2])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("FONTNAME", (0, 0), (-1, -1), font),
            ]
        )
    )
    return t


def _tbl(headers, rows, styles, widths):
    font, font_bold = register_institutional_fonts()
    data = [[Paragraph(h, styles["cell_b"]) for h in headers]]
    for r in rows:
        data.append([Paragraph(_esc(c), styles["cell"]) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), SES_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTNAME", (0, 1), (-1, -1), font),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#94A3B8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F8FAFC")))
    t.setStyle(TableStyle(cmds))
    return t


def coletar() -> dict:
    resumo = read_table("resumo_municipal_atual")
    resumo["cod_ibge"] = (
        resumo["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True).str.extract(r"(\d{6,7})", expand=False)
    )
    row = resumo.loc[resumo["cod_ibge"] == COD].iloc[0]
    reg = str(row.get("regional_saude") or "")

    occ_mun = read_table("hospital_ocupacao_municipio")
    occ_mun["cod_ibge"] = occ_mun["cod_ibge"].astype(str)
    mun = occ_mun.loc[occ_mun["cod_ibge"] == COD]
    mun_row = mun.iloc[0] if not mun.empty else None

    occ_un = read_table("hospital_ocupacao_unidade")
    occ_un["cod_ibge"] = occ_un["cod_ibge"].astype(str)
    un = occ_un.loc[occ_un["cod_ibge"] == COD].copy()
    un_agg = pd.DataFrame()
    if not un.empty:
        gcols = [c for c in ("UnidadeNotificadoraId", "NomeUnidade", "fonte_geo_unidade", "DataReferencia") if c in un.columns]
        num = [
            c
            for c in (
                "leitos_existentes",
                "leitos_sus",
                "leitos_ocupados",
                "leitos_bloqueados_movimento",
                "leitos_higienizacao",
                "leitos_reservados",
            )
            if c in un.columns
        ]
        # aggregate by unit+tipo if present
        g2 = [c for c in ("UnidadeNotificadoraId", "NomeUnidade", "fonte_geo_unidade", "TipoLeito", "ClassificacaoId") if c in un.columns]
        if g2 and num:
            un_agg = un.groupby(g2, dropna=False)[num].sum().reset_index()
            un_agg["ocupacao_pct"] = 100 * un_agg["leitos_ocupados"] / un_agg["leitos_existentes"].replace({0: pd.NA})
        un_tot = (
            un.groupby(["UnidadeNotificadoraId", "NomeUnidade", "fonte_geo_unidade"], dropna=False)[num]
            .sum()
            .reset_index()
            if num
            else pd.DataFrame()
        )
        if not un_tot.empty:
            un_tot["ocupacao_pct"] = 100 * un_tot["leitos_ocupados"] / un_tot["leitos_existentes"].replace({0: pd.NA})
    else:
        un_tot = pd.DataFrame()

    est = None
    if table_exists("hospital_ocupacao_estado"):
        e = read_table("hospital_ocupacao_estado")
        if e is not None and not e.empty:
            est = e.iloc[-1]

    peers = resumo.loc[
        resumo["regional_saude"].astype(str) == reg,
        [
            c
            for c in (
                "municipio",
                "cod_ibge",
                "fonte_ocupacao",
                "ocupacao_leitos_pct",
                "leitos_total",
                "leitos_ocupados",
                "kpi_sisreg_solicitacoes",
                "kpi_sisreg_fila_h",
                "nivel",
                "indice_pressao_saude",
                "tmax",
                "pm25_ugm3",
            )
            if c in resumo.columns
        ],
    ].copy()
    peers = peers.sort_values("ocupacao_leitos_pct", ascending=False, na_position="last")

    geo = pd.DataFrame()
    if GEO_CSV.is_file():
        g = pd.read_csv(GEO_CSV, encoding="utf-8-sig")
        g["cod6"] = g["cod_ibge_6"].astype(str).str.replace(r"\D", "", regex=True).str.slice(0, 6)
        geo = g[
            g["cod6"].eq("510792")
            | g["municipio"].astype(str).str.contains("Sorriso", case=False, na=False)
            | g["nome"].astype(str).str.contains("SORRISO", case=False, na=False)
        ].copy()

    # Campos operacionais extras do resumo
    campos = [
        "nivel",
        "nivel_alerta_integrado",
        "indice_pressao_saude",
        "semaforo_pressao",
        "fonte_ocupacao",
        "ocupacao_leitos_pct",
        "leitos_total",
        "leitos_ocupados",
        "kpi_sisreg_solicitacoes",
        "kpi_sisreg_fila_h",
        "kpi_sisreg_semaforo",
        "kpi_sisreg_score",
        "kpi_sisreg_disponivel",
        "tmax",
        "utci_proxy",
        "pm25_ugm3",
        "qualidade_ar_nivel",
        "risco_cumulativo_3d",
        "pred_nivel_clima_7d",
        "pred_indice_pressao_7d",
        "tendencia_pressao_7d",
        "nivel_prontidao",
        "pressao_calor_pct",
        "regional_saude",
    ]
    ops = {c: row.get(c) for c in campos if c in row.index}

    return {
        "row": row,
        "ops": ops,
        "mun": mun_row,
        "un_agg": un_agg,
        "un_tot": un_tot,
        "peers": peers,
        "reg": reg,
        "est": est,
        "geo": geo,
        "quando": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def gerar_pdf(d: dict, path: Path) -> Path:
    styles = _styles()
    row, mun, ops, reg, est, geo = d["row"], d["mun"], d["ops"], d["reg"], d["est"], d["geo"]
    un_tot, un_agg, peers = d["un_tot"], d["un_agg"], d["peers"]

    ocup = mun.get("ocupacao_pct") if mun is not None else ops.get("ocupacao_leitos_pct")
    le = mun.get("leitos_existentes") if mun is not None else ops.get("leitos_total")
    lo = mun.get("leitos_ocupados") if mun is not None else ops.get("leitos_ocupados")
    fonte = str(ops.get("fonte_ocupacao") or (mun.get("fonte") if mun is not None else "") or "—")

    from sisclima.branding import SYSTEM_NAME

    story = [
        Paragraph(f"Relatório completo de validação — {MUNICIPIO}", styles["title"]),
        Paragraph(
            f"{SYSTEM_NAME} / CIEVS-MT · IBGE {COD} · Regional {_esc(reg)} · {_esc(d['quando'])}",
            styles["small"],
        ),
        Spacer(1, 0.15 * cm),
        Paragraph("1. Identificação e leitura executiva", styles["h2"]),
        Paragraph(
            f"<b>{MUNICIPIO}</b> está em nível operacional <b>{_esc(str(ops.get('nivel') or '—').capitalize())}</b>, "
            f"com ocupação IndicaSUS (filtros SIEGES) de <b>{_esc(_fmt(ocup, 1, '%'))}</b> "
            f"({_esc(_fmt(lo, 0))}/{_esc(_fmt(le, 0))} leitos) e pressão SISREG de "
            f"<b>{_esc(_fmt(ops.get('kpi_sisreg_solicitacoes'), 0))}</b> solicitações. "
            "Ocupação hospitalar ≠ pressão de regulação.",
            styles["body"],
        ),
        _kv(
            [
                ("Município / IBGE", f"{MUNICIPIO} / {COD}"),
                ("Regional de saúde", reg or "—"),
                ("Nível operacional", str(ops.get("nivel") or "—")),
                ("Alerta integrado", str(ops.get("nivel_alerta_integrado") or "—")),
                ("Índice pressão 0–100", _fmt(ops.get("indice_pressao_saude"), 1)),
                ("Semáforo pressão", str(ops.get("semaforo_pressao") or "—")),
                ("Prontidão", str(ops.get("nivel_prontidao") or "—")),
            ],
            styles,
        ),
        Paragraph("2. Achado crítico de cadastro/geo (IndicaSUS)", styles["h2"]),
        Paragraph(
            "O <b>Hospital Regional de Sorriso</b> (FormHospitalId <b>469</b>) colidia com "
            "<b>UnidadeSaudeId 469</b> (UBS Centro / Guarantã do Norte). Sem priorizar "
            "<b>form.Hospital</b> na geo, os leitos de Sorriso eram atribuídos a outro município "
            "e Sorriso aparecia como <b>SEM_LEITOS_INDICASUS</b>. Correção aplicada no ARARAS: "
            "prioridade Hospital → Estabelecimento → UnidadeSaude. Geolocalização do hospital "
            "passa a usar CNES (lat/lon IndicaSUS da UnidadeSaude descartados por colisão).",
            styles["body"],
        ),
        Paragraph("3. Ocupação hospitalar — IndicaSUS (filtros SIEGES)", styles["h2"]),
        Paragraph(
            "Filtros: SituacaoAtual≠Bloqueado · Tipo SUS Hab./Não Hab. · TipoLeito≠Pronto Atendimento · "
            "exclusão UPA/PA/unidade mista.",
            styles["small"],
        ),
        _kv(
            [
                ("Fonte", fonte),
                ("Ocupação", _fmt(ocup, 1, "%")),
                ("Leitos elegíveis", _fmt(le, 0)),
                ("Leitos SUS Hab. (aprox.)", _fmt(mun.get("leitos_sus") if mun is not None else None, 0)),
                ("Leitos ocupados", _fmt(lo, 0)),
                ("Bloqueados (fora do denominador)", _fmt(mun.get("leitos_bloqueados_movimento") if mun is not None else None, 0)),
                ("Higienização / reservados", f"{_fmt(mun.get('leitos_higienizacao') if mun is not None else None, 0)} / {_fmt(mun.get('leitos_reservados') if mun is not None else None, 0)}"),
                ("Última movimentação", str(mun.get("ultima_movimentacao") if mun is not None else "—")),
                (
                    "Referência estadual",
                    (
                        f"{_fmt(est.get('ocupacao_pct'), 1, '%')} · "
                        f"{_fmt(est.get('leitos_ocupados'), 0)}/{_fmt(est.get('leitos_existentes'), 0)} · "
                        f"{_fmt(est.get('municipios_com_ocupacao'), 0)} mun."
                        if est is not None
                        else "—"
                    ),
                ),
            ],
            styles,
        ),
    ]

    story.append(Paragraph("3.1 Unidades com leitos no recorte (totais)", styles["h2"]))
    if un_tot is None or un_tot.empty:
        story.append(Paragraph("Nenhuma unidade com leitos elegíveis SIEGES neste IBGE.", styles["body"]))
    else:
        rows = []
        for _, u in un_tot.iterrows():
            rows.append(
                [
                    str(int(u["UnidadeNotificadoraId"])) if pd.notna(u.get("UnidadeNotificadoraId")) else "—",
                    str(u.get("NomeUnidade") or "—")[:40],
                    str(u.get("fonte_geo_unidade") or "—"),
                    _fmt(u.get("leitos_existentes"), 0),
                    _fmt(u.get("leitos_ocupados"), 0),
                    _fmt(u.get("ocupacao_pct"), 1),
                    _fmt(u.get("leitos_bloqueados_movimento"), 0),
                ]
            )
        story.append(
            _tbl(
                ["Id", "Unidade", "Geo", "Leitos", "Ocup.", "%", "Bloq."],
                rows,
                styles,
                [1.3 * cm, 6.0 * cm, 2.0 * cm, 1.6 * cm, 1.6 * cm, 1.5 * cm, 1.5 * cm],
            )
        )

    if un_agg is not None and not un_agg.empty and "TipoLeito" in un_agg.columns:
        story.append(Paragraph("3.2 Detalhe por TipoLeito / Classificação", styles["h2"]))
        rows = []
        for _, u in un_agg.sort_values("leitos_existentes", ascending=False).head(25).iterrows():
            rows.append(
                [
                    str(u.get("TipoLeito") if pd.notna(u.get("TipoLeito")) else "—"),
                    str(u.get("ClassificacaoId") if pd.notna(u.get("ClassificacaoId")) else "—"),
                    _fmt(u.get("leitos_existentes"), 0),
                    _fmt(u.get("leitos_ocupados"), 0),
                    _fmt(u.get("ocupacao_pct"), 1),
                ]
            )
        story.append(
            _tbl(
                ["TipoLeito", "Classif.", "Leitos", "Ocup.", "%"],
                rows,
                styles,
                [2.5 * cm, 2.5 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm],
            )
        )

    story.extend(
        [
            Paragraph("4. Pressão hospitalar — SISREG (≠ ocupação)", styles["h2"]),
            Paragraph(
                "Solicitações e fila medem demanda/regulação territorial. "
                "<b>Não</b> devem ser lidas como percentual de leitos.",
                styles["body"],
            ),
            _kv(
                [
                    ("Solicitações", _fmt(ops.get("kpi_sisreg_solicitacoes"), 0)),
                    ("Fila média (h)", _fmt(ops.get("kpi_sisreg_fila_h"), 1)),
                    ("Semáforo SISREG", str(ops.get("kpi_sisreg_semaforo") or "—")),
                    ("Score SISREG", _fmt(ops.get("kpi_sisreg_score"), 1)),
                    ("Disponível", str(ops.get("kpi_sisreg_disponivel") or "—")),
                ],
                styles,
            ),
            Paragraph("5. Clima, ar e tendência", styles["h2"]),
            _kv(
                [
                    ("Tmáx", _fmt(ops.get("tmax"), 1, " °C")),
                    ("UTCI proxy", _fmt(ops.get("utci_proxy"), 1)),
                    ("PM2,5", _fmt(ops.get("pm25_ugm3"), 1, " µg/m³")),
                    ("Qualidade do ar", str(ops.get("qualidade_ar_nivel") or "—")),
                    ("Risco cumulativo 3d", _fmt(ops.get("risco_cumulativo_3d"), 2)),
                    ("Pressão calor (painel)", _fmt(ops.get("pressao_calor_pct"), 1)),
                    ("Predição clima 7d", str(ops.get("pred_nivel_clima_7d") or "—")),
                    ("Predição pressão 7d", _fmt(ops.get("pred_indice_pressao_7d"), 1)),
                    ("Tendência pressão 7d", str(ops.get("tendencia_pressao_7d") or "—")),
                ],
                styles,
            ),
            Paragraph("6. Geolocalização — hospitais/UPAs IndicaSUS em Sorriso", styles["h2"]),
            Paragraph(
                "Validação cruzada form.Hospital × UnidadeSaude × CNES. "
                "Centroide municipal não é coordenada oficial.",
                styles["small"],
            ),
        ]
    )

    if geo is None or geo.empty:
        story.append(Paragraph("Sem registros no pacote de validação geo para Sorriso.", styles["body"]))
    else:
        rows = []
        for _, g in geo.iterrows():
            rows.append(
                [
                    str(int(g["unidade_id"])) if pd.notna(g.get("unidade_id")) else "—",
                    str(g.get("nome") or "—")[:36],
                    str(g.get("grupo") or "—"),
                    str(g.get("status_geo") or "—")[:28],
                    str(g.get("fonte_coord") or "—")[:16],
                    _fmt(g.get("lat"), 4) if pd.notna(g.get("lat")) else "—",
                    _fmt(g.get("lon"), 4) if pd.notna(g.get("lon")) else "—",
                    str(g.get("cnes") or "—"),
                ]
            )
        story.append(
            _tbl(
                ["Id", "Nome", "Grupo", "Status geo", "Fonte", "Lat", "Lon", "CNES"],
                rows,
                styles,
                [1.2 * cm, 4.2 * cm, 1.6 * cm, 3.2 * cm, 2.0 * cm, 1.6 * cm, 1.6 * cm, 1.6 * cm],
            )
        )

    story.append(Paragraph("7. Comparativo — Regional Sinop", styles["h2"]))
    peer_rows = []
    for _, p in peers.iterrows():
        peer_rows.append(
            [
                str(p.get("municipio") or "—")[:18],
                str(p.get("cod_ibge") or ""),
                _fmt(p.get("ocupacao_leitos_pct"), 1),
                _fmt(p.get("leitos_total"), 0),
                _fmt(p.get("kpi_sisreg_solicitacoes"), 0),
                str(p.get("nivel") or "—")[:8],
                _fmt(p.get("indice_pressao_saude"), 1),
                _fmt(p.get("tmax"), 1),
                _fmt(p.get("pm25_ugm3"), 1),
            ]
        )
    story.append(
        _tbl(
            ["Município", "IBGE", "Ocup%", "Leitos", "SISREG", "Nível", "Pressão", "Tmáx", "PM2,5"],
            peer_rows,
            styles,
            [2.8 * cm, 1.6 * cm, 1.4 * cm, 1.4 * cm, 1.8 * cm, 1.4 * cm, 1.5 * cm, 1.3 * cm, 1.4 * cm],
        )
    )

    story.extend(
        [
            Paragraph("8. Checklist de homologação", styles["h2"]),
            Paragraph(
                "1) Dash SIEGES: Hospital Regional de Sorriso com mesmos filtros — conferir % e leitos.<br/>"
                "2) Confirmar que UPA Sara Akemi / PA não entram no denominador de ocupação hospitalar.<br/>"
                "3) Conferir CNES 2795655 (Hospital Regional) no mapa / cadastro.<br/>"
                "4) Guarantã do Norte não deve herdar Id 469.<br/>"
                "5) SISREG (~solicitações) lido como pressão, não como ocupação.<br/>"
                "6) Hospitais Candido Portinari / 13 de Maio / IGHASMAT: colisão Id sem CNES confiável — "
                "pendência de geo institucional.",
                styles["body"],
            ),
            Paragraph(
                "Documento de apoio à gestão · ARARAS MT · CIEVS-MT / SES-MT. "
                "Não inventa ocupação estadual nem converte fila SISREG em % de leitos.",
                styles["small"],
            ),
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=CONTENT_TOP_MARGIN,
        bottomMargin=CONTENT_BOTTOM_MARGIN,
        title=f"Validação completa Sorriso — {SYSTEM_NAME}",
        author="CIEVS · SES-MT",
    )
    on1, onn = page_callbacks(doc_title=f"Validação completa · {MUNICIPIO}")
    doc.build(story, onFirstPage=on1, onLaterPages=onn)
    return path


def gerar_markdown(d: dict, path: Path) -> Path:
    row, mun, ops, geo = d["row"], d["mun"], d["ops"], d["geo"]
    ocup = mun.get("ocupacao_pct") if mun is not None else ops.get("ocupacao_leitos_pct")
    le = mun.get("leitos_existentes") if mun is not None else ops.get("leitos_total")
    lo = mun.get("leitos_ocupados") if mun is not None else ops.get("leitos_ocupados")
    lines = [
        f"# Relatório completo de validação — {MUNICIPIO}",
        "",
        f"IBGE `{COD}` · Regional **{d['reg']}** · {d['quando']}",
        "",
        "## Leitura executiva",
        "",
        f"- Nível: **{str(ops.get('nivel') or '—').capitalize()}**",
        f"- Ocupação IndicaSUS (SIEGES): **{_fmt(ocup, 1, '%')}** ({_fmt(lo, 0)}/{_fmt(le, 0)} leitos)",
        f"- SISREG: **{_fmt(ops.get('kpi_sisreg_solicitacoes'), 0)}** solicitações · fila {_fmt(ops.get('kpi_sisreg_fila_h'), 1)} h",
        f"- Índice pressão: **{_fmt(ops.get('indice_pressao_saude'), 1)}** · semáforo {ops.get('semaforo_pressao') or '—'}",
        "",
        "## Achado geo/cadastro",
        "",
        "Hospital Regional (Id 469) colidia com UnidadeSaude de Guarantã; geo prioriza Hospital; coord mapa via CNES.",
        "",
        "## Unidades geo (IndicaSUS × CNES)",
        "",
    ]
    if geo is not None and not geo.empty:
        lines += [
            "| Id | Nome | Grupo | Status | Fonte | Lat | Lon | CNES |",
            "|---:|---|---|---|---|---:|---:|---|",
        ]
        for _, g in geo.iterrows():
            lines.append(
                f"| {g.get('unidade_id')} | {g.get('nome')} | {g.get('grupo')} | {g.get('status_geo')} | "
                f"{g.get('fonte_coord') or '—'} | {_fmt(g.get('lat'), 4) if pd.notna(g.get('lat')) else '—'} | "
                f"{_fmt(g.get('lon'), 4) if pd.notna(g.get('lon')) else '—'} | {g.get('cnes') or '—'} |"
            )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = coletar()
    pdf = OUT_DIR / f"relatorio_validacao_completa_sorriso_{ts}.pdf"
    stable = OUT_DIR / "relatorio_validacao_completa_sorriso.pdf"
    gerar_pdf(d, pdf)
    stable.write_bytes(pdf.read_bytes())
    md = OUT_DIR / "relatorio_validacao_completa_sorriso.md"
    gerar_markdown(d, md)
    meta = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "municipio": MUNICIPIO,
        "cod_ibge": COD,
        "pdf": str(stable.relative_to(ROOT)).replace("\\", "/"),
        "md": str(md.relative_to(ROOT)).replace("\\", "/"),
        "nivel": str(d["ops"].get("nivel")),
        "ocupacao_pct": float(d["mun"]["ocupacao_pct"]) if d["mun"] is not None else None,
        "sisreg_solicitacoes": float(d["ops"]["kpi_sisreg_solicitacoes"])
        if d["ops"].get("kpi_sisreg_solicitacoes") is not None and pd.notna(d["ops"].get("kpi_sisreg_solicitacoes"))
        else None,
        "geo_n": int(len(d["geo"])) if d["geo"] is not None else 0,
    }
    (OUT_DIR / "relatorio_validacao_completa_sorriso.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # HTML via markdown if possible
    try:
        import markdown

        html = (
            "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>"
            "<title>Validação completa Sorriso</title>"
            "<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem}"
            "table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #ccc;padding:.35rem}"
            "th{background:#ecfdf5}</style></head><body>"
            + markdown.markdown(md.read_text(encoding="utf-8"), extensions=["tables"])
            + f"<p><a href='{stable.name}'>PDF institucional completo</a></p>"
            + "</body></html>"
        )
        (OUT_DIR / "relatorio_validacao_completa_sorriso.html").write_text(html, encoding="utf-8")
    except Exception:
        pass
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print("PDF", stable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
