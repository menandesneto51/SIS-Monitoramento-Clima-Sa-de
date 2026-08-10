# -*- coding: utf-8 -*-
"""Testes do agente de configuração do WhatsApp."""
from __future__ import annotations

import os

import pytest

from sisclima.alerts import whatsapp, whatsapp_agent


@pytest.fixture
def meta_completo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('WHATSAPP_PHONE_NUMBER_ID', '123456789')
    monkeypatch.setenv('WHATSAPP_TOKEN', 'EAAG-token-longo-de-teste')
    monkeypatch.setenv('WHATSAPP_TO', '65999998888')


def test_catalogo_cobre_todos_os_provedores_do_canal():
    assert set(whatsapp_agent.CATALOGO) == set(whatsapp.PROVEDORES)
    for nome, info in whatsapp_agent.CATALOGO.items():
        assert info.variaveis_obrigatorias == whatsapp.VARIAVEIS_OBRIGATORIAS[nome]
        assert info.passos, f'{nome} precisa de passo a passo'
        assert info.documentacao.startswith('https://')


def test_diagnostico_sem_nada_configurado_orienta_a_escolher_provedor():
    diag = whatsapp_agent.diagnosticar()

    assert diag.provedor is None
    assert diag.pronto is False
    assert diag.provedores_configurados == []
    assert 'Nenhum provedor' in diag.problemas[0]
    assert any('Raiz do projeto:' in aviso for aviso in diag.avisos)
    assert any('.env' in aviso for aviso in diag.avisos)


def test_diagnostico_detecta_variaveis_whatsapp_no_env(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text('WHATSAPP_NUMERO_ERRADO=123\nMETA_TOKEN=abc\n', encoding='utf-8')
    monkeypatch.setattr(whatsapp_agent, 'ROOT', tmp_path)
    monkeypatch.setattr(
        'sisclima.core.config.ENV_DOTENV_CANDIDATES',
        (tmp_path / '.env',),
    )
    monkeypatch.setattr(
        'sisclima.core.config.env_dotenv_paths',
        lambda: [env_file],
    )

    diag = whatsapp_agent.diagnosticar()

    assert any('WHATSAPP_NUMERO_ERRADO' in aviso for aviso in diag.avisos)


def test_diagnostico_aponta_variaveis_faltantes(monkeypatch):
    monkeypatch.setenv('WHATSAPP_PROVIDER', 'meta_cloud')
    monkeypatch.setenv('WHATSAPP_PHONE_NUMBER_ID', '123456789')
    diag = whatsapp_agent.diagnosticar()

    assert diag.pronto is False
    assert any('WHATSAPP_TOKEN' in p for p in diag.problemas)
    assert any('WHATSAPP_TO' in p for p in diag.problemas)


def test_diagnostico_completo_avisa_sobre_template(meta_completo):
    diag = whatsapp_agent.diagnosticar()

    assert diag.provedor == 'meta_cloud'
    assert diag.pronto is True
    assert diag.canal_habilitado is True
    assert diag.destinatarios == ['5565999998888']
    assert any('template' in aviso.lower() for aviso in diag.avisos)


def test_diagnostico_mascara_segredos(meta_completo):
    diag = whatsapp_agent.diagnosticar()

    assert diag.variaveis['WHATSAPP_PHONE_NUMBER_ID'] == '123456789'
    assert diag.variaveis['WHATSAPP_TOKEN'] != 'EAAG-token-longo-de-teste'
    assert diag.variaveis['WHATSAPP_TOKEN'].startswith('EAAG')
    assert '******' in diag.variaveis['WHATSAPP_TOKEN']


def test_diagnostico_avisa_sobre_evolution_em_http(monkeypatch):
    monkeypatch.setenv('EVOLUTION_API_URL', 'http://192.168.0.10:8080')
    monkeypatch.setenv('EVOLUTION_API_KEY', 'chave')
    monkeypatch.setenv('EVOLUTION_INSTANCE', 'vigia')
    monkeypatch.setenv('WHATSAPP_TO', '65999998888')
    diag = whatsapp_agent.diagnosticar()

    assert diag.pronto is True
    assert any('HTTPS' in aviso for aviso in diag.avisos)


def test_diagnostico_avisa_que_callmebot_atende_um_celular_so(monkeypatch):
    monkeypatch.setenv('CALLMEBOT_APIKEY', '123456')
    monkeypatch.setenv('CALLMEBOT_PHONE', '65999998888')
    monkeypatch.setenv('WHATSAPP_TO', '65999998888, 65988887777')
    diag = whatsapp_agent.diagnosticar()

    assert diag.pronto is True
    assert diag.destinatarios == ['5565999998888']
    assert any('5565988887777' in aviso for aviso in diag.avisos)


def test_diagnostico_avisa_quando_canal_esta_desligado(monkeypatch, meta_completo):
    monkeypatch.setenv('ALERT_WHATSAPP_ENABLED', 'false')
    diag = whatsapp_agent.diagnosticar()

    assert diag.canal_habilitado is False
    assert any('ALERT_WHATSAPP_ENABLED' in aviso for aviso in diag.avisos)


def test_diagnostico_de_provedor_desconhecido():
    diag = whatsapp_agent.diagnosticar('sinal_de_fumaca')

    assert diag.pronto is False
    assert 'desconhecido' in diag.problemas[0]


def test_passos_pendentes_somem_conforme_variaveis_chegam(monkeypatch):
    todos = whatsapp_agent.passos_pendentes('evolution')
    assert len(todos) == len(whatsapp_agent.CATALOGO['evolution'].passos)

    monkeypatch.setenv('EVOLUTION_API_URL', 'https://whats.exemplo.gov.br')
    monkeypatch.setenv('EVOLUTION_API_KEY', 'chave')
    monkeypatch.setenv('EVOLUTION_INSTANCE', 'vigia')
    monkeypatch.setenv('WHATSAPP_TO', '65999998888')

    assert whatsapp_agent.passos_pendentes('evolution') == []


def test_mascarar():
    assert whatsapp_agent.mascarar('') == ''
    assert whatsapp_agent.mascarar('curto') == '*****'
    assert whatsapp_agent.mascarar('token-bem-longo-mesmo') == 'toke******esmo'


@pytest.mark.parametrize(
    'kwargs, esperado',
    [
        ({}, 'meta_cloud'),
        ({'uso': 'automacao'}, 'webhook'),
        # O CallMeBot nunca é recomendado: o cadastro dele fica fechado quando o robô lota.
        ({'uso': 'interno'}, 'meta_cloud'),
        ({'uso': 'interno', 'tem_servidor': True}, 'meta_cloud'),
        ({'tem_servidor': True, 'volume_alto': True}, 'evolution'),
    ],
)
def test_recomendar(kwargs, esperado):
    provedor, motivo = whatsapp_agent.recomendar(**kwargs)
    assert provedor == esperado
    assert motivo


def test_gerar_env_traz_todas_as_variaveis_do_provedor():
    bloco = whatsapp_agent.gerar_env('meta_cloud', {'WHATSAPP_TOKEN': 'abc123'})

    assert 'ALERT_WHATSAPP_ENABLED=true' in bloco
    assert 'WHATSAPP_PROVIDER=meta_cloud' in bloco
    assert 'WHATSAPP_TOKEN=abc123' in bloco
    for nome in whatsapp.VARIAVEIS_OBRIGATORIAS['meta_cloud']:
        assert f'{nome}=' in bloco


def test_gerar_secrets_toml_escapa_aspas():
    bloco = whatsapp_agent.gerar_secrets_toml('webhook', {'WHATSAPP_WEBHOOK_URL': 'https://n8n/"x"'})

    assert 'WHATSAPP_PROVIDER = "webhook"' in bloco
    assert r'WHATSAPP_WEBHOOK_URL = "https://n8n/\"x\""' in bloco


def test_gerar_env_rejeita_provedor_invalido():
    with pytest.raises(ValueError):
        whatsapp_agent.gerar_env('sinal_de_fumaca')


def test_aplicar_na_sessao_define_e_remove(monkeypatch):
    monkeypatch.setenv('WHATSAPP_TOKEN', 'antigo')
    aplicadas = whatsapp_agent.aplicar_na_sessao({'WHATSAPP_TO': '65999998888', 'WHATSAPP_TOKEN': ''})

    assert aplicadas == ['WHATSAPP_TO']
    assert os.environ['WHATSAPP_TO'] == '65999998888'
    assert 'WHATSAPP_TOKEN' not in os.environ


def test_resumo_texto_nao_vaza_segredo(meta_completo):
    texto = whatsapp_agent.resumo_texto(whatsapp_agent.diagnosticar())

    assert 'EAAG-token-longo-de-teste' not in texto
    assert 'Pronto para enviar: sim' in texto


def test_cli_listar_e_plano(capsys):
    assert whatsapp_agent.main(['listar']) == 0
    assert 'meta_cloud' in capsys.readouterr().out

    assert whatsapp_agent.main(['plano', '--provedor', 'evolution']) == 0
    assert 'QR Code' in capsys.readouterr().out


def test_cli_diagnostico_falha_sem_configuracao(capsys):
    assert whatsapp_agent.main(['diagnostico']) == 1
    assert 'Nenhum provedor' in capsys.readouterr().out


def test_cli_verificar_mostra_ausencia(capsys):
    assert whatsapp_agent.main(['verificar']) == 1
    saida = capsys.readouterr().out
    assert 'Raiz do projeto:' in saida
    assert 'WHATSAPP_TOKEN' in saida


def test_cli_aplicar_habilita_teste_na_sessao(capsys, monkeypatch):
    monkeypatch.delenv('WHATSAPP_PHONE_NUMBER_ID', raising=False)
    monkeypatch.delenv('WHATSAPP_TOKEN', raising=False)
    monkeypatch.delenv('WHATSAPP_TO', raising=False)
    codigo = whatsapp_agent.main([
        'aplicar',
        '--valor', 'ALERT_WHATSAPP_ENABLED=true',
        '--valor', 'WHATSAPP_PROVIDER=meta_cloud',
        '--valor', 'WHATSAPP_PHONE_NUMBER_ID=123',
        '--valor', 'WHATSAPP_TOKEN=EAAG-teste',
        '--valor', 'WHATSAPP_TO=65999998888',
    ])
    assert codigo == 0
    assert 'Pronto para enviar: sim' in capsys.readouterr().out


def test_cli_diagnostico_json_quando_pronto(capsys, meta_completo):
    assert whatsapp_agent.main(['--json', 'diagnostico']) == 0
    saida = capsys.readouterr().out
    assert '"pronto": true' in saida
    assert 'EAAG-token-longo-de-teste' not in saida


def test_cli_env(capsys):
    assert whatsapp_agent.main(['env', '--provedor', 'callmebot', '--valor', 'CALLMEBOT_PHONE=65999998888']) == 0
    assert 'CALLMEBOT_PHONE=65999998888' in capsys.readouterr().out


def test_cli_testar_sem_configuracao(capsys):
    assert whatsapp_agent.main(['testar']) == 1
    assert 'ERRO' in capsys.readouterr().out


def test_cli_registrar(meta_completo, capsys, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        whatsapp,
        'registrar_numero_meta',
        lambda pin: whatsapp.ResultadoEnvio(True, 'meta_cloud', '123', 'ok'),
    )
    assert whatsapp_agent.main(['registrar', '--pin', '123456']) == 0
    assert '[OK' in capsys.readouterr().out


def test_cli_status(meta_completo, capsys, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        whatsapp,
        'consultar_numero_meta',
        lambda: whatsapp.ResultadoEnvio(
            True,
            'meta_cloud',
            '+55 65 99999-8888',
            'platform_type=CLOUD_API',
            200,
            {'platform_type': 'CLOUD_API', 'is_on_biz_app': False},
        ),
    )
    assert whatsapp_agent.main(['status']) == 0
    assert 'CLOUD_API' in capsys.readouterr().out
