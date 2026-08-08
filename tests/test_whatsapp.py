# -*- coding: utf-8 -*-
"""Testes do canal de WhatsApp (nenhuma requisição real é feita)."""
from __future__ import annotations

import pytest
import requests

from sisclima.alerts import whatsapp
from tests.conftest import RespostaFalsa


@pytest.fixture
def meta_configurado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('WHATSAPP_PHONE_NUMBER_ID', '123456789')
    monkeypatch.setenv('WHATSAPP_TOKEN', 'token-secreto-de-teste')
    monkeypatch.setenv('WHATSAPP_TO', '65999998888')


@pytest.fixture
def evolution_configurado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('EVOLUTION_API_URL', 'https://whats.exemplo.gov.br/')
    monkeypatch.setenv('EVOLUTION_API_KEY', 'chave-evolution')
    monkeypatch.setenv('EVOLUTION_INSTANCE', 'vigia')
    monkeypatch.setenv('WHATSAPP_TO', '65999998888')


class ClienteFalso:
    """Registra as chamadas HTTP e devolve respostas pré-programadas."""

    def __init__(self, *respostas: RespostaFalsa):
        self.respostas = list(respostas) or [RespostaFalsa(200, {'ok': True})]
        self.chamadas: list[dict] = []

    def _responder(self, metodo: str, url: str, **kwargs) -> RespostaFalsa:
        self.chamadas.append({'metodo': metodo, 'url': url, **kwargs})
        indice = min(len(self.chamadas) - 1, len(self.respostas) - 1)
        return self.respostas[indice]

    def post(self, url: str, **kwargs) -> RespostaFalsa:
        return self._responder('POST', url, **kwargs)

    def get(self, url: str, **kwargs) -> RespostaFalsa:
        return self._responder('GET', url, **kwargs)


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch):
    def _instalar(*respostas: RespostaFalsa) -> ClienteFalso:
        falso = ClienteFalso(*respostas)
        monkeypatch.setattr(whatsapp.requests, 'post', falso.post)
        monkeypatch.setattr(whatsapp.requests, 'get', falso.get)
        return falso

    return _instalar


@pytest.mark.parametrize(
    'entrada, esperado',
    [
        ('(65) 99999-8888', '5565999998888'),
        ('65 3333-4444', '556533334444'),
        ('+55 65 99999-8888', '5565999998888'),
        ('5565999998888', '5565999998888'),
        ('', ''),
        ('sem numero', ''),
    ],
)
def test_normalizar_numero(entrada, esperado):
    assert whatsapp.normalizar_numero(entrada) == esperado


def test_destinatarios_aceita_separadores_e_remove_duplicados(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('WHATSAPP_TO', '65999998888, (65) 99999-8888; 6533334444')
    assert whatsapp.destinatarios() == ['5565999998888', '556533334444']


def test_provedor_ativo_em_auto_escolhe_o_configurado(evolution_configurado):
    assert whatsapp.provedor_ativo() == 'evolution'
    assert whatsapp.provedores_configurados() == ['evolution']


def test_provedor_ativo_prefere_meta_quando_ha_mais_de_um(meta_configurado, evolution_configurado):
    assert whatsapp.provedor_ativo() == 'meta_cloud'


def test_provedor_ativo_respeita_escolha_explicita(monkeypatch, meta_configurado, evolution_configurado):
    monkeypatch.setenv('WHATSAPP_PROVIDER', 'evolution')
    assert whatsapp.provedor_ativo() == 'evolution'


def test_provedor_desconhecido_nao_envia(monkeypatch, meta_configurado):
    monkeypatch.setenv('WHATSAPP_PROVIDER', 'inexistente')
    assert whatsapp.provedor_ativo() is None
    resultados = whatsapp.enviar_whatsapp('oi', provedor='inexistente')
    assert not any(r.ok for r in resultados)


def test_sem_provedor_configurado_nao_quebra():
    resultados = whatsapp.enviar_whatsapp('oi')
    assert len(resultados) == 1
    assert resultados[0].ok is False
    assert 'Nenhum provedor' in resultados[0].detalhe


def test_variaveis_faltantes_lista_apenas_o_que_falta(monkeypatch):
    monkeypatch.setenv('WHATSAPP_PHONE_NUMBER_ID', '123')
    assert whatsapp.variaveis_faltantes('meta_cloud') == ['WHATSAPP_TOKEN', 'WHATSAPP_TO']


def test_canal_desligado_explicitamente(monkeypatch, meta_configurado):
    monkeypatch.setenv('ALERT_WHATSAPP_ENABLED', 'false')
    assert whatsapp.whatsapp_habilitado() is False
    assert whatsapp.send_whatsapp('oi') is False


def test_canal_habilitado_por_deducao(meta_configurado):
    assert whatsapp.whatsapp_habilitado() is True


def test_meta_cloud_envia_texto_livre(meta_configurado, cliente):
    falso = cliente(RespostaFalsa(200, {'messages': [{'id': 'wamid.123'}]}))
    resultados = whatsapp.enviar_whatsapp('Nível laranja em Cuiabá')

    assert [r.ok for r in resultados] == [True]
    chamada = falso.chamadas[0]
    assert chamada['url'].endswith('/123456789/messages')
    assert whatsapp.VERSAO_API_META_PADRAO in chamada['url']
    assert chamada['headers']['Authorization'] == 'Bearer token-secreto-de-teste'
    assert chamada['json'] == {
        'messaging_product': 'whatsapp',
        'to': '5565999998888',
        'type': 'text',
        'text': {'preview_url': False, 'body': 'Nível laranja em Cuiabá'},
    }


def test_meta_cloud_usa_template_e_achata_quebras_de_linha(monkeypatch, meta_configurado, cliente):
    monkeypatch.setenv('WHATSAPP_TEMPLATE_NAME', 'alerta_vigia')
    falso = cliente(RespostaFalsa(200, {'messages': [{'id': 'wamid.1'}]}))
    whatsapp.enviar_whatsapp('Mudança de nível\nverde -> laranja')

    corpo = falso.chamadas[0]['json']
    assert corpo['type'] == 'template'
    assert corpo['template']['name'] == 'alerta_vigia'
    assert corpo['template']['language']['code'] == 'pt_BR'
    parametro = corpo['template']['components'][0]['parameters'][0]['text']
    assert '\n' not in parametro
    assert parametro == 'Mudança de nível | verde -> laranja'


def test_meta_cloud_reporta_mensagem_de_erro_da_api(meta_configurado, cliente):
    cliente(RespostaFalsa(400, {'error': {'message': 'Recipient phone number not in allowed list'}}))
    resultado = whatsapp.enviar_whatsapp('oi')[0]

    assert resultado.ok is False
    assert resultado.status_http == 400
    assert 'allowed list' in resultado.detalhe


def test_evolution_envia_no_formato_v2(evolution_configurado, cliente):
    falso = cliente(RespostaFalsa(201, {'status': 'PENDING'}))
    resultado = whatsapp.enviar_whatsapp('teste')[0]

    assert resultado.ok is True
    chamada = falso.chamadas[0]
    assert chamada['url'] == 'https://whats.exemplo.gov.br/message/sendText/vigia'
    assert chamada['headers']['apikey'] == 'chave-evolution'
    assert chamada['json'] == {'number': '5565999998888', 'text': 'teste'}


def test_evolution_repete_no_formato_v1_quando_recebe_400(evolution_configurado, cliente):
    falso = cliente(RespostaFalsa(400, {'error': 'Bad Request'}), RespostaFalsa(201, {'status': 'PENDING'}))
    resultado = whatsapp.enviar_whatsapp('teste')[0]

    assert resultado.ok is True
    assert len(falso.chamadas) == 2
    assert falso.chamadas[1]['json'] == {'number': '5565999998888', 'textMessage': {'text': 'teste'}}


def test_callmebot_trata_erro_com_http_200(monkeypatch, cliente):
    monkeypatch.setenv('CALLMEBOT_APIKEY', '123456')
    monkeypatch.setenv('CALLMEBOT_PHONE', '65999998888')
    cliente(RespostaFalsa(200, text='APIKey is invalid'))
    resultado = whatsapp.enviar_whatsapp('teste')[0]

    assert resultado.provedor == 'callmebot'
    assert resultado.ok is False


def test_callmebot_sucesso(monkeypatch, cliente):
    monkeypatch.setenv('CALLMEBOT_APIKEY', '123456')
    monkeypatch.setenv('CALLMEBOT_PHONE', '65999998888')
    falso = cliente(RespostaFalsa(200, text='Message queued. You will receive it in a few seconds.'))
    resultado = whatsapp.enviar_whatsapp('teste')[0]

    assert resultado.ok is True
    assert 'phone=%2B5565999998888' in falso.chamadas[0]['url']


def test_webhook_envia_payload_unico_com_todos_os_destinos(monkeypatch, cliente):
    monkeypatch.setenv('WHATSAPP_WEBHOOK_URL', 'https://n8n.exemplo.gov.br/webhook/vigia')
    monkeypatch.setenv('WHATSAPP_WEBHOOK_TOKEN', 'segredo')
    monkeypatch.setenv('WHATSAPP_TO', '65999998888, 65988887777')
    falso = cliente(RespostaFalsa(200, {'received': True}))
    resultados = whatsapp.enviar_whatsapp('teste', extra={'nivel_novo': 'laranja'})

    assert len(resultados) == 1 and resultados[0].ok
    chamada = falso.chamadas[0]
    assert chamada['headers']['Authorization'] == 'Bearer segredo'
    assert chamada['json'] == {
        'canal': 'whatsapp',
        'para': ['5565999998888', '5565988887777'],
        'mensagem': 'teste',
        'nivel_novo': 'laranja',
    }


def test_falha_de_rede_nao_levanta_excecao(meta_configurado, monkeypatch):
    def explodir(*args, **kwargs):
        raise ConnectionError('sem rede')

    monkeypatch.setattr(whatsapp.requests, 'post', explodir)
    resultado = whatsapp.enviar_whatsapp('teste')[0]

    assert resultado.ok is False
    assert 'erro de rede' in resultado.detalhe


def test_mensagem_maior_que_o_limite_e_truncada(meta_configurado, cliente):
    falso = cliente(RespostaFalsa(200, {'messages': []}))
    whatsapp.enviar_whatsapp('x' * (whatsapp.limite_caracteres() + 500))

    corpo = falso.chamadas[0]['json']['text']['body']
    assert len(corpo) == whatsapp.limite_caracteres()
    assert corpo.endswith('...')


def test_verificar_conexao_meta_nao_envia_mensagem(meta_configurado, cliente):
    falso = cliente(RespostaFalsa(200, {'display_phone_number': '+55 65 99999-8888', 'verified_name': 'VIGIA MT'}))
    resultado = whatsapp.verificar_conexao('meta_cloud')

    assert resultado.ok is True
    assert falso.chamadas[0]['metodo'] == 'GET'
    assert 'VIGIA MT' in resultado.detalhe


def test_verificar_conexao_evolution_exige_state_open(evolution_configurado, cliente):
    cliente(RespostaFalsa(200, {'instance': {'state': 'close'}}))
    resultado = whatsapp.verificar_conexao('evolution')

    assert resultado.ok is False
    assert 'QR Code' in resultado.detalhe


def test_send_whatsapp_devolve_booleano(meta_configurado, cliente):
    cliente(RespostaFalsa(200, {'messages': []}))
    assert whatsapp.send_whatsapp('teste') is True


def test_http_verify_respeita_ca_bundle(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('WHATSAPP_CA_BUNDLE', r'C:\TI\ca-corporativo.pem')
    assert whatsapp.http_verify() == r'C:\TI\ca-corporativo.pem'


def test_http_verify_pode_desligar_ssl(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('WHATSAPP_SSL_VERIFY', 'false')
    assert whatsapp.http_verify() is False


def test_envio_meta_passa_verify(meta_configurado, cliente, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('WHATSAPP_SSL_VERIFY', 'false')
    falso = cliente(RespostaFalsa(200, {'messages': []}))
    whatsapp.enviar_whatsapp('teste')
    assert falso.chamadas[0]['verify'] is False


def test_erro_ssl_sugere_correcao(meta_configurado, monkeypatch: pytest.MonkeyPatch):
    def explodir(*args, **kwargs):
        raise requests.exceptions.SSLError('[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed')

    monkeypatch.setattr(whatsapp.requests, 'post', explodir)
    resultado = whatsapp.enviar_whatsapp('teste')[0]
    assert 'WHATSAPP_CA_BUNDLE' in resultado.detalhe
    assert 'WHATSAPP_SSL_VERIFY=false' in resultado.detalhe
