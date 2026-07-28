# -*- coding: utf-8 -*-
from pathlib import Path
from datetime import datetime
import py_compile

ARQ = Path("alerta_municipal_cuiaba_v11_10.py")

HELPER = '''
def load_geocalor_cardioresp_cuiaba_block() -> list[str]:
    """Carrega resultados GeoCalor cardiorrespiratórios para Cuiabá."""
    import sqlite3 as _sqlite3_geo
    import pandas as _pd_geo
    from pathlib import Path as _Path_geo

    db = _Path_geo("data/output/sis_integrado.db")
    if not db.exists():
        return [
            "Análise GeoCalor cardiorrespiratória:",
            "- Banco local indisponível para leitura dos resultados de RR."
        ]

    try:
        con_geo = _sqlite3_geo.connect(db)
        exists_geo = _pd_geo.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='geocalor_cuiaba_cardioresp_v11_12'",
            con_geo
        )
        if exists_geo.empty:
            con_geo.close()
            return [
                "Análise GeoCalor cardiorrespiratória:",
                "- Tabela geocalor_cuiaba_cardioresp_v11_12 ainda não foi gerada.",
                "- Rodar calcular_geocalor_cardioresp_v11_12.py para atualizar esta seção."
            ]

        df_geo = _pd_geo.read_sql("SELECT * FROM geocalor_cuiaba_cardioresp_v11_12", con_geo)
        con_geo.close()

        lines_geo = ["Análise GeoCalor cardiorrespiratória:"]
        if df_geo.empty:
            lines_geo.append("- Sem resultado disponível para Cuiabá.")
            return lines_geo

        status_vals = set(df_geo.get("status_modelagem", _pd_geo.Series(dtype=str)).dropna().astype(str).unique())
        if any("insuficiente" in s for s in status_vals):
            detalhe = str(df_geo.get("detalhe", _pd_geo.Series(["Dados insuficientes."])).dropna().astype(str).iloc[0])
            lines_geo.append("- Status: dados diários insuficientes para estimar RR local com defasagens 0–7.")
            lines_geo.append(f"- Observação: {detalhe[:700]}")
            lines_geo.append("- Interpretação: a nota GeoCalor permanece como referência metodológica; não há RR municipal validado para Cuiabá nesta execução.")
            return lines_geo

        for desfecho, g in df_geo.groupby("desfecho_label"):
            g2 = g.sort_values("rr", ascending=False).head(1)
            if g2.empty:
                continue
            r = g2.iloc[0]
            try:
                rr = float(r["rr"])
                li = float(r["rr_ic95_inf"])
                ls = float(r["rr_ic95_sup"])
                lag = int(r["lag"])
                lines_geo.append(f"- {desfecho}: maior RR lag {lag} = {rr:.2f} (IC95% {li:.2f}–{ls:.2f}); método {r.get('metodo','')}.")
            except Exception:
                lines_geo.append(f"- {desfecho}: resultado disponível, mas sem RR numérico válido.")

        lines_geo.append("- Uso: interpretar como componente epidemiológico complementar ao alerta operacional municipal.")
        return lines_geo
    except Exception as e:
        return [
            "Análise GeoCalor cardiorrespiratória:",
            f"- Erro ao carregar resultados: {type(e).__name__}: {e}"
        ]
'''

INSERT = '''
    lines.append("")
    for _linha_geo in load_geocalor_cardioresp_cuiaba_block():
        lines.append(_linha_geo)
'''

def main():
    print("=" * 70)
    print("V11.12 - PATCH ALERTA CUIABA GEOCALOR CARDIORESP")
    print("=" * 70)

    if not ARQ.exists():
        raise SystemExit(f"ERRO: arquivo não encontrado: {ARQ}")

    original = ARQ.read_text(encoding="utf-8", errors="replace")
    txt = original

    if "load_geocalor_cardioresp_cuiaba_block" not in txt:
        marker_func = "\ndef compose_text(payload: dict[str, Any]) -> str:"
        if marker_func not in txt:
            raise SystemExit("ERRO: não encontrei def compose_text.")
        txt = txt.replace(marker_func, "\n" + HELPER + marker_func)

    if "for _linha_geo in load_geocalor_cardioresp_cuiaba_block()" not in txt:
        marker = '    lines.append("Recomendações específicas para Cuiabá:")'
        if marker not in txt:
            raise SystemExit("ERRO: marcador de recomendações de Cuiabá não encontrado.")
        txt = txt.replace(marker, INSERT + "\n" + marker)

    bak = ARQ.with_suffix(ARQ.suffix + f".bak_geocalor_cardioresp_v11_12_{datetime.now():%Y%m%d_%H%M%S}")
    bak.write_text(original, encoding="utf-8")

    ARQ.write_text(txt, encoding="utf-8")
    py_compile.compile(str(ARQ), doraise=True)

    print(f"OK: alerta de Cuiabá atualizado: {ARQ}")
    print(f"Backup: {bak}")

if __name__ == "__main__":
    main()
