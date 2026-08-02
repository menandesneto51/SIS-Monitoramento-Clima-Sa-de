# -*- coding: utf-8 -*-
"""Agente de configuração do WhatsApp gratuito.

Lê o ambiente, diz exatamente o que falta para o canal de WhatsApp funcionar,
gera o trecho de ``.env`` (ou ``secrets.toml``) correspondente e faz o envio de
teste. É usado tanto pela página ``pages/13_Configurar_WhatsApp.py`` quanto pela
linha de comando:

    python -m sisclima.alerts.whatsapp_agent listar
    python -m sisclima.alerts.whatsapp_agent recomendar --tem-servidor --uso interno
    python -m sisclima.alerts.whatsapp_agent plano --provedor meta_cloud
    python -m sisclima.alerts.whatsapp_agent diagnostico
    python -m sisclima.alerts.whatsapp_agent env --provedor evolution
    python -m sisclima.alerts.whatsapp_agent testar --para 65999998888
    python -m sisclima.alerts.whatsapp_agent descobrir --token EAA...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field

from sisclima.alerts import whatsapp
from sisclima.alerts import meta_discover
from sisclima.core.config import env, env_name_used

SEGREDOS = ('TOKEN', 'KEY', 'APIKEY', 'SENHA', 'PASSWORD', 'SECRET')


@dataclass(frozen=True)
class Passo:
    """Uma etapa concreta da configuração, com as variáveis que ela produz."""

    ordem: int
    titulo: str
    detalhe: str
    variaveis: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProvedorInfo:
    nome: str
    rotulo: str
    tipo: str
    custo: str
    indicado_para: str
    limitacoes: tuple[str, ...]
    documentacao: str
    passos: tuple[Passo, ...]

    @property
    def variaveis_obrigatorias(self) -> tuple[str, ...]:
        return whatsapp.VARIAVEIS_OBRIGATORIAS.get(self.nome, ())

    @property
    def variaveis_opcionais(self) -> tuple[str, ...]:
        return whatsapp.VARIAVEIS_OPCIONAIS.get(self.nome, ())

    def para_dict(self) -> dict:
        dados = asdict(self)
        dados['variaveis_obrigatorias'] = list(self.variaveis_obrigatorias)
        dados['variaveis_opcionais'] = list(self.variaveis_opcionais)
        dados['configurado'] = whatsapp.provedor_configurado(self.nome)
        return dados


CATALOGO: dict[str, ProvedorInfo] = {
    'meta_cloud': ProvedorInfo(
        nome='meta_cloud',
        rotulo='WhatsApp Cloud API (Meta, oficial)',
        tipo='oficial',
        custo='Sem mensalidade. Número de teste gratuito; mensagens de serviço e templates '
              'utilitários dentro da janela de 24h não são cobrados. Templates enviados fora '
              'dessa janela são cobrados por mensagem.',
        indicado_para='Uso institucional com número oficial da SES/secretaria, sem servidor próprio.',
        limitacoes=(
            'O número de teste só envia para até 5 destinatários previamente cadastrados.',
            'Envio proativo (fora da janela de 24h) exige template aprovado pela Meta.',
            'Número de produção exige verificação do negócio no Meta Business.',
        ),
        documentacao='https://developers.facebook.com/docs/whatsapp/cloud-api/get-started',
        passos=(
            Passo(1, 'Criar app no Meta for Developers',
                  'Acesse developers.facebook.com, crie um app do tipo "Negócios" e adicione o produto WhatsApp.'),
            Passo(2, 'Pegar o número de teste e o Phone Number ID',
                  'Na aba "API Setup" do produto WhatsApp, copie o "Phone number ID" do número de teste gratuito.',
                  ('WHATSAPP_PHONE_NUMBER_ID',)),
            Passo(3, 'Gerar o token de acesso',
                  'Use o token temporário (24h) para testar e, na sequência, gere um token permanente de usuário '
                  'do sistema em Configurações do Negócio > Usuários do sistema.',
                  ('WHATSAPP_TOKEN',)),
            Passo(4, 'Cadastrar os destinatários de teste',
                  'Ainda em "API Setup", adicione em "To" os celulares que receberão os alertas e confirme o código '
                  'enviado a cada um. Sem isso o número de teste não entrega nada.',
                  ('WHATSAPP_TO',)),
            Passo(5, 'Criar o template de alerta (envio proativo)',
                  'Em WhatsApp Manager > Modelos de mensagem, crie um template da categoria "Utilidade" com um '
                  'parâmetro {{1}} no corpo. Sem template, só é possível responder dentro da janela de 24h.',
                  ('WHATSAPP_TEMPLATE_NAME', 'WHATSAPP_TEMPLATE_LANG')),
        ),
    ),
    'evolution': ProvedorInfo(
        nome='evolution',
        rotulo='Evolution API v2 (auto-hospedada)',
        tipo='nao_oficial',
        custo='Software open source, sem licença. Custo apenas do servidor onde roda (ou zero, se rodar '
              'em máquina que a secretaria já mantém).',
        indicado_para='Quem já tem servidor/Docker e quer usar um número comum, sem cobrança por mensagem.',
        limitacoes=(
            'Não é API oficial: conecta como WhatsApp Web e o número pode ser bloqueado pela Meta.',
            'A sessão cai quando o celular fica muito tempo offline; exige releitura do QR Code.',
            'Requer manter um serviço no ar (Docker) e proteger a porta da API.',
        ),
        documentacao='https://doc.evolution-api.com/v2/pt/get-started/introduction',
        passos=(
            Passo(1, 'Subir a Evolution API',
                  'Rode a imagem oficial via Docker (evoapicloud/evolution-api) definindo uma AUTHENTICATION_API_KEY forte.'),
            Passo(2, 'Anotar a URL pública e a chave',
                  'A URL precisa ser alcançável pela máquina que roda o pipeline (ex.: https://whats.saude.mt.gov.br).',
                  ('EVOLUTION_API_URL', 'EVOLUTION_API_KEY')),
            Passo(3, 'Criar a instância',
                  'POST /instance/create com o nome da instância. Use o nome, não o UUID, nas chamadas seguintes.',
                  ('EVOLUTION_INSTANCE',)),
            Passo(4, 'Conectar o número lendo o QR Code',
                  'GET /instance/connect/{instancia} devolve o QR. Leia no celular e confirme que o state ficou "open".'),
            Passo(5, 'Cadastrar os destinatários',
                  'Informe os celulares que receberão o alerta, com DDD (o DDI 55 é adicionado automaticamente).',
                  ('WHATSAPP_TO',)),
        ),
    ),
    'callmebot': ProvedorInfo(
        nome='callmebot',
        rotulo='CallMeBot (gratuito, uso pessoal)',
        tipo='nao_oficial',
        custo='Totalmente gratuito, sem cadastro e sem servidor.',
        indicado_para='Plantão e testes, quando já existe uma chave ativa do robô.',
        limitacoes=(
            'O cadastro fecha quando o robô lota. Nesse período o site esconde o número e não há como '
            'obter chave nova — só esperar ou usar outro provedor.',
            'Cada destinatário precisa autorizar o robô individualmente e recebe uma chave própria.',
            'Serviço de terceiro, sem SLA e com limite de frequência de envio.',
            'Não use para comunicação oficial com a população.',
        ),
        documentacao='https://www.callmebot.com/blog/free-api-whatsapp-messages/',
        passos=(
            Passo(1, 'Verificar se o robô aceita cadastro',
                  'Em callmebot.com/blog/free-api-whatsapp-messages, o número aparece apenas quando há vagas. '
                  'Se estiver mascarado ou o robô responder "This Bot is full", não há alternativa: use outro '
                  'provedor. O número também muda de tempos em tempos, então sempre consulte o site.'),
            Passo(2, 'Autorizar o robô',
                  'Desse celular, envie no WhatsApp a frase exata "I allow callmebot to send me messages" '
                  'para o contato criado.'),
            Passo(3, 'Guardar a chave devolvida',
                  'O robô responde "API Activated for your phone number. Your APIKEY is ...". A chave é '
                  'individual: cada destinatário precisa autorizar e tem a sua.',
                  ('CALLMEBOT_APIKEY', 'CALLMEBOT_PHONE')),
        ),
    ),
    'webhook': ProvedorInfo(
        nome='webhook',
        rotulo='Ponte por webhook (n8n, Make, Zapier, Apps Script)',
        tipo='ponte',
        custo='Depende da ferramenta: n8n auto-hospedado é gratuito; Make e Zapier têm plano free limitado.',
        indicado_para='Quem já tem automação montada e só quer que o VIGIA dispare o gatilho.',
        limitacoes=(
            'O envio de fato acontece fora do SIS; o status retornado é só o do webhook.',
            'Planos gratuitos de SaaS limitam execuções por mês.',
        ),
        documentacao='https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/',
        passos=(
            Passo(1, 'Criar o fluxo com gatilho de webhook',
                  'No n8n/Make/Zapier, crie um fluxo que comece com um webhook POST e termine no envio do WhatsApp.'),
            Passo(2, 'Copiar a URL do webhook',
                  'O SIS envia JSON com as chaves canal, para, mensagem e os dados do alerta.',
                  ('WHATSAPP_WEBHOOK_URL',)),
            Passo(3, 'Proteger a URL (recomendado)',
                  'Configure um token no fluxo; o SIS o envia no cabeçalho Authorization: Bearer.',
                  ('WHATSAPP_WEBHOOK_TOKEN',)),
        ),
    ),
}


@dataclass
class Diagnostico:
    """Retrato do estado atual da configuração do canal."""

    provedor: str | None
    pronto: bool
    canal_habilitado: bool
    problemas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    variaveis: dict[str, str] = field(default_factory=dict)
    passos_pendentes: list[Passo] = field(default_factory=list)
    destinatarios: list[str] = field(default_factory=list)
    provedores_configurados: list[str] = field(default_factory=list)

    def para_dict(self) -> dict:
        return asdict(self)


def mascarar(valor: str | None, visivel: int = 4) -> str:
    """Esconde o miolo de um segredo, preservando o suficiente para conferência."""
    if not valor:
        return ''
    texto = str(valor)
    if len(texto) <= visivel * 2:
        return '*' * len(texto)
    return f'{texto[:visivel]}{"*" * 6}{texto[-visivel:]}'


def _e_segredo(nome: str) -> bool:
    return any(marca in nome.upper() for marca in SEGREDOS)


def _valor_exibivel(nome: str) -> str:
    valor = env(nome)
    if not valor:
        return ''
    return mascarar(valor) if _e_segredo(nome) else valor


def listar_provedores() -> list[ProvedorInfo]:
    return [CATALOGO[nome] for nome in whatsapp.ORDEM_AUTO if nome in CATALOGO]


def recomendar(tem_servidor: bool = False, uso: str = 'institucional', volume_alto: bool = False) -> tuple[str, str]:
    """Sugere um provedor e explica o porquê.

    ``uso`` aceita ``institucional`` (comunicação oficial), ``interno`` (equipe técnica)
    ou ``automacao`` (já existe fluxo n8n/Make montado).
    """
    uso = (uso or 'institucional').strip().lower()
    if uso == 'automacao':
        return 'webhook', ('Você já tem uma automação montada: o VIGIA só precisa disparar o gatilho e a '
                           'ferramenta existente cuida do envio.')
    if volume_alto and tem_servidor:
        return 'evolution', ('Com servidor próprio e volume alto, a Evolution API evita a cobrança por template '
                             'fora da janela de 24h. Aceite o risco de ser um caminho não oficial.')
    if uso == 'interno':
        # O CallMeBot seria mais simples, mas o cadastro dele passa longos períodos fechado.
        return 'meta_cloud', ('Mesmo para avisar só a equipe técnica, a Cloud API da Meta é o caminho confiável: '
                              'o número de teste é gratuito e atende até 5 celulares. O CallMeBot seria mais '
                              'simples, mas só serve se você já tiver uma chave: quando o robô lota, ele para de '
                              'aceitar cadastro por tempo indeterminado.')
    return 'meta_cloud', ('Para comunicação oficial, a Cloud API da Meta é o caminho suportado: número de teste '
                          'gratuito para começar e sem custo em mensagens de serviço dentro da janela de 24h.')


def plano_de_configuracao(provedor: str) -> list[Passo]:
    info = CATALOGO.get(provedor)
    return list(info.passos) if info else []


def passos_pendentes(provedor: str) -> list[Passo]:
    """Passos cujas variáveis ainda não estão no ambiente.

    Passos sem variáveis associadas (ações manuais, como ler o QR Code) só aparecem
    enquanto o provedor não está completo.
    """
    faltantes = set(whatsapp.variaveis_faltantes(provedor))
    completo = not faltantes
    pendentes: list[Passo] = []
    for passo in plano_de_configuracao(provedor):
        if not passo.variaveis:
            if not completo:
                pendentes.append(passo)
            continue
        if any(nome in faltantes for nome in passo.variaveis):
            pendentes.append(passo)
    return pendentes


def diagnosticar(provedor: str | None = None) -> Diagnostico:
    """Estado atual do canal: o que já está pronto, o que falta e o que merece atenção."""
    configurados = whatsapp.provedores_configurados()
    escolhido = (provedor or whatsapp.provedor_ativo() or '').strip().lower() or None

    problemas: list[str] = []
    avisos: list[str] = []

    if escolhido is None:
        problemas.append(
            'Nenhum provedor de WhatsApp configurado. Escolha um provedor e preencha as variáveis indicadas.'
        )
        return Diagnostico(
            provedor=None,
            pronto=False,
            canal_habilitado=False,
            problemas=problemas,
            avisos=avisos,
            provedores_configurados=configurados,
        )

    if escolhido not in CATALOGO:
        problemas.append(f'Provedor "{escolhido}" desconhecido. Use um de: {", ".join(whatsapp.PROVEDORES)}.')
        return Diagnostico(
            provedor=escolhido,
            pronto=False,
            canal_habilitado=False,
            problemas=problemas,
            avisos=avisos,
            provedores_configurados=configurados,
        )

    info = CATALOGO[escolhido]
    faltantes = whatsapp.variaveis_faltantes(escolhido)
    for nome in faltantes:
        problemas.append(f'Variável obrigatória ausente: {nome}.')

    variaveis: dict[str, str] = {}
    for nome in list(info.variaveis_obrigatorias) + list(info.variaveis_opcionais):
        variaveis[nome] = _valor_exibivel(nome)

    numeros = whatsapp.destinatarios(
        env('CALLMEBOT_PHONE') if escolhido == 'callmebot' else None
    )
    if escolhido != 'webhook' and env('WHATSAPP_TO') and not numeros:
        problemas.append('WHATSAPP_TO está preenchido mas nenhum número válido foi reconhecido.')

    if escolhido == 'meta_cloud' and not env('WHATSAPP_TEMPLATE_NAME'):
        avisos.append(
            'Sem WHATSAPP_TEMPLATE_NAME o envio usa mensagem de texto livre, que a Meta só aceita dentro da '
            'janela de 24h após o cidadão escrever. Para alerta proativo, cadastre um template utilitário.'
        )
    if escolhido == 'evolution' and (env('EVOLUTION_API_URL') or '').startswith('http://'):
        avisos.append('EVOLUTION_API_URL está em HTTP: a chave da API trafega sem criptografia. Prefira HTTPS.')
    if escolhido == 'callmebot':
        avisos.append('CallMeBot é serviço de terceiro sem SLA. Use apenas para avisos internos e testes.')
        ignorados = [numero for numero in whatsapp.destinatarios(env('WHATSAPP_TO')) if numero not in numeros]
        if ignorados or len(numeros) > 1:
            avisos.append(
                'A chave do CallMeBot vale para um único celular, o de CALLMEBOT_PHONE. Os demais números '
                f'({", ".join(ignorados) or "os excedentes"}) não vão receber. Para uma lista, use outro provedor.'
            )
    if escolhido == 'webhook' and not env('WHATSAPP_WEBHOOK_TOKEN'):
        avisos.append('Webhook sem WHATSAPP_WEBHOOK_TOKEN: qualquer um que descobrir a URL dispara mensagens.')

    if env_name_used('ALERT_WHATSAPP_ENABLED') and not whatsapp.whatsapp_habilitado():
        avisos.append('ALERT_WHATSAPP_ENABLED está desligado: o canal não será usado mesmo configurado.')

    return Diagnostico(
        provedor=escolhido,
        pronto=not problemas,
        canal_habilitado=whatsapp.whatsapp_habilitado(),
        problemas=problemas,
        avisos=avisos,
        variaveis=variaveis,
        passos_pendentes=passos_pendentes(escolhido),
        destinatarios=numeros,
        provedores_configurados=configurados,
    )


def _linhas_env(provedor: str, valores: dict[str, str] | None = None, incluir_vazias: bool = True) -> list[tuple[str, str]]:
    valores = valores or {}
    info = CATALOGO[provedor]
    linhas: list[tuple[str, str]] = [
        ('ALERT_WHATSAPP_ENABLED', 'true'),
        ('WHATSAPP_PROVIDER', provedor),
    ]
    for nome in list(info.variaveis_obrigatorias) + list(info.variaveis_opcionais):
        valor = valores.get(nome) or env(nome) or ''
        if not valor and not incluir_vazias:
            continue
        linhas.append((nome, valor))
    return linhas


def gerar_env(provedor: str, valores: dict[str, str] | None = None) -> str:
    """Bloco pronto para colar no ``.env`` da máquina que roda o pipeline."""
    if provedor not in CATALOGO:
        raise ValueError(f'Provedor desconhecido: {provedor}')
    info = CATALOGO[provedor]
    linhas = [f'# WhatsApp — {info.rotulo}', f'# Documentação: {info.documentacao}']
    for nome, valor in _linhas_env(provedor, valores):
        linhas.append(f'{nome}={valor}')
    return '\n'.join(linhas) + '\n'


def gerar_secrets_toml(provedor: str, valores: dict[str, str] | None = None) -> str:
    """Mesma configuração no formato ``.streamlit/secrets.toml`` (Streamlit Cloud)."""
    if provedor not in CATALOGO:
        raise ValueError(f'Provedor desconhecido: {provedor}')
    info = CATALOGO[provedor]
    linhas = [f'# WhatsApp — {info.rotulo}']
    for nome, valor in _linhas_env(provedor, valores):
        escapado = str(valor).replace('\\', '\\\\').replace('"', '\\"')
        linhas.append(f'{nome} = "{escapado}"')
    return '\n'.join(linhas) + '\n'


def aplicar_na_sessao(valores: dict[str, str]) -> list[str]:
    """Coloca os valores em ``os.environ`` para permitir diagnóstico e teste imediatos.

    Nada é gravado em disco: ao encerrar o processo, a configuração se perde.
    """
    aplicadas: list[str] = []
    for nome, valor in (valores or {}).items():
        texto = str(valor or '').strip()
        if texto:
            os.environ[nome] = texto
            aplicadas.append(nome)
        elif nome in os.environ:
            del os.environ[nome]
    return aplicadas


def mensagem_de_teste() -> str:
    return (
        '[SIS Clima-Saúde MT / VIGIA] Teste de configuração do canal WhatsApp. '
        'Se você recebeu esta mensagem, os alertas de mudança de nível já podem ser enviados por aqui.'
    )


def testar(provedor: str | None = None, destinos: str | list[str] | None = None, mensagem: str | None = None) -> list[whatsapp.ResultadoEnvio]:
    """Envia uma mensagem de teste pelo provedor indicado."""
    return whatsapp.enviar_whatsapp(mensagem or mensagem_de_teste(), destinos=destinos, provedor=provedor)


def resumo_texto(diag: Diagnostico) -> str:
    """Diagnóstico em texto simples, usado pela CLI."""
    linhas: list[str] = []
    if diag.provedor:
        info = CATALOGO.get(diag.provedor)
        linhas.append(f'Provedor: {info.rotulo if info else diag.provedor}')
    else:
        linhas.append('Provedor: nenhum configurado')
    linhas.append(f'Pronto para enviar: {"sim" if diag.pronto else "não"}')
    linhas.append(f'Canal habilitado: {"sim" if diag.canal_habilitado else "não"}')
    if diag.destinatarios:
        linhas.append(f'Destinatários: {", ".join(diag.destinatarios)}')
    if diag.variaveis:
        linhas.append('Variáveis:')
        for nome, valor in diag.variaveis.items():
            linhas.append(f'  - {nome}: {valor or "(vazio)"}')
    if diag.problemas:
        linhas.append('Problemas:')
        linhas.extend(f'  - {item}' for item in diag.problemas)
    if diag.avisos:
        linhas.append('Avisos:')
        linhas.extend(f'  - {item}' for item in diag.avisos)
    if diag.passos_pendentes:
        linhas.append('Próximos passos:')
        for passo in diag.passos_pendentes:
            variaveis = f' [{", ".join(passo.variaveis)}]' if passo.variaveis else ''
            linhas.append(f'  {passo.ordem}. {passo.titulo}{variaveis}')
            linhas.append(f'     {passo.detalhe}')
    return '\n'.join(linhas)


def _cmd_listar(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps([info.para_dict() for info in listar_provedores()], ensure_ascii=False, indent=2))
        return 0
    for info in listar_provedores():
        marca = 'configurado' if whatsapp.provedor_configurado(info.nome) else 'pendente'
        print(f'\n{info.nome} — {info.rotulo}  [{marca}]')
        print(f'  Tipo: {info.tipo}')
        print(f'  Custo: {info.custo}')
        print(f'  Indicado para: {info.indicado_para}')
        print(f'  Obrigatórias: {", ".join(info.variaveis_obrigatorias) or "—"}')
        print(f'  Documentação: {info.documentacao}')
    return 0


def _cmd_recomendar(args: argparse.Namespace) -> int:
    provedor, motivo = recomendar(tem_servidor=args.tem_servidor, uso=args.uso, volume_alto=args.volume_alto)
    if args.json:
        print(json.dumps({'provedor': provedor, 'motivo': motivo}, ensure_ascii=False, indent=2))
    else:
        print(f'Provedor recomendado: {provedor} ({CATALOGO[provedor].rotulo})\n{motivo}')
    return 0


def _cmd_plano(args: argparse.Namespace) -> int:
    if args.provedor not in CATALOGO:
        print(f'Provedor desconhecido: {args.provedor}', file=sys.stderr)
        return 2
    info = CATALOGO[args.provedor]
    if args.json:
        print(json.dumps([asdict(passo) for passo in info.passos], ensure_ascii=False, indent=2))
        return 0
    print(f'{info.rotulo}\n{info.documentacao}\n')
    for passo in info.passos:
        variaveis = f' [{", ".join(passo.variaveis)}]' if passo.variaveis else ''
        print(f'{passo.ordem}. {passo.titulo}{variaveis}\n   {passo.detalhe}')
    if info.limitacoes:
        print('\nLimitações:')
        for item in info.limitacoes:
            print(f'  - {item}')
    return 0


def _cmd_diagnostico(args: argparse.Namespace) -> int:
    diag = diagnosticar(args.provedor)
    if args.json:
        print(json.dumps(diag.para_dict(), ensure_ascii=False, indent=2))
    else:
        print(resumo_texto(diag))
    return 0 if diag.pronto else 1


def _cmd_env(args: argparse.Namespace) -> int:
    if args.provedor not in CATALOGO:
        print(f'Provedor desconhecido: {args.provedor}', file=sys.stderr)
        return 2
    valores: dict[str, str] = {}
    for item in args.valor or []:
        if '=' not in item:
            print(f'Use o formato CHAVE=valor (recebido: {item})', file=sys.stderr)
            return 2
        chave, _, valor = item.partition('=')
        valores[chave.strip()] = valor.strip()
    print(gerar_secrets_toml(args.provedor, valores) if args.formato == 'toml' else gerar_env(args.provedor, valores))
    return 0


def _cmd_testar(args: argparse.Namespace) -> int:
    resultados = testar(args.provedor, args.para, args.mensagem)
    if args.json:
        print(json.dumps([asdict(r) for r in resultados], ensure_ascii=False, indent=2, default=str))
    else:
        for resultado in resultados:
            marca = 'OK ' if resultado.ok else 'ERRO'
            print(f'[{marca}] {resultado.provedor} -> {resultado.destino or "(sem destino)"}: {resultado.detalhe}')
    return 0 if any(r.ok for r in resultados) else 1


def _cmd_descobrir(args: argparse.Namespace) -> int:
    token = (args.token or env('WHATSAPP_TOKEN') or '').strip()
    if not token:
        print('Informe --token EAA... ou defina WHATSAPP_TOKEN no ambiente.', file=sys.stderr)
        print('Gere o token em: https://developers.facebook.com/tools/explorer', file=sys.stderr)
        print('Guia visual: docs/META_ONDE_CLICAR.md', file=sys.stderr)
        return 2

    resultado = meta_discover.descobrir(token)
    if args.json:
        payload = {
            'ok': resultado.ok,
            'token_valido': resultado.token_valido,
            'numeros': [asdict(n) for n in resultado.numeros],
            'waba_ids': resultado.waba_ids,
            'avisos': resultado.avisos,
            'erros': resultado.erros,
            'phone_number_id_sugerido': resultado.phone_number_id_sugerido,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(meta_discover.resumo_texto(resultado))
        if resultado.phone_number_id_sugerido:
            valores = {
                'WHATSAPP_PHONE_NUMBER_ID': resultado.phone_number_id_sugerido,
                'WHATSAPP_TOKEN': token,
                'WHATSAPP_TO': '65992190039',
            }
            print('\n--- Bloco .env sugerido ---')
            print(gerar_env('meta_cloud', valores))

    return 0 if resultado.ok else 1


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='python -m sisclima.alerts.whatsapp_agent',
        description='Agente de configuração do canal de WhatsApp gratuito do SIS Clima-Saúde MT.',
    )
    parser.add_argument('--json', action='store_true', help='Saída em JSON.')
    sub = parser.add_subparsers(dest='comando', required=True)

    sub.add_parser('listar', help='Compara os provedores gratuitos disponíveis.').set_defaults(func=_cmd_listar)

    p_rec = sub.add_parser('recomendar', help='Sugere o provedor conforme o cenário.')
    p_rec.add_argument('--tem-servidor', action='store_true', help='Existe servidor próprio/Docker disponível.')
    p_rec.add_argument('--uso', default='institucional', choices=['institucional', 'interno', 'automacao'])
    p_rec.add_argument('--volume-alto', action='store_true', help='Muitos envios proativos por mês.')
    p_rec.set_defaults(func=_cmd_recomendar)

    p_plano = sub.add_parser('plano', help='Mostra o passo a passo de um provedor.')
    p_plano.add_argument('--provedor', required=True, choices=list(CATALOGO))
    p_plano.set_defaults(func=_cmd_plano)

    p_diag = sub.add_parser('diagnostico', help='Verifica o que falta no ambiente atual.')
    p_diag.add_argument('--provedor', choices=list(CATALOGO), help='Força o provedor avaliado.')
    p_diag.set_defaults(func=_cmd_diagnostico)

    p_env = sub.add_parser('env', help='Gera o bloco de configuração para .env ou secrets.toml.')
    p_env.add_argument('--provedor', required=True, choices=list(CATALOGO))
    p_env.add_argument('--formato', default='env', choices=['env', 'toml'])
    p_env.add_argument('--valor', action='append', metavar='CHAVE=VALOR', help='Preenche uma variável no bloco gerado.')
    p_env.set_defaults(func=_cmd_env)

    p_teste = sub.add_parser('testar', help='Envia uma mensagem de teste.')
    p_teste.add_argument('--provedor', choices=list(CATALOGO))
    p_teste.add_argument('--para', help='Destinatários separados por vírgula. Padrão: WHATSAPP_TO.')
    p_teste.add_argument('--mensagem', help='Texto alternativo para o teste.')
    p_teste.set_defaults(func=_cmd_testar)

    p_desc = sub.add_parser(
        'descobrir',
        help='Lista Phone number IDs via Graph API (quando API Setup não aparece).',
    )
    p_desc.add_argument('--token', help='Token EAA... do Explorador da Graph API ou WHATSAPP_TOKEN.')
    p_desc.set_defaults(func=_cmd_descobrir)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == '__main__':
    raise SystemExit(main())
