# -*- coding: utf-8 -*-
"""
Sonda o Centralizador e-SUS APS (Postgres esus2).

Requer VPN SES (ou execução no servidor) e ESUS_APS_* no .env.

  .\\.venv\\Scripts\\python.exe scripts\\explorar_esus_aps.py

Não extrai PII (nome, CPF, CNS, endereço). Só metadados e agregados.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sisclima.ingestion.esus_aps import (  # noqa: E402
    build_esus_aps_url,
    classify_esus_layout,
    credentials_ready,
    esus_aps_config,
    fetch_columns,
    fetch_date_bounds,
    fetch_reltuples,
    fetch_table_catalog,
    get_esus_engine,
    is_pii_column,
    probe_tcp_ports,
    read_esus_sql,
    reset_esus_engine,
    select_relevant_tables,
    suggest_indicators,
    use_esus_aps,
)

REPORT_JSON = ROOT / "docs" / "esus_aps_exploracao.json"
REPORT_MD = ROOT / "docs" / "esus_aps_exploracao.md"
FALLBACK_PORTS = (5432, 5433)


def _session_info(reader) -> dict[str, Any]:
    sql = """
    SELECT
      version() AS pg_version,
      current_database() AS database,
      current_user AS current_user,
      inet_server_addr()::text AS server_addr,
      inet_server_port() AS server_port
    """
    df = reader(sql)
    if df is None or df.empty:
        return {}
    row = df.iloc[0].to_dict()
    return {k: (None if v is None else str(v)) for k, v in row.items()}


def _inspect_table(schema: str, table: str, reader) -> dict[str, Any]:
    cols_df = fetch_columns(schema, table, reader)
    columns: list[dict[str, str]] = []
    date_like: list[str] = []
    if cols_df is not None and not cols_df.empty:
        for rec in cols_df.to_dict(orient="records"):
            name = str(rec.get("column_name") or "")
            dtype = str(rec.get("data_type") or rec.get("udt_name") or "")
            pii = is_pii_column(name)
            columns.append(
                {
                    "name": name,
                    "type": dtype,
                    "pii": pii,
                }
            )
            if not pii:
                date_like.append(name)
    reltuples = fetch_reltuples(schema, table, reader)
    bounds: dict[str, Any] = {}
    try:
        bounds = fetch_date_bounds(schema, table, date_like, reader)
    except Exception as exc:  # noqa: BLE001
        bounds = {"erro": str(exc)}
    return {
        "schema": schema,
        "table": table,
        "n_colunas": len(columns),
        "colunas_pii": [c["name"] for c in columns if c["pii"]],
        "colunas": columns,
        "reltuples": reltuples,
        "datas": bounds,
    }


def _markdown(report: dict[str, Any]) -> str:
    tcp = report.get("tcp") or {}
    sess = report.get("sessao") or {}
    layout = report.get("layout") or {}
    lines = [
        "# Inventário e-SUS APS (sonda local)",
        "",
        f"Gerado em `{report.get('gerado_em')}` — **não versionar** (metadados da sessão).",
        "",
        "## Conexão",
        "",
        f"- Host: `{report.get('host')}`",
        f"- Porta configurada: `{report.get('port')}`",
        f"- Porta TCP aberta: `{tcp.get('open_port')}`",
        f"- Banco: `{report.get('database')}`",
        f"- SSL: `{report.get('sslmode')}`",
        f"- Usuário da sessão: `{sess.get('current_user') or '—'}`",
        f"- `version()`: `{sess.get('pg_version') or '—'}`",
        "",
        "## Classificação",
        "",
        f"- Tipo: **{layout.get('kind')}**",
        f"- Fatos `tb_fat_*`: {len(layout.get('facts') or [])}",
        f"- Dimensões `tb_dim_*`: {len(layout.get('dims') or [])}",
        f"- Hits PEC (`tb_cidadao` / `tb_atend`): {layout.get('pec_hits') or []}",
        "",
        "## Indicadores candidatos",
        "",
        "| Id | Status | Tabelas | Uso |",
        "|---|---|---|---|",
    ]
    for ind in report.get("indicadores") or []:
        lines.append(
            f"| {ind.get('id')} | {ind.get('status')} | {ind.get('tabelas') or '—'} | {ind.get('uso')} |"
        )
    lines += ["", "## Tabelas relevantes (amostra de metadados)", ""]
    for item in report.get("tabelas_detalhe") or []:
        lines.append(f"### `{item.get('schema')}.{item.get('table')}`")
        lines.append("")
        lines.append(f"- colunas: {item.get('n_colunas')} (PII omitidas da extração: {item.get('colunas_pii') or '—'})")
        lines.append(f"- `reltuples` (aprox.): {item.get('reltuples')}")
        datas = item.get("datas") or {}
        if datas.get("coluna"):
            lines.append(
                f"- intervalo `{datas.get('coluna')}`: {datas.get('min')} → {datas.get('max')}"
            )
        lines.append("")
    lines += [
        "## Próximo passo",
        "",
        "Confirmar tabelas reais deste `esus2` e só então versionar SQL agregado em `sql/esus_aps_*.sql`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if not use_esus_aps():
        print("USE_ESUS_APS=false — ligue a flag no .env (VPN SES).")
        return 1

    try:
        cfg = esus_aps_config()
    except ValueError as exc:
        print(f"Configuração incompleta: {exc}")
        return 1

    host = cfg["host"]
    port = int(cfg["port"])
    ports = [port] + [p for p in FALLBACK_PORTS if p != port]
    tcp = probe_tcp_ports(host, ports, timeout=float(cfg.get("connect_timeout") or 15))
    print(f"=== TCP {host} ===")
    for attempt in tcp.get("attempts") or []:
        status = "ok" if attempt.get("ok") else attempt.get("error")
        print(f"  porta {attempt.get('port')}: {status}")

    if tcp.get("open_port") and int(tcp["open_port"]) != port:
        print(f"Porta {port} fechada; usando {tcp['open_port']} nesta sessão.")
        cfg = dict(cfg)
        cfg["port"] = int(tcp["open_port"])
        reset_esus_engine()

    if not tcp.get("open_port"):
        print("Nenhuma porta Postgres respondeu (5432/5433). Confira VPN SES.")
        report = {
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "host": host,
            "port": port,
            "database": cfg.get("database"),
            "sslmode": cfg.get("sslmode"),
            "tcp": tcp,
            "erro": "tcp_indisponivel",
        }
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2

    if not credentials_ready(cfg):
        print("ESUS_APS_USER / ESUS_APS_PASSWORD vazios no .env — preencha a conta de leitura.")
        return 1

    print(f"URL (senha oculta): {build_esus_aps_url(cfg, hide_password=True)}")
    engine = get_esus_engine(cfg)

    def reader(sql: str, params: dict | None = None):
        return read_esus_sql(sql, params, engine=engine)

    try:
        sess = _session_info(reader)
        catalog = fetch_table_catalog(reader)
    except Exception as exc:  # noqa: BLE001
        print(f"Falha ao autenticar/consultar metadados: {exc}")
        return 3

    tables: list[str] = []
    schema_map: dict[str, str] = {}
    if catalog is not None and not catalog.empty:
        for rec in catalog.to_dict(orient="records"):
            name = str(rec.get("table_name") or "")
            schema = str(rec.get("table_schema") or "public")
            tables.append(name)
            schema_map[name.lower()] = schema

    layout = classify_esus_layout(tables)
    relevant = select_relevant_tables(tables)
    detalhes = []
    for name in relevant:
        schema = schema_map.get(name, cfg.get("schema") or "public")
        print(f"--- {schema}.{name} ---")
        try:
            info = _inspect_table(schema, name, reader)
        except Exception as exc:  # noqa: BLE001
            info = {"schema": schema, "table": name, "erro": str(exc)}
        detalhes.append(info)
        print(f"  colunas={info.get('n_colunas')} reltuples={info.get('reltuples')}")

    indicadores = suggest_indicators(tables)
    report = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "host": host,
        "port": cfg["port"],
        "database": cfg.get("database"),
        "sslmode": cfg.get("sslmode"),
        "tcp": tcp,
        "sessao": sess,
        "layout": layout,
        "n_tabelas": len(tables),
        "tabelas": sorted(set(tables)),
        "indicadores": indicadores,
        "tabelas_detalhe": detalhes,
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(_markdown(report), encoding="utf-8")
    print(f"\nTipo: {layout.get('kind')} | tabelas={len(tables)}")
    print(f"Relatório: {REPORT_JSON}")
    print(f"Resumo: {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
