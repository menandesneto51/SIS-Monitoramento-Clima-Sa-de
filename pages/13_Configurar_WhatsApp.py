# -*- coding: utf-8 -*-
"""Assistente de configuração do canal de WhatsApp gratuito do VIGIA."""
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

st.set_page_config(page_title="Configurar WhatsApp", page_icon="🟢", layout="wide")

try:
    from sisclima.alerts import whatsapp, whatsapp_agent
except Exception as exc:  # noqa: BLE001 - a página não pode derrubar o painel inteiro
    st.title("🟢 Configurar WhatsApp")
    st.error(f"Não foi possível carregar o agente de WhatsApp: {exc}")
    st.stop()

# No Streamlit Cloud as credenciais chegam por st.secrets; o restante do SIS lê os.environ.
try:
    for _chave, _valor in dict(st.secrets).items():
        if isinstance(_valor, str) and _chave not in os.environ:
            os.environ[_chave] = _valor
except Exception:  # noqa: BLE001 - ausência de secrets.toml é o caso normal em execução local
    pass

ROTULOS = {
    "WHATSAPP_TO": ("Destinatários", "Celulares com DDD, separados por vírgula. O DDI 55 é adicionado automaticamente."),
    "WHATSAPP_DDI_PADRAO": ("DDI padrão", "Use 55 para o Brasil."),
    "WHATSAPP_PHONE_NUMBER_ID": ("Phone Number ID", "Identificador do número na aba API Setup do app Meta."),
    "WHATSAPP_TOKEN": ("Token de acesso", "Token temporário (24h) para testar ou permanente de usuário do sistema."),
    "WHATSAPP_API_VERSION": ("Versão da Graph API", f"Padrão: {whatsapp.VERSAO_API_META_PADRAO}."),
    "WHATSAPP_TEMPLATE_NAME": ("Nome do template", "Necessário para alerta proativo fora da janela de 24h."),
    "WHATSAPP_TEMPLATE_LANG": ("Idioma do template", "Ex.: pt_BR."),
    "EVOLUTION_API_URL": ("URL da Evolution API", "Ex.: https://whats.suainstituicao.gov.br"),
    "EVOLUTION_API_KEY": ("Chave da API", "AUTHENTICATION_API_KEY definida ao subir o contêiner."),
    "EVOLUTION_INSTANCE": ("Nome da instância", "Use o nome da instância, não o UUID."),
    "CALLMEBOT_APIKEY": ("Chave do CallMeBot", "Chave devolvida pelo robô ao número autorizado."),
    "CALLMEBOT_PHONE": ("Celular autorizado", "Número que enviou a autorização ao robô."),
    "WHATSAPP_WEBHOOK_URL": ("URL do webhook", "Endpoint que recebe o JSON do alerta (n8n, Make, Zapier...)."),
    "WHATSAPP_WEBHOOK_TOKEN": ("Token do webhook", "Enviado no cabeçalho Authorization: Bearer."),
}

st.title("🟢 Configurar WhatsApp — agente de configuração")
st.caption(
    "Escolha um provedor gratuito, siga o passo a passo, teste o envio e leve a configuração "
    "pronta para o .env do pipeline."
)
st.info(
    "Nada digitado aqui é gravado em disco. Os valores valem só para esta sessão, para permitir o teste. "
    "Para valer em produção, copie o bloco gerado no fim da página.",
    icon="🔒",
)


def rotulo(nome: str) -> tuple[str, str]:
    return ROTULOS.get(nome, (nome, ""))


def e_segredo(nome: str) -> bool:
    return any(marca in nome.upper() for marca in whatsapp_agent.SEGREDOS)


st.subheader("1. Escolher o provedor")

with st.expander("Não sei qual escolher — me ajude a decidir"):
    col_a, col_b, col_c = st.columns(3)
    uso = col_a.selectbox(
        "Para quem é o alerta?",
        options=["institucional", "interno", "automacao"],
        format_func=lambda v: {
            "institucional": "Comunicação oficial (gestores, população)",
            "interno": "Equipe técnica / plantão",
            "automacao": "Já tenho fluxo n8n, Make ou Zapier",
        }[v],
    )
    tem_servidor = col_b.checkbox("Temos servidor próprio ou Docker disponível")
    volume_alto = col_c.checkbox("Muitos envios proativos por mês")
    sugerido, motivo = whatsapp_agent.recomendar(tem_servidor=tem_servidor, uso=uso, volume_alto=volume_alto)
    st.success(f"**Recomendado: {whatsapp_agent.CATALOGO[sugerido].rotulo}**\n\n{motivo}")

provedores = whatsapp_agent.listar_provedores()
padrao = whatsapp.provedor_ativo() or provedores[0].nome
nomes = [info.nome for info in provedores]

escolhido = st.radio(
    "Provedor",
    options=nomes,
    index=nomes.index(padrao) if padrao in nomes else 0,
    format_func=lambda nome: (
        f"{whatsapp_agent.CATALOGO[nome].rotulo}"
        f"{'  ✅ configurado' if whatsapp.provedor_configurado(nome) else ''}"
    ),
    horizontal=False,
)
info = whatsapp_agent.CATALOGO[escolhido]

st.dataframe(
    pd.DataFrame(
        [
            {
                "Provedor": p.rotulo,
                "Tipo": {"oficial": "Oficial", "nao_oficial": "Não oficial", "ponte": "Ponte"}[p.tipo],
                "Custo": p.custo,
                "Indicado para": p.indicado_para,
                "Configurado": "Sim" if whatsapp.provedor_configurado(p.nome) else "Não",
            }
            for p in provedores
        ]
    ),
    width="stretch",
    hide_index=True,
)

with st.expander(f"Limitações de {info.rotulo}", expanded=info.tipo != "oficial"):
    for item in info.limitacoes:
        st.markdown(f"- {item}")
    st.markdown(f"[Documentação oficial]({info.documentacao})")

st.subheader("2. Passo a passo")

faltantes = set(whatsapp.variaveis_faltantes(escolhido))
for passo in info.passos:
    pendente = (not passo.variaveis and faltantes) or any(nome in faltantes for nome in passo.variaveis)
    marca = "⬜" if pendente else "✅"
    variaveis = f" — `{'`, `'.join(passo.variaveis)}`" if passo.variaveis else ""
    st.markdown(f"{marca} **{passo.ordem}. {passo.titulo}**{variaveis}  \n{passo.detalhe}")

st.subheader("3. Preencher as credenciais")

with st.form("credenciais_whatsapp"):
    valores: dict[str, str] = {}
    obrigatorias = list(info.variaveis_obrigatorias)
    opcionais = list(info.variaveis_opcionais)

    for nome in obrigatorias:
        titulo, ajuda = rotulo(nome)
        valores[nome] = st.text_input(
            f"{titulo} *",
            value=os.environ.get(nome, ""),
            help=f"{ajuda} (variável `{nome}`)",
            type="password" if e_segredo(nome) else "default",
        )

    if opcionais:
        with st.expander("Campos opcionais"):
            for nome in opcionais:
                titulo, ajuda = rotulo(nome)
                valores[nome] = st.text_input(
                    titulo,
                    value=os.environ.get(nome, ""),
                    help=f"{ajuda} (variável `{nome}`)",
                    type="password" if e_segredo(nome) else "default",
                )

    aplicar = st.form_submit_button("Aplicar nesta sessão e diagnosticar", type="primary")

if aplicar:
    whatsapp_agent.aplicar_na_sessao({"WHATSAPP_PROVIDER": escolhido, "ALERT_WHATSAPP_ENABLED": "true", **valores})
    st.session_state["whatsapp_valores"] = {k: v for k, v in valores.items() if v}
    st.rerun()

st.subheader("4. Diagnóstico")

diag = whatsapp_agent.diagnosticar(escolhido)
col1, col2, col3 = st.columns(3)
col1.metric("Pronto para enviar", "Sim" if diag.pronto else "Não")
col2.metric("Canal habilitado", "Sim" if diag.canal_habilitado else "Não")
col3.metric("Destinatários", len(diag.destinatarios))

for problema in diag.problemas:
    st.error(problema)
for aviso in diag.avisos:
    st.warning(aviso)
if diag.pronto and not diag.problemas:
    st.success("Todas as variáveis obrigatórias estão preenchidas.")

if diag.variaveis:
    st.dataframe(
        pd.DataFrame(
            [
                {"Variável": nome, "Valor": valor or "(vazio)", "Obrigatória": "Sim" if nome in obrigatorias else "Não"}
                for nome, valor in diag.variaveis.items()
            ]
        ),
        width="stretch",
        hide_index=True,
    )

col_verificar, col_testar = st.columns(2)

if col_verificar.button("Verificar credenciais (não envia mensagem)", disabled=not diag.pronto):
    resultado = whatsapp.verificar_conexao(escolhido)
    (st.success if resultado.ok else st.error)(resultado.detalhe or "Sem detalhe retornado.")

destino_teste = col_testar.text_input(
    "Enviar teste para (opcional)",
    value="",
    placeholder="65999998888 — em branco usa os destinatários configurados",
)
if col_testar.button("Enviar mensagem de teste", disabled=not diag.pronto):
    resultados = whatsapp_agent.testar(escolhido, destino_teste or None)
    for resultado in resultados:
        alvo = resultado.destino or "(sem destino)"
        (st.success if resultado.ok else st.error)(f"{alvo}: {resultado.detalhe}")

st.subheader("5. Levar para produção")

st.markdown(
    "O painel na nuvem serve para montar e testar a configuração. O envio automático dos alertas acontece "
    "no pipeline, então o bloco abaixo precisa ir para o ambiente que roda o `sisclima`."
)

valores_gerados = st.session_state.get("whatsapp_valores", {})
aba_env, aba_toml, aba_cli = st.tabs([".env (pipeline local)", "secrets.toml (Streamlit Cloud)", "Linha de comando"])

with aba_env:
    bloco_env = whatsapp_agent.gerar_env(escolhido, valores_gerados)
    st.code(bloco_env, language="bash")
    st.download_button("Baixar bloco .env", bloco_env, file_name="whatsapp.env", mime="text/plain")

with aba_toml:
    bloco_toml = whatsapp_agent.gerar_secrets_toml(escolhido, valores_gerados)
    st.code(bloco_toml, language="toml")
    st.download_button("Baixar secrets.toml", bloco_toml, file_name="secrets.toml", mime="text/plain")
    st.caption("Cole em Settings > Secrets do app no Streamlit Cloud. Nunca versione este arquivo.")

with aba_cli:
    st.code(
        "python -m sisclima.alerts.whatsapp_agent diagnostico\n"
        f"python -m sisclima.alerts.whatsapp_agent plano --provedor {escolhido}\n"
        "python -m sisclima.alerts.whatsapp_agent testar --para 65999998888",
        language="bash",
    )
    st.caption("Rode na máquina do pipeline para validar o mesmo canal fora do painel.")

st.caption(
    "Tutorial passo a passo (Meta Cloud API): `docs/TUTORIAL_WHATSAPP_META_CLOUD.md` · "
    "Referência geral: `docs/WHATSAPP_GRATUITO.md`"
)
