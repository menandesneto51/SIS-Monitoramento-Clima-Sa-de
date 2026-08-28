# -*- coding: utf-8 -*-
"""Importa e-mails municipais (COSEMS) e participantes da Sala (Portaria 0590).

Não cria senha nem libera fan-out. Municípios entram PENDENTE/ativo=0.
Participantes da Sala vão para config/plano_el_nino_participantes.yaml.

  python scripts/importar_catalogos_acesso.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sisclima.plano.participantes import (  # noqa: E402
    CATALOGO_PATH,
    EMAILS_SECRETARIA,
    area_id_do_catalogo,
    perfil_sugerido,
)


def _txt(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _mun_key(s: str) -> str:
    t = _txt(s).casefold()
    return t.replace("'", "").replace("’", "").replace("`", "")


def _email(v) -> str:
    t = _txt(v).lower()
    return t if "@" in t else ""


def _load_sheet(path: Path, sheet: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    hdr = 0
    for i in range(min(8, len(raw))):
        vals = [str(x).strip().lower() for x in raw.iloc[i].tolist()]
        joined = " ".join(vals)
        if "e-mail" in joined or "email" in joined:
            if any(k in joined for k in ("nome", "munic", "área", "area", "unidade")):
                hdr = i
                break
        if "id" in vals and any("munic" in v for v in vals):
            hdr = i
            break
    df = pd.read_excel(path, sheet_name=sheet, header=hdr)
    return df.dropna(how="all")


def importar_municipios(xlsx: Path, csv_out: Path) -> dict:
    df = _load_sheet(xlsx, "Destinatarios_Alertas")
    rows = []
    for _, r in df.iterrows():
        email = _email(r.get("E-mail institucional"))
        mun = _txt(r.get("Município"))
        if not email or not mun:
            continue
        validacao = _txt(r.get("Validação operacional")).upper() or "PENDENTE"
        rows.append(
            {
                "tipo_destinatario": "municipal",
                "regional_saude": _txt(r.get("Região de Saúde")),
                "cod_ibge": "",
                "municipio": mun,
                "nome": _txt(r.get("Secretário(a)")) or f"SMS {mun}",
                "email": email,
                "telegram_chat_id": "",
                "ativo": "1" if validacao == "APROVADO" else "0",
                "validacao_operacional": validacao,
            }
        )
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(csv_out, index=False, encoding="utf-8-sig")
    return {"n": len(rows), "aprovados": sum(1 for x in rows if x["ativo"] == "1"), "path": str(csv_out)}


def importar_participantes(xlsx: Path, dest_xlsx: Path, yaml_out: Path) -> dict:
    from sisclima.auth.access import lookup_territorio

    gt = _load_sheet(xlsx, "Grupo_Tecnico")
    cp = _load_sheet(xlsx, "Cadastro_Pessoas")
    me = _load_sheet(xlsx, "Municipios_Estrategicos")
    dest = _load_sheet(dest_xlsx, "Destinatarios_Alertas")
    dest_map = {
        _mun_key(r.get("Município")): _email(r.get("E-mail institucional"))
        for _, r in dest.iterrows()
        if _txt(r.get("Município"))
    }

    pessoas: dict[str, dict] = {}

    def upsert(row: dict) -> None:
        email = row.get("email") or ""
        key = email or _txt(row.get("nome")).casefold()
        if not key:
            return
        prev = pessoas.get(key) or {}
        merged = {**prev, **{k: v for k, v in row.items() if v}}
        if prev.get("area_id") and prev["area_id"] != "multi_area" and merged.get("area_id") in {"", "multi_area"}:
            merged["area_id"] = prev["area_id"]
        if prev.get("sigla") and not merged.get("sigla"):
            merged["sigla"] = prev["sigla"]
        merged["perfil_sugerido"] = perfil_sugerido(merged)
        pessoas[key] = merged

    for _, r in gt.iterrows():
        nome = _txt(r.get("Nome"))
        email = _email(r.get("E-mail"))
        area_txt = _txt(r.get("Área técnica (fonte)"))
        sigla = _txt(r.get("Enquadramento"))
        superintendencia = _txt(r.get("Superintendência (fonte)"))
        area_id = area_id_do_catalogo(sigla=sigla, area_texto=area_txt, superintendencia=superintendencia)
        papel = "titular" if "titular formal" in _txt(r.get("Situação para Sala de Situação")).casefold() else "grupo_tecnico"
        rec = {
            "nome": nome,
            "email": email,
            "sigla": sigla,
            "area_texto": area_txt,
            "superintendencia": superintendencia,
            "area_id": area_id,
            "papel": papel,
            "telefone": _txt(r.get("Telefone")),
            "status_indicacao": _txt(r.get("Situação para Sala de Situação")),
            "fonte": "Grupo_Tecnico",
        }
        rec["perfil_sugerido"] = perfil_sugerido(rec)
        upsert(rec)

    for _, r in cp.iterrows():
        nome = _txt(r.get("Nome"))
        email = _email(r.get("E-mail"))
        area_txt = _txt(r.get("Área/Programa"))
        papel_raw = _txt(r.get("Papel no Plano El Niño"))
        area_id = area_id_do_catalogo(area_texto=area_txt)
        if _norm_is_cievs(email, area_txt):
            area_id = "cievs"
        papel = "grupo_tecnico"
        pl = papel_raw.casefold()
        if pl == "titular":
            papel = "titular"
        elif "suplente" in pl:
            papel = "suplente"
        elif "secretaria" in pl or email in EMAILS_SECRETARIA:
            papel = "secretaria_executiva"
        rec = {
            "nome": nome,
            "email": email,
            "sigla": "",
            "area_texto": area_txt,
            "superintendencia": _txt(r.get("Superintendência/Gabinete")),
            "area_id": area_id,
            "papel": papel,
            "telefone": _txt(r.get("Telefone")),
            "status_indicacao": _txt(r.get("Status da definição")),
            "fonte": "Cadastro_Pessoas",
        }
        rec["perfil_sugerido"] = perfil_sugerido(rec)
        upsert(rec)

    municipios = []
    for _, r in me.iterrows():
        mun = _txt(r.get("Município estratégico"))
        if not mun:
            continue
        _m, regional, ibge = lookup_territorio(municipio=mun)
        email = dest_map.get(_mun_key(mun), "")
        municipios.append(
            {
                "municipio": _m or mun,
                "regional_saude": regional,
                "cod_ibge": ibge,
                "email_sms": email,
                "indicacao_local": _txt(r.get("Indicação localizada?")),
            }
        )

    com_email = [p for p in pessoas.values() if p.get("email")]
    payload = {
        "fonte": xlsx.name,
        "ato": "Portaria nº 0590/2026/GBSES",
        "atualizado_em": "2026-08-25",
        "regra": "Sala só abre para ses/admin. SMS usa e-mail municipal no painel interno, sem a Sala. Vínculo não cria senha.",
        "participantes": sorted(com_email, key=lambda x: x.get("nome") or ""),
        "sem_email": sorted(
            [p["nome"] for p in pessoas.values() if p.get("nome") and not p.get("email")],
        ),
        "municipios_estrategicos": municipios,
    }
    yaml_out.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    return {
        "n_participantes": len(com_email),
        "sem_email": len(payload["sem_email"]),
        "n_municipios": len(municipios),
        "com_email_sms": sum(1 for m in municipios if m.get("email_sms")),
        "path": str(yaml_out),
    }


def _norm_is_cievs(email: str, area_txt: str) -> bool:
    return email in EMAILS_SECRETARIA or "cievs" in area_txt.casefold() or "vigidesastre" in area_txt.casefold()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--indicacoes",
        default=str(Path.home() / "Downloads" / "Controle_Indicacoes_El_Nino_SES_MT_2026.xlsx"),
    )
    parser.add_argument(
        "--destinatarios",
        default=str(ROOT / "data" / "input" / "ARARAS_MT_Destinatarios_Alertas_2026.xlsx"),
    )
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "input" / "contatos_alertas.csv"))
    parser.add_argument("--yaml-out", default=str(CATALOGO_PATH))
    args = parser.parse_args()
    ind = Path(args.indicacoes)
    dest = Path(args.destinatarios)
    if not ind.exists():
        alt = ROOT / "data" / "input" / ind.name
        if alt.exists():
            ind = alt
        else:
            print(f"Planilha de indicações não encontrada: {ind}")
            return 1
    if not dest.exists():
        print(f"Planilha de destinatários não encontrada: {dest}")
        return 1
    mun = importar_municipios(dest, Path(args.csv_out))
    pes = importar_participantes(ind, dest, Path(args.yaml_out))
    print(f"Municípios COSEMS: {mun['n']} e-mails ({mun['aprovados']} APROVADO) → {mun['path']}")
    print(
        f"Sala: {pes['n_participantes']} com e-mail · {pes['sem_email']} sem e-mail · "
        f"{pes['n_municipios']} municípios estratégicos ({pes['com_email_sms']} com e-mail SMS) → {pes['path']}"
    )
    print("Fan-out continua desligado até Validação operacional = APROVADO. Vínculos: aba Acessos da Sala.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
