# -*- coding: utf-8 -*-
"""Cálculo e registro dos 88 indicadores do Plano (fonte oficial = ARARAS)."""
from __future__ import annotations

import re
from typing import Any

from sisclima.core.db import db_conn, fetchall
from sisclima.core.logging_utils import get_logger
from sisclima.plano.acesso import pode_editar_area
from sisclima.plano.catalogo import carregar_catalogo, indicador_por_id, indicadores_do_indice
from sisclima.plano.operacao import percentual_implementacao, registrar_atualizacao
from sisclima.plano.schema import garantir_schema

log = get_logger(__name__)

_RE_FRACAO = re.compile(r"(\d+)\s*/\s*(\d+)")
_RE_VERDE = re.compile(r"verde\s*[=≥]\s*(\d+)", re.I)
_RE_AMARELO = re.compile(r"amarelo\s*[=]\s*(\d+)", re.I)
_RE_VERMELHO = re.compile(r"vermelho\s*[<=]\s*(\d+)", re.I)


def progresso(numerador: float | None, denominador: float | None) -> float | None:
    """15/20 → 75. A área não calcula o percentual."""
    if numerador is None or denominador in (None, 0):
        return None
    return percentual_implementacao(int(numerador), int(denominador))


def parse_denominador(indicador: dict[str, Any]) -> int | None:
    """Denominador conhecido no catálogo (ex.: 16 ERS, binário = 1)."""
    meta = str(indicador.get("meta_numerica") or "")
    formula = str(indicador.get("formula") or "")
    unidade = str(indicador.get("unidade") or "")
    m = _RE_FRACAO.search(meta) or _RE_FRACAO.search(formula)
    if m:
        return int(m.group(2))
    if "binário" in unidade.casefold() or meta.strip().casefold() in {"sim", "não", "nao"}:
        return 1
    m2 = re.search(r"÷\s*(\d+)", formula)
    if m2:
        return int(m2.group(1))
    return None


def limiares_semaforo(indicador: dict[str, Any]) -> tuple[float, float]:
    """Retorna (mínimo verde, mínimo amarelo)."""
    texto = str(indicador.get("semaforo") or "")
    verde, amarelo = 100.0, 70.0
    gv = _RE_VERDE.search(texto)
    ga = _RE_AMARELO.search(texto)
    gr = _RE_VERMELHO.search(texto)
    if gv:
        verde = float(gv.group(1))
    if ga:
        amarelo = float(ga.group(1))
    elif gr:
        amarelo = float(gr.group(1))
    return verde, amarelo


def semaforo(pct: float | None, indicador: dict[str, Any] | None = None) -> str:
    if pct is None:
        return "nao_informado"
    verde, amarelo = limiares_semaforo(indicador or {})
    if pct >= verde:
        return "meta_atingida"
    if pct >= amarelo:
        return "em_andamento"
    if pct > 0:
        return "atraso_risco"
    return "nao_iniciado"


def rotulo_semaforo(codigo: str) -> str:
    return {
        "nao_informado": "⚪ Sem informação",
        "nao_iniciado": "⚪ Não iniciado",
        "em_andamento": "🟡 Em andamento",
        "atraso_risco": "🟠 Abaixo do esperado",
        "meta_atingida": "🟢 Meta atingida",
        "em_validacao": "🟠 Em validação",
        "rejeitado": "🔴 Correção solicitada",
        "automatico": "🔵 Automático (fonte)",
        "alias": "🔗 Alias (ver canônico)",
        "sinal_gatilho": "🟣 Gatilho (não é meta)",
        "nao_aplicavel": "⚪ N/A (denominador 0)",
        "nao_calculavel": "⚪ Não calculável",
    }.get(codigo, codigo)


def parse_valor_fracao(valor: str | None) -> tuple[int | None, int | None]:
    raw = str(valor or "").strip()
    m = _RE_FRACAO.search(raw)
    if m:
        return int(m.group(1)), int(m.group(2))
    if raw in {"1", "sim", "true", "Sim"}:
        return 1, 1
    if raw in {"0", "nao", "não", "false", "Não"}:
        return 0, 1
    try:
        return int(float(raw)), None
    except (TypeError, ValueError):
        return None, None


def _ultima_leitura(codigo: str) -> dict[str, Any] | None:
    garantir_schema()
    with db_conn() as conn:
        rows = fetchall(
            conn,
            """
            SELECT * FROM atualizacao
            WHERE alvo = 'indicador' AND alvo_codigo = ?
            ORDER BY id DESC
            """,
            (codigo,),
        )
    return dict(rows[0]) if rows else None


def avaliar_indicador(indicador: dict[str, Any], leitura: dict[str, Any] | None) -> dict[str, Any]:
    modo = str(indicador.get("modo_atualizacao") or "documental")
    papel = str(indicador.get("papel_operacional") or "")
    denom_cat = parse_denominador(indicador)
    num = den = pct = None
    situacao = "nao_informado"
    if papel == "alias":
        sem = "alias"
    elif leitura:
        num, den = parse_valor_fracao(str(leitura.get("valor") or ""))
        if den is None:
            den = denom_cat
        if den == 0:
            pct = None
            sem = "nao_aplicavel"
        else:
            pct = progresso(num, den)
            situacao = str(leitura.get("situacao_validacao") or "informado")
            if situacao == "em_validacao":
                sem = "em_validacao"
            elif situacao == "rejeitado":
                sem = "rejeitado"
            elif papel == "gatilho":
                sem = "sinal_gatilho"
            else:
                sem = semaforo(pct, indicador)
    else:
        if modo == "automatico":
            sem = "automatico"
        elif papel == "gatilho":
            sem = "nao_informado"
        else:
            sem = "nao_informado"
    oficial = situacao == "validado" and sem == "meta_atingida" and papel not in {"gatilho", "alias"}
    return {
        "id": indicador.get("id"),
        "codigo_fonte": indicador.get("codigo_fonte"),
        "nome": indicador.get("nome_ajustado") or indicador.get("nome"),
        "nome_original": indicador.get("nome"),
        "area_id": indicador.get("area_id"),
        "acao_id": indicador.get("acao_id"),
        "tipo": indicador.get("tipo"),
        "modo": modo,
        "papel_operacional": papel,
        "perfil_s": indicador.get("perfil_s") or "",
        "padrao_completude": indicador.get("padrao_completude") or "",
        "decisao_adequacao": indicador.get("decisao_adequacao") or "",
        "alvo_automacao": indicador.get("alvo_automacao") or "",
        "alteracao_proposta": indicador.get("alteracao_proposta") or "",
        "subindicadores": list(indicador.get("subindicadores") or []),
        "entra_no_indice": bool(indicador.get("entra_no_indice")) and papel not in {"gatilho", "alias"},
        "numerador": num,
        "denominador": den if den is not None else denom_cat,
        "percentual": pct,
        "semaforo": sem,
        "rotulo": rotulo_semaforo(sem),
        "oficial": oficial,
        "situacao_validacao": situacao if leitura else None,
        "editavel": modo != "automatico" and papel != "alias",
        "classe_emergencia": indicador.get("classe_emergencia") or "",
        "perfil_escalonamento": indicador.get("perfil_escalonamento") or "",
        "gate_prontidao": bool(indicador.get("gate_prontidao")),
        "id_canonico": indicador.get("id_canonico") or "",
    }


def registrar_leitura(
    *,
    user: dict[str, Any],
    indicador_id: str,
    numerador: float | None = None,
    denominador: float | None = None,
    binario: bool | None = None,
    observacao: str = "",
    enviar_validacao: bool = True,
) -> tuple[bool, str, int | None]:
    """Área informa o dado bruto. O ARARAS calcula. Automático não aceita digitação."""
    ind = indicador_por_id(indicador_id)
    if not ind:
        return False, "Indicador não encontrado no catálogo.", None
    if not pode_editar_area(user, str(ind.get("area_id") or "")):
        return False, "Área isolada: este perfil não atualiza indicador de outra área.", None
    modo = str(ind.get("modo_atualizacao") or "")
    if modo == "automatico":
        return False, "Indicador automático: o valor vem da fonte, não da digitação da área.", None
    den_cat = parse_denominador(ind)
    if binario is not None:
        valor = "1/1" if binario else "0/1"
        pct = 100.0 if binario else 0.0
    else:
        den = denominador if denominador not in (None, 0) else den_cat
        if numerador is None or den in (None, 0):
            return False, "Informe numerador e denominador (ex.: 15 de 20).", None
        valor = f"{int(numerador)}/{int(den)}"
        pct = progresso(numerador, den)
    status = "em_validacao" if enviar_validacao else "em_andamento"
    ok, msg, novo_id = registrar_atualizacao(
        user=user,
        acao_codigo=str(ind.get("acao_id") or ind.get("id")),
        status=status,
        valor=valor,
        observacao=observacao or f"{ind.get('id')} = {valor} ({pct}%)",
        alvo="indicador",
        alvo_codigo=str(ind.get("id")),
    )
    if ok:
        msg = f"{msg} Resultado: {valor} = {pct}% {rotulo_semaforo(semaforo(pct, ind))}."
    return ok, msg, novo_id


def quadro_indicadores(*, area_id: str | None = None, so_indice: bool = False, **_extra) -> list[dict[str, Any]]:
    if "so_indice" in _extra:
        so_indice = bool(_extra["so_indice"])
    cat = carregar_catalogo()
    itens = indicadores_do_indice(cat) if so_indice else list(cat.get("indicadores") or [])
    if area_id:
        itens = [i for i in itens if str(i.get("area_id") or "") == area_id]
    out = []
    for ind in itens:
        leitura = _ultima_leitura(str(ind.get("id")))
        out.append(avaliar_indicador(ind, leitura))
    return out


def cumprimento_indice(quadro: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Média dos indicadores do índice com leitura validada. Sem dado = 0% oficial."""
    rows = quadro if quadro is not None else quadro_indicadores(so_indice=True)
    indice = [r for r in rows if r.get("entra_no_indice")]
    total = len(indice)
    com_dado = [r for r in indice if r.get("percentual") is not None]
    validados = [r for r in indice if r.get("situacao_validacao") == "validado"]
    metas = [r for r in validados if r.get("semaforo") == "meta_atingida"]
    media = round(sum(float(r["percentual"]) for r in com_dado) / len(com_dado), 1) if com_dado else 0.0
    return {
        "n_indice": total,
        "n_com_dado": len(com_dado),
        "n_validados": len(validados),
        "n_meta": len(metas),
        "percentual_operacional": media if com_dado else 0.0,
        "percentual_oficial": percentual_implementacao(len(metas), total) if total else 0.0,
        "oficial": bool(total and len(metas) == total),
        "n_indice": total,
        "n_meta": len(metas),
        "percentual_operacional": media if com_dado else 0.0,
    }


def registrar_leitura_sistema(leitura: dict[str, Any]) -> tuple[bool, str, int | None]:
    """Grava coleta automática. Não passa pela digitação da área."""
    if leitura.get("status") != "ok":
        return False, str(leitura.get("motivo") or "aguardando fonte"), None
    return _gravar_automatico(leitura)


def atualizar_automaticos() -> dict[str, Any]:
    from sisclima.plano.conectores import coletar_automaticos

    gravados = 0
    inalterados = 0
    aguardando = 0
    erros = 0
    leituras = coletar_automaticos()
    for leitura in leituras:
        if leitura.get("status") != "ok":
            aguardando += 1
            continue
        ok, msg, _ = _gravar_automatico(leitura)
        if ok and msg == "inalterado":
            inalterados += 1
        elif ok:
            gravados += 1
        else:
            erros += 1
            log.warning("auto %s: %s", leitura.get("indicador_id"), msg)
    return {
        "gravados": gravados,
        "inalterados": inalterados,
        "aguardando_fonte": aguardando,
        "erros": erros,
        "n": len(leituras),
        "ok": gravados + inalterados,
    }


def _gravar_automatico(leitura: dict[str, Any]) -> tuple[bool, str, int | None]:
    from sisclima.plano.conectores import USUARIO_SISTEMA
    from sisclima.plano.operacao import registrar_atualizacao

    ind = indicador_por_id(str(leitura.get("indicador_id")))
    if not ind:
        return False, "indicador ausente", None
    valor = f"{int(leitura['numerador'])}/{int(leitura['denominador'])}"
    anterior = _ultima_leitura(str(ind.get("id")))
    if anterior and str(anterior.get("valor") or "") == valor:
        return True, "inalterado", int(anterior["id"]) if anterior.get("id") is not None else None
    return registrar_atualizacao(
        user=USUARIO_SISTEMA,
        acao_codigo=str(ind.get("acao_id") or ind.get("id")),
        status="em_andamento",
        valor=valor,
        observacao=f"auto:{leitura.get('fonte')}",
        alvo="indicador",
        alvo_codigo=str(ind.get("id")),
    )


def linhas_painel_indicadores(
    *,
    quadro: list[dict[str, Any]] | None = None,
    leituras_auto: list[dict[str, Any]] | None = None,
    area_id: str | None = None,
    **kw: Any,
) -> list[dict[str, Any]]:
    """Quadro operacional: 88 indicadores + situação da coleta automática (sem inventar valor)."""
    from sisclima.plano.areas import rotulo_area
    from sisclima.plano.conectores import BLOCO_AGUARDANDO, ESTOQUE_DEFASADO
    from sisclima.plano.sugestoes import enriquecer_linhas, sugerir_indicador

    rows = quadro if quadro is not None else quadro_indicadores(area_id=area_id)
    if leituras_auto is None:
        leituras_auto = kw.get("leituras_auto")
    auto_map = {str(r.get("indicador_id")): r for r in (leituras_auto or [])}
    out: list[dict[str, Any]] = []
    for r in rows:
        iid = str(r.get("id") or "")
        modo = str(r.get("modo") or "")
        auto = auto_map.get(iid)
        nota = ""
        if modo == "automatico":
            if auto and auto.get("status") == "ok":
                situacao = "coletado"
                fonte = str(auto.get("fonte") or "pipeline")
                num = auto.get("numerador")
                den = auto.get("denominador")
                if iid in ESTOQUE_DEFASADO:
                    nota = "carga de estoque pode estar defasada"
            elif auto and auto.get("status") != "ok":
                situacao = "aguardando_fonte"
                fonte = str(auto.get("motivo") or "aguardando fonte")
                num = None
                den = r.get("denominador")
            elif r.get("numerador") is not None and r.get("denominador"):
                situacao = "coletado"
                fonte = "última gravação no ARARAS"
                num = r.get("numerador")
                den = r.get("denominador")
            else:
                situacao = "aguardando_fonte"
                fonte = "sem leitura automática nesta rodada"
                num = None
                den = r.get("denominador")
        elif r.get("numerador") is not None and r.get("denominador"):
            situacao = str(r.get("situacao_validacao") or "informado")
            fonte = "informado pela área"
            num = r.get("numerador")
            den = r.get("denominador")
        else:
            situacao = "nao_informado"
            fonte = "área ainda não informou"
            num = None
            den = r.get("denominador")
        leitura = f"{int(num)}/{int(den)}" if num is not None and den else "—"
        sug = None
        if situacao in {"nao_informado", "aguardando_fonte"}:
            sug = sugerir_indicador(iid)
            if sug and not nota:
                nota = str(sug.get("nota") or "")
        out.append(
            {
                "id": iid,
                "nome": r.get("nome") or "",
                "area_id": r.get("area_id") or "",
                "area": rotulo_area(str(r.get("area_id") or "")),
                "modo": modo,
                "situacao": situacao,
                "leitura": leitura,
                "percentual": r.get("percentual") if num is not None else None,
                "semaforo": r.get("rotulo") or "",
                "entra_no_indice": bool(r.get("entra_no_indice")),
                "bloco_pendente": BLOCO_AGUARDANDO.get(iid, ""),
                "fonte": fonte,
                "nota": nota,
                "sugestao": (
                    f"{sug['numerador'] if sug.get('numerador') is not None else '—'}"
                    f"/{sug['denominador']}"
                    if sug and sug.get("denominador")
                    else ""
                ),
                "editavel": bool(r.get("editavel")),
                "situacao_validacao": r.get("situacao_validacao"),
                "numerador": num,
                "denominador": den,
                "classe_emergencia": r.get("classe_emergencia") or "",
                "perfil_escalonamento": r.get("perfil_escalonamento") or "",
                "perfil_s": r.get("perfil_s") or "",
                "papel_operacional": r.get("papel_operacional") or "",
                "padrao_completude": r.get("padrao_completude") or "",
                "gate_prontidao": bool(r.get("gate_prontidao")),
                "id_canonico": r.get("id_canonico") or "",
                "subindicadores": list(r.get("subindicadores") or []),
            }
        )
    from sisclima.plano.completude import enriquecer_completude

    return enriquecer_completude(enriquecer_linhas(out))


def csv_painel_indicadores(linhas: list[dict[str, Any]]) -> str:
    import csv
    import io

    buf = io.StringIO()
    campos = [
        "id",
        "nome",
        "area",
        "modo",
        "situacao",
        "leitura",
        "percentual",
        "semaforo",
        "entra_no_indice",
        "bloco_pendente",
        "fonte",
        "nota",
        "sugestao",
        "onda",
        "impacto",
        "classe_emergencia",
        "perfil_escalonamento",
        "perfil_s",
        "papel_operacional",
        "padrao_completude",
        "gate_prontidao",
        "id_canonico",
        "completude",
        "status_completude",
    ]
    writer = csv.DictWriter(buf, fieldnames=campos, extrasaction="ignore")
    writer.writeheader()
    for row in linhas:
        writer.writerow({k: row.get(k) if row.get(k) is not None else "" for k in campos})
    return buf.getvalue()


def resumo_painel_indicadores(linhas: list[dict[str, Any]]) -> dict[str, Any]:
    autos = [r for r in linhas if r.get("modo") == "automatico"]
    coletados = [r for r in autos if r.get("situacao") == "coletado"]
    aguardando = [r for r in autos if r.get("situacao") == "aguardando_fonte"]
    return {
        "n": len(linhas),
        "n_automaticos": len(autos),
        "n_coletados": len(coletados),
        "n_aguardando": len(aguardando),
        "n_nao_informado": sum(1 for r in linhas if r.get("situacao") == "nao_informado"),
    }





