# -*- coding: utf-8 -*-
"""
VALIDACAO OPERACIONAL V11.7 - ARARAS MT

Gera:
- data/output/validacao_operacional_v11_7.txt
- data/output/validacao_operacional_v11_7.csv
"""

import sqlite3
from pathlib import Path
from datetime import datetime
import pandas as pd

DB = Path("data/output/sis_integrado.db")
OUT_DIR = Path("data/output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def table_exists(con, name):
    q = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?", con, params=(name,))
    return not q.empty

def count_table(con, name):
    if not table_exists(con, name):
        return None
    return int(pd.read_sql(f"SELECT COUNT(*) n FROM {name}", con).iloc[0]["n"])

def get_cols(con, table):
    if not table_exists(con, table):
        return []
    return list(pd.read_sql(f"PRAGMA table_info({table})", con)["name"])

def add(rows, item, status, detalhe):
    rows.append({"item": item, "status": status, "detalhe": detalhe})

def main():
    rows = []
    if not DB.exists():
        add(rows, "Banco SQLite", "ERRO", f"Banco não encontrado: {DB}")
        df = pd.DataFrame(rows)
        df.to_csv(OUT_DIR / "validacao_operacional_v11_7.csv", index=False, encoding="utf-8-sig")
        print(df.to_string(index=False))
        raise SystemExit(1)

    con = sqlite3.connect(DB)

    add(rows, "Banco SQLite", "OK", str(DB))

    # Tabelas essenciais
    essenciais = [
        "resumo_municipal_atual",
        "met_biometeo",
        "qualidade_ar_municipal",
        "hospital_ocupacao_municipio",
        "hospital_ocupacao_estado",
        "ops_resumo_operacional_cnes",
        "alerta_inteligente_municipal_v6",
        "v9_priorizacao_epidemiologica",
        "historico_envios_alertas_v10_2",
    ]

    for t in essenciais:
        n = count_table(con, t)
        if n is None:
            add(rows, f"Tabela {t}", "AVISO", "não encontrada")
        elif n == 0:
            add(rows, f"Tabela {t}", "AVISO", "existe, mas está vazia")
        else:
            add(rows, f"Tabela {t}", "OK", f"{n} linhas")

    # Resumo municipal
    if table_exists(con, "resumo_municipal_atual"):
        cols = get_cols(con, "resumo_municipal_atual")
        rm = pd.read_sql("SELECT * FROM resumo_municipal_atual", con)
        n = len(rm)
        cod_col = "cod_ibge" if "cod_ibge" in rm.columns else None
        mun_col = "municipio" if "municipio" in rm.columns else None

        add(rows, "Municípios no resumo", "OK" if n >= 141 else "AVISO", f"{n} linhas")

        if cod_col:
            unicos = rm[cod_col].nunique(dropna=True)
            add(rows, "Municípios únicos cod_ibge", "OK" if unicos >= 141 else "AVISO", f"{unicos} códigos únicos")

        if "nivel" in rm.columns:
            dist = rm["nivel"].fillna("cinza").astype(str).str.lower().value_counts().to_dict()
            soma = sum(dist.values())
            alerta = sum(dist.get(x, 0) for x in ["laranja", "vermelha", "roxa"])
            detalhe = f"distribuição={dist}; soma={soma}; >=laranja={alerta}"
            add(rows, "Distribuição de níveis", "OK" if soma == n else "AVISO", detalhe)

            verm = rm[rm["nivel"].fillna("").astype(str).str.lower().eq("vermelha")]
            if not verm.empty and mun_col:
                add(rows, "Municípios vermelhos", "OK", "; ".join(verm[mun_col].astype(str).tolist()))
            else:
                add(rows, "Municípios vermelhos", "OK", "nenhum município em vermelho")

        for col in ["ocupacao_leitos_pct", "pressao_calor_pct", "pm25_ugm3", "risco_cumulativo_3d"]:
            if col in rm.columns:
                preench = int(rm[col].notna().sum())
                status = "OK" if preench >= max(1, int(0.8 * n)) else "AVISO"
                add(rows, f"Preenchimento {col}", status, f"{preench}/{n} preenchidos")
            else:
                add(rows, f"Coluna {col}", "AVISO", "não encontrada no resumo_municipal_atual")

    # Predição
    if table_exists(con, "predicao_calor_7d_municipal_v6"):
        pred = pd.read_sql("SELECT * FROM predicao_calor_7d_municipal_v6", con)
        cols = list(pred.columns)
        add(rows, "Predição 7 dias", "OK" if len(pred) > 0 else "AVISO", f"{len(pred)} linhas; colunas={cols[:12]}")
        if "nivel_predicao_7d" in pred.columns:
            distp = pred["nivel_predicao_7d"].fillna("cinza").astype(str).str.lower().value_counts().to_dict()
            add(rows, "Distribuição predição 7d", "OK", str(distp))
        else:
            add(rows, "Coluna nivel_predicao_7d", "AVISO", "não existe; dispatcher usa fallback cinza")
    else:
        add(rows, "Predição 7 dias", "AVISO", "tabela predicao_calor_7d_municipal_v6 não encontrada; dispatcher usa fallback cinza")

    # Histórico de envio hoje
    if table_exists(con, "historico_envios_alertas_v10_2"):
        hoje = pd.read_sql("""
            SELECT data_alerta, escopo, canal, status_envio, COUNT(*) n
            FROM historico_envios_alertas_v10_2
            WHERE data_alerta = date('now','localtime')
            GROUP BY data_alerta, escopo, canal, status_envio
            ORDER BY escopo, canal, status_envio
        """, con)
        if hoje.empty:
            add(rows, "Envios hoje", "AVISO", "sem registros de envio para a data local de hoje")
        else:
            add(rows, "Envios hoje", "OK", hoje.to_string(index=False).replace("\n", " | "))

        erros = pd.read_sql("""
            SELECT COUNT(*) n
            FROM historico_envios_alertas_v10_2
            WHERE data_alerta = date('now','localtime') AND status_envio <> 'enviado'
        """, con).iloc[0]["n"]
        add(rows, "Erros de envio hoje", "OK" if int(erros) == 0 else "AVISO", f"{int(erros)} registros não enviados")

    con.close()

    df = pd.DataFrame(rows)
    csv_path = OUT_DIR / "validacao_operacional_v11_7.csv"
    txt_path = OUT_DIR / "validacao_operacional_v11_7.txt"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    lines = []
    lines.append("=" * 70)
    lines.append("VALIDAÇÃO OPERACIONAL V11.7 - ARARAS MT")
    lines.append(f"Gerado em: {datetime.now():%Y-%m-%d %H:%M:%S}")
    lines.append("=" * 70)
    lines.append(df.to_string(index=False))
    txt_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print()
    print(f"CSV: {csv_path}")
    print(f"TXT: {txt_path}")

    if (df["status"] == "ERRO").any():
        raise SystemExit(1)

if __name__ == "__main__":
    main()
