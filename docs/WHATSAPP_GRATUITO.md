# Canal de WhatsApp gratuito

O SIS Clima-Saúde MT envia os alertas de mudança de nível por e-mail, Telegram, webhook e
WhatsApp. Este documento cobre o canal de WhatsApp e os provedores que operam sem custo de
licença.

A configuração é conduzida pelo **agente de configuração**, disponível de duas formas:

- página **Configurar WhatsApp** no painel (`pages/13_Configurar_WhatsApp.py`);
- linha de comando `python -m sisclima.alerts.whatsapp_agent`.

Os dois usam o mesmo código (`sisclima/alerts/whatsapp_agent.py`) e leem as mesmas variáveis
de ambiente.

## Qual provedor escolher

| Provedor | Tipo | Custo | Quando usar |
|---|---|---|---|
| `meta_cloud` | Oficial (Meta) | Sem mensalidade. Número de teste gratuito. Mensagens de serviço e templates utilitários dentro da janela de 24h não são cobrados; templates fora dela são cobrados por mensagem. | Comunicação oficial com número institucional, sem servidor próprio. |
| `evolution` | Não oficial (open source) | Só o custo do servidor onde roda. Sem cobrança por mensagem. | Já existe servidor/Docker e o volume proativo é alto. |
| `callmebot` | Não oficial (serviço de terceiro) | Zero. | Plantão e testes: avisar 1 ou 2 celulares da equipe técnica. |
| `webhook` | Ponte (n8n, Make, Zapier, Apps Script) | Depende da ferramenta; n8n auto-hospedado é gratuito. | Já existe automação montada e o VIGIA só precisa disparar o gatilho. |

Em caso de dúvida:

```bash
python -m sisclima.alerts.whatsapp_agent recomendar --uso institucional
python -m sisclima.alerts.whatsapp_agent listar
```

> A Evolution API e o CallMeBot conectam como WhatsApp Web ou por serviço de terceiro. Não são
> caminhos homologados pela Meta e o número pode ser bloqueado. Para comunicação oficial com a
> população, use `meta_cloud`.

## Variáveis de ambiente

Comuns a todos os provedores:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `ALERT_WHATSAPP_ENABLED` | não | Liga/desliga o canal. Sem ela, o canal liga sozinho quando há provedor completo. |
| `WHATSAPP_PROVIDER` | não | `auto` (padrão), `meta_cloud`, `evolution`, `callmebot` ou `webhook`. |
| `WHATSAPP_TO` | depende | Destinatários separados por vírgula, ponto e vírgula ou quebra de linha. Aceita `(65) 99999-8888`; o DDI 55 é acrescentado automaticamente. |
| `WHATSAPP_DDI_PADRAO` | não | DDI aplicado a números com 10 ou 11 dígitos. Padrão `55`. |

Com `WHATSAPP_PROVIDER=auto`, o primeiro provedor completamente configurado é usado, na ordem
`meta_cloud`, `evolution`, `callmebot`, `webhook`.

### `meta_cloud` — WhatsApp Cloud API

| Variável | Obrigatória | Descrição |
|---|---|---|
| `WHATSAPP_PHONE_NUMBER_ID` | sim | Phone Number ID exibido na aba **API Setup**. |
| `WHATSAPP_TOKEN` | sim | Token de acesso (temporário para testar, permanente para produção). |
| `WHATSAPP_TO` | sim | Celulares que receberão o alerta. |
| `WHATSAPP_API_VERSION` | não | Versão da Graph API. Padrão `v23.0`. |
| `WHATSAPP_TEMPLATE_NAME` | não | Template aprovado, necessário para envio proativo. |
| `WHATSAPP_TEMPLATE_LANG` | não | Idioma do template. Padrão `pt_BR`. |

Passo a passo:

1. Crie um app do tipo **Negócios** em [developers.facebook.com](https://developers.facebook.com) e
   adicione o produto **WhatsApp**.
2. Em **API Setup**, copie o **Phone number ID** do número de teste gratuito.
3. Gere o token: o temporário (24h) serve para testar; para produção, crie um usuário do sistema em
   **Configurações do Negócio > Usuários do sistema** e gere um token permanente.
4. Ainda em **API Setup**, cadastre em **To** os celulares que receberão os alertas e confirme o
   código enviado a cada um. **O número de teste não entrega nada para quem não estiver nessa lista
   (limite de 5 destinatários).**
5. Para alerta proativo, crie em **WhatsApp Manager > Modelos de mensagem** um template da categoria
   **Utilidade** com um parâmetro `{{1}}` no corpo, e preencha `WHATSAPP_TEMPLATE_NAME`.

Sobre a cobrança: a Meta não cobra pelo acesso à API. Mensagens de texto livre só podem ser enviadas
dentro da janela de 24h aberta por uma mensagem do cidadão, e nesse caso são gratuitas. Templates
utilitários dentro dessa janela também são gratuitos. Um template enviado fora da janela — o caso
típico de um alerta proativo de nível — é cobrado por mensagem, com preço por país e categoria.

Sem `WHATSAPP_TEMPLATE_NAME`, o SIS envia texto livre, que só chega dentro da janela de 24h.

### `evolution` — Evolution API v2 auto-hospedada

| Variável | Obrigatória | Descrição |
|---|---|---|
| `EVOLUTION_API_URL` | sim | URL base da API, alcançável pela máquina do pipeline. |
| `EVOLUTION_API_KEY` | sim | `AUTHENTICATION_API_KEY` definida ao subir o contêiner. |
| `EVOLUTION_INSTANCE` | sim | Nome da instância (não o UUID). |
| `WHATSAPP_TO` | sim | Celulares que receberão o alerta. |

Passo a passo:

1. Suba a API com a imagem oficial (`evoapicloud/evolution-api`), definindo uma
   `AUTHENTICATION_API_KEY` forte.
2. Crie a instância com `POST /instance/create`.
3. Conecte o número com `GET /instance/connect/{instancia}` e leia o QR Code no celular.
4. Confirme que `GET /instance/connectionState/{instancia}` responde `state: open`.

O SIS envia no formato v2 (`POST /message/sendText/{instancia}` com `{"number": ..., "text": ...}`) e
repete automaticamente no formato v1 (`textMessage.text`) quando a instância responde HTTP 400.

Use HTTPS: a chave da API vai no cabeçalho `apikey` e trafega em claro sobre HTTP.

### `callmebot`

| Variável | Obrigatória | Descrição |
|---|---|---|
| `CALLMEBOT_APIKEY` | sim | Chave devolvida pelo robô. |
| `CALLMEBOT_PHONE` | sim | Celular que autorizou o robô. |

O número do robô muda de tempos em tempos, então pegue o vigente em
[callmebot.com/blog/free-api-whatsapp-messages](https://www.callmebot.com/blog/free-api-whatsapp-messages/),
salve nos contatos e envie a frase exata `I allow callmebot to send me messages`. O robô responde
com `API Activated for your phone number. Your APIKEY is ...`.

A chave é individual e vale para **um único celular**: `WHATSAPP_TO` com vários números não faz o
CallMeBot entregar para todos, só o dono da chave recebe. Para uma lista de destinatários, use outro
provedor.

O CallMeBot responde HTTP 200 mesmo quando a chave está errada; o SIS inspeciona o corpo da resposta
para detectar esse caso.

### `webhook` — ponte com n8n, Make, Zapier

| Variável | Obrigatória | Descrição |
|---|---|---|
| `WHATSAPP_WEBHOOK_URL` | sim | Endpoint que recebe o alerta. |
| `WHATSAPP_WEBHOOK_TOKEN` | não | Enviado no cabeçalho `Authorization: Bearer`. |
| `WHATSAPP_TO` | não | Vai no payload para a ferramenta decidir o destino. |

O SIS faz um único `POST` com o corpo:

```json
{
  "canal": "whatsapp",
  "para": ["5565999998888"],
  "mensagem": "[SIS Clima-Saúde] Mudança de nível: verde -> laranja\n\n...",
  "subject": "[SIS Clima-Saúde] Mudança de nível: verde -> laranja",
  "data_referencia": "2026-07-31",
  "nivel_anterior": "verde",
  "nivel_novo": "laranja",
  "indicadores": {}
}
```

> **Mudança de comportamento:** `WHATSAPP_WEBHOOK_URL` deixou de ser alias de `WEBHOOK_URL`. Antes,
> essa variável alimentava o webhook genérico; agora ela pertence ao canal de WhatsApp. Quem usava
> `WHATSAPP_WEBHOOK_URL` para o webhook genérico e quer manter esse comportamento deve renomear a
> variável para `WEBHOOK_URL`.

## Usando o agente

### Pela página do painel

Abra **Configurar WhatsApp** no menu lateral. A página compara os provedores, mostra o passo a passo
com o que já está pronto, recebe as credenciais, roda o diagnóstico, testa o envio e entrega o bloco
pronto para `.env` ou `secrets.toml`.

Nada digitado na página é gravado em disco: os valores valem apenas para aquela sessão, o suficiente
para o teste. Para valer em produção, copie o bloco gerado.

### Pela linha de comando

```bash
# comparar provedores e ver o que já está configurado
python -m sisclima.alerts.whatsapp_agent listar

# passo a passo de um provedor
python -m sisclima.alerts.whatsapp_agent plano --provedor meta_cloud

# o que ainda falta no ambiente atual (sai com código 1 se não estiver pronto)
python -m sisclima.alerts.whatsapp_agent diagnostico

# gerar o bloco de configuração
python -m sisclima.alerts.whatsapp_agent env --provedor evolution
python -m sisclima.alerts.whatsapp_agent env --provedor meta_cloud --formato toml

# enviar mensagem de teste
python -m sisclima.alerts.whatsapp_agent testar --para 65999998888
```

Todos os comandos aceitam `--json` para uso em script. O diagnóstico mascara tokens e chaves na
saída.

## Onde colocar as credenciais

- **Pipeline local (produção dos alertas):** arquivo `.env` na raiz, lido por
  `sisclima/core/config.py`. É onde o envio automático realmente acontece.
- **Streamlit Cloud:** **Settings > Secrets** do app. A página exporta os segredos para
  `os.environ`, então o restante do SIS os enxerga.

O `.gitignore` já bloqueia `.env`, `*.env` e `secrets.toml`. Nunca versione credenciais.

## Como o alerta é disparado

`sisclima/alerts/change_detector.py` chama `dispatch_alert` quando o nível do estado muda, e
`dispatch_alert` aciona todos os canais habilitados:

```python
{'email': True, 'telegram': False, 'whatsapp': True, 'webhook': False}
```

O resultado é gravado na coluna `canais` da tabela `alertas_enviados`. Falha de um canal não
interrompe os demais nem o pipeline: erros de rede e de credencial viram `False` com registro no log.

## Testes

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Os testes não fazem chamadas de rede reais: as respostas HTTP são simuladas.
