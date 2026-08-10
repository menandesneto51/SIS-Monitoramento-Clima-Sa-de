# Tutorial passo a passo — WhatsApp Cloud API (Meta) + SIS Clima-Saúde MT

Este guia leva do zero até o envio real de alertas do VIGIA pelo WhatsApp, usando a **Cloud API
oficial da Meta**. Foi escrito para o cenário em que o número **já está no WhatsApp Business** no
celular — por exemplo `+55 65 99219-0039`.

**Tempo estimado de leitura:** 30–45 minutos para concluir todas as fases.  
**Pré-requisito técnico:** acesso de administrador ao Meta Business Suite e à máquina que roda o
pipeline do `sisclima`.

Documentos relacionados:

- [`META_ONDE_CLICAR.md`](META_ONDE_CLICAR.md) — **se não achar API Setup** (interface Meta 2026)
- [`WHATSAPP_GRATUITO.md`](WHATSAPP_GRATUITO.md) — visão geral dos provedores e variáveis
- [`OPERACAO.md`](OPERACAO.md) — rotina diária do pipeline

---

## Visão geral das fases

| Fase | O que você faz | Mexe no seu número? |
|---|---|---|
| 0 | Decidir coexistência ou migração | Não |
| 1 | Criar app Meta + produto WhatsApp | Não |
| 2 | Testar com número de teste gratuito da Meta | Não |
| 3 | Vincular o número real (ex.: 99219-0039) | **Sim** |
| 4 | Registrar o número na Cloud API | Sim |
| 5 | Gerar token permanente | Não |
| 6 | Configurar o `.env` do SIS | Não |
| 7 | Criar template para alertas automáticos | Não |
| 8 | Validar envio de teste | Não |
| 9 | Colocar em produção no pipeline | Não |

> **Regra de ouro:** conclua a **Fase 2** antes de vincular o número real. Assim você confirma que o
> SIS envia mensagens sem arriscar o WhatsApp Business que já funciona no celular.

---

## Fase 0 — Decisão: manter o app no celular ou não?

Seu número está no **WhatsApp Business** (app no celular). Ao conectá-lo à Cloud API, existem dois
caminhos:

### Opção A — Coexistência (recomendada)

| | |
|---|---|
| **O que é** | App no celular **e** API no SIS, **no mesmo número** |
| **Vantagem** | Equipe continua atendendo manualmente; alertas saem pela API |
| **Requisitos** | WhatsApp Business **≥ 2.24.17**; não desinstalar o app; abrir o app a cada ~13 dias |
| **Na Meta** | Escolher **“Conectar WhatsApp Business App”** / **“Número já usado no WhatsApp Business”** |

### Opção B — Migração total

| | |
|---|---|
| **O que é** | Número passa a ser **só** da API; o app deixa de funcionar com esse número |
| **Quando** | Só automação, sem atendimento manual no app |
| **Risco** | Apagar a conta no app **sem backup** perde histórico |

**Checklist antes de continuar:**

- [ ] Celular com WhatsApp Business atualizado
- [ ] Conta Meta Business da secretaria (CNPJ / portfólio empresarial)
- [ ] Acesso a [developers.facebook.com](https://developers.facebook.com)
- [ ] Máquina local com o repositório do SIS e Python instalado
- [ ] Número anotado no formato internacional: **+55 65 99219-0039**

---

> **Não achou a tela API Setup?** Siga [`META_ONDE_CLICAR.md`](META_ONDE_CLICAR.md) ou rode
> `python -m sisclima.alerts.whatsapp_agent descobrir --token EAA...` após gerar token no
> [Explorador da Graph API](https://developers.facebook.com/tools/explorer).

## Fase 1 — Criar o app na Meta

### 1.1 Entrar no Meta for Developers

1. Abra [developers.facebook.com](https://developers.facebook.com)
2. Entre com a conta que administra o WhatsApp Business da secretaria
3. Se pedir verificação de identidade ou e-mail, conclua antes de seguir

### 1.2 Criar o aplicativo

1. Menu **Meus apps** → **Criar app**
2. Tipo de uso: **Outro** ou **Negócios**
3. Preencha:
   - **Nome do app:** `SIS Clima-Saude MT` (ou `VIGIA Alertas`)
   - **E-mail de contato:** e-mail institucional
   - **Portfólio empresarial:** selecione o da SES/secretaria
4. Clique **Criar app**

### 1.3 Adicionar o produto WhatsApp

1. No painel do app → **Adicionar produto**
2. Localize **WhatsApp** → **Configurar**
3. No menu lateral, abra **WhatsApp → API Setup** (Configuração da API)

### 1.4 Anotar os dados do número de teste

A Meta fornece um **número de teste gratuito**. Na tela **API Setup**, copie para um bloco de notas:

| Campo na tela Meta | O que é | Variável no SIS |
|---|---|---|
| **Phone number ID** | ID numérico longo (~15 dígitos) | `WHATSAPP_PHONE_NUMBER_ID` |
| **WhatsApp Business Account ID** | ID da conta WABA | referência |
| **Temporary access token** | Token que expira em 24h | `WHATSAPP_TOKEN` (só para teste rápido) |

> **Atenção:** copie o **Phone number ID**, não o telefone `+1 555...`. São coisas diferentes.

**Checkpoint Fase 1:**

- [ ] App criado no Meta for Developers
- [ ] Produto WhatsApp adicionado
- [ ] Phone number ID do **número de teste** anotado
- [ ] Token temporário anotado (ou pule para Fase 5 se for direto ao permanente)

---

## Fase 2 — Testar com o número de teste (sem mexer no seu WhatsApp Business)

Esta fase valida que o **SIS consegue enviar** antes de vincular o `99219-0039`.

### 2.1 Cadastrar seu celular como destinatário de teste

1. Na **API Setup**, localize a seção **To** (destinatários / “Send messages to”)
2. Clique **Manage phone number list** ou **Gerenciar lista**
3. Adicione: **+55 65 99219-0039** (ou o celular que vai receber o teste)
4. Confirme o código recebido por SMS ou ligação

> O número de teste da Meta **só envia** para até **5 destinatários** cadastrados nesta lista.

### 2.2 Abrir a janela de 24 horas (importante)

Sem template aprovado, a Meta só entrega **texto livre** dentro de uma janela de 24h aberta por
uma mensagem **do destinatário**.

1. No seu celular, abra o WhatsApp
2. Envie **"oi"** ou **"teste"** para o **número de teste** que aparece na API Setup
3. Aguarde a confirmação de entrega

### 2.3 Criar o arquivo `.env` na máquina do pipeline

Na **raiz do repositório** (mesma pasta do `streamlit_app.py`), crie ou edite o arquivo `.env`:

```bash
# --- WhatsApp Cloud API (Meta) — FASE 2: teste com número de teste ---
ALERT_WHATSAPP_ENABLED=true
WHATSAPP_PROVIDER=meta_cloud
WHATSAPP_PHONE_NUMBER_ID=<cole o Phone number ID do NÚMERO DE TESTE>
WHATSAPP_TOKEN=<cole o token temporário EAA... ou permanente>
WHATSAPP_TO=65992190039
```

**O que NÃO preencher nesta fase:**

```bash
# Deixe estas linhas FORA do .env por enquanto:
# WHATSAPP_TEMPLATE_NAME=...
# WHATSAPP_TEMPLATE_LANG=...
# WHATSAPP_API_VERSION=...   (padrão v23.0)
# WHATSAPP_DDI_PADRAO=...    (padrão 55)
```

### 2.4 Rodar o diagnóstico e o teste

Na pasta do projeto:

```bash
python -m sisclima.alerts.whatsapp_agent diagnostico
python -m sisclima.alerts.whatsapp_agent testar
```

**Resultado esperado:**

```
[OK ] meta_cloud -> 5565992190039: mensagem aceita pela Cloud API
```

E a mensagem de teste chega no WhatsApp do celular cadastrado.

**Se falhar**, consulte a seção [Solução de problemas](#solução-de-problemas) no final deste guia.

**Checkpoint Fase 2:**

- [ ] Celular cadastrado na lista **To** da API Setup
- [ ] Mensagem "oi" enviada do celular para o número de teste
- [ ] `.env` criado com Phone number ID do **teste**
- [ ] `diagnostico` retorna **Pronto para enviar: sim**
- [ ] `testar` entrega mensagem no celular

---

## Fase 3 — Vincular o número real (+55 65 99219-0039)

> Só avance se a **Fase 2** funcionou.

### 3.1 Adicionar o número na Meta

1. **API Setup** → **Add phone number** / **Adicionar número de telefone**
2. País: **Brasil (+55)**
3. Número: **65 99219-0039**
4. Na tela seguinte, **se disponível**, escolha:
   - **“Conectar WhatsApp Business App”**, ou
   - **“Este número já está em uso no WhatsApp Business”**
   
   Isso ativa a **coexistência** (Opção A da Fase 0).

5. Escolha verificação por **SMS** ou **ligação** — o código chega no celular com o app instalado
6. Preencha o perfil do número:
   - **Nome de exibição:** ex. `SES MT VIGIA` ou `Clima-Saude MT`
   - **Categoria:** Governo ou Saúde
   - **Fuso horário:** `America/Cuiaba`

### 3.2 Anotar o novo Phone number ID

Depois de verificado, o número aparece no seletor **From** da API Setup.

1. Selecione **+55 65 99219-0039** no dropdown **From**
2. Copie o **Phone number ID** deste número — **é diferente** do número de teste
3. Guarde como `PHONE_NUMBER_ID_PRODUCAO`

### 3.3 Se não aparecer opção de coexistência

Alguns fluxos da Meta ainda pedem migração clássica:

1. **Faça backup** do histórico no WhatsApp Business (Configurações → Conversas → Backup)
2. No app: **Configurações → Conta → Apagar conta**
3. Aguarde **5–10 minutos**
4. Repita o passo 3.1 para registrar o número na API

> Após migração total, o app **não** funciona mais com esse número. Prefira coexistência sempre
> que a opção existir.

**Checkpoint Fase 3:**

- [ ] Número +55 65 99219-0039 verificado na Meta
- [ ] Phone number ID de **produção** anotado (diferente do teste)
- [ ] App WhatsApp Business continua abrindo normalmente (coexistência) **ou** migração consciente feita

---

## Fase 4 — Registrar o número para uso na Cloud API

Adicionar e verificar o número **não basta**. É preciso **registrá-lo** para a Cloud API.

### 4.1 Pelo painel (quando disponível)

Na **API Setup**, se aparecer aviso **“Please register your phone number”**:

1. Clique no link **Register** ao lado do número
2. Defina um **PIN de 6 dígitos** (ex.: `123456`) e anote em local seguro
3. Confirme

### 4.2 Pela API (alternativa)

Substitua `<PHONE_NUMBER_ID_PRODUCAO>` e `<SEU_TOKEN>`:

```bash
curl -X POST "https://graph.facebook.com/v23.0/<PHONE_NUMBER_ID_PRODUCAO>/register" \
  -H "Authorization: Bearer <SEU_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "pin": "123456"
  }'
```

Resposta esperada: HTTP 200 sem erro.

Para armazenamento de dados no Brasil (opcional):

```json
{
  "messaging_product": "whatsapp",
  "pin": "123456",
  "data_localization_region": "BR"
}
```

**Checkpoint Fase 4:**

- [ ] Número registrado (sem aviso “Please register” no painel)
- [ ] PIN de 6 dígitos anotado

---

## Fase 5 — Token permanente (obrigatório para produção)

O token temporário da API Setup expira em **24 horas**. O pipeline precisa de um **permanente**.

### 5.1 Criar usuário do sistema

1. Abra [business.facebook.com](https://business.facebook.com)
2. **Configurações do negócio** (ícone de engrenagem)
3. **Usuários → Usuários do sistema → Adicionar**
4. Nome: `sisclima-api`
5. Função: **Administrador** (ou função com acesso ao app WhatsApp)

### 5.2 Atribuir ativos

1. Com o usuário selecionado → **Adicionar ativos**
2. Tipo **Apps** → selecione o app `SIS Clima-Saude MT`
3. Permissão: **Controle total**
4. Tipo **Contas do WhatsApp** → selecione a WABA
5. Permissão: **Controle total**

### 5.3 Gerar o token

1. **Gerar token**
2. Selecione o app WhatsApp
3. Marque as permissões:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
4. **Gerar token** → copie o valor (`EAA...` — ~200 caracteres)
5. Guarde em local seguro; **não versione** no Git

**Checkpoint Fase 5:**

- [ ] Token permanente `EAA...` gerado e guardado
- [ ] Usuário do sistema `sisclima-api` criado

---

## Fase 6 — Configurar o `.env` de produção no SIS

Atualize o `.env` na máquina que roda o **pipeline** (não só o painel Streamlit Cloud):

```bash
# --- WhatsApp Cloud API (Meta) — PRODUÇÃO ---
ALERT_WHATSAPP_ENABLED=true
WHATSAPP_PROVIDER=meta_cloud
WHATSAPP_PHONE_NUMBER_ID=<PHONE_NUMBER_ID_PRODUCAO do 99219-0039>
WHATSAPP_TOKEN=<token permanente EAA...>
WHATSAPP_TO=65992190039
```

### Vários destinatários

Separe por vírgula (equipe técnica, gestores):

```bash
WHATSAPP_TO=65992190039,65988887777,6533334444
```

### Campos que devem ficar de fora (por enquanto)

| Campo | Motivo |
|---|---|
| `WHATSAPP_TEMPLATE_NAME` | Só depois da Fase 7 (template aprovado) |
| `WHATSAPP_API_VERSION` | Padrão `v23.0` — não precisa |
| `WHATSAPP_DDI_PADRAO` | Padrão `55` — não precisa |

### Conferir credenciais sem enviar mensagem

```bash
python -m sisclima.alerts.whatsapp_agent diagnostico
```

Saída esperada:

```
Provedor: WhatsApp Cloud API (Meta, oficial)
Pronto para enviar: sim
Canal habilitado: sim
Destinatários: 5565992190039
```

Para checar se o token acessa o número (sem disparar alerta):

```bash
python -c "
from sisclima.alerts.whatsapp import verificar_conexao
r = verificar_conexao('meta_cloud')
print('OK' if r.ok else 'ERRO', '-', r.detalhe)
"
```

**Checkpoint Fase 6:**

- [ ] `.env` atualizado com Phone number ID de **produção**
- [ ] Token **permanente** no `.env`
- [ ] `diagnostico` retorna pronto

---

## Fase 7 — Template para alertas automáticos do VIGIA

Os alertas do VIGIA são **proativos** (saem sem o cidadão ter escrito antes). Fora da janela de
24h, a Meta **só aceita template aprovado**.

### 7.1 Criar o modelo

1. [business.facebook.com](https://business.facebook.com) → **WhatsApp Manager**
2. **Modelos de mensagem** → **Criar modelo**
3. Preencha:

| Campo | Valor sugerido |
|---|---|
| Nome | `alerta_vigia` (só minúsculas, números e `_`) |
| Categoria | **Utilidade** (nunca Marketing para alerta operacional) |
| Idioma | **Português (Brasil)** — `pt_BR` |

4. Corpo da mensagem:

```
🌡️ Alerta VIGIA — Clima-Saúde MT

{{1}}

Este é um alerta automático do sistema de vigilância em saúde.
```

5. O parâmetro `{{1}}` receberá o texto completo do alerta gerado pelo SIS
6. Envie para **aprovação da Meta**

Aprovação costuma levar de **1 a 24 horas**.

### 7.2 Ativar o template no `.env`

Quando o status do modelo for **Aprovado**:

```bash
WHATSAPP_TEMPLATE_NAME=alerta_vigia
WHATSAPP_TEMPLATE_LANG=pt_BR
```

### 7.3 Testar envio proativo

```bash
python -m sisclima.alerts.whatsapp_agent testar --mensagem "Teste de alerta proativo VIGIA — nivel laranja em Cuiaba."
```

**Checkpoint Fase 7:**

- [ ] Template `alerta_vigia` criado (categoria Utilidade)
- [ ] Status **Aprovado** no WhatsApp Manager
- [ ] `WHATSAPP_TEMPLATE_NAME=alerta_vigia` no `.env`
- [ ] Teste proativo entregue no celular **sem** precisar mandar "oi" antes

---

## Fase 8 — Validar pelo painel (opcional)

Se o painel Streamlit estiver no ar:

1. Abra **Configurar WhatsApp** no menu lateral
2. Selecione **WhatsApp Cloud API (Meta, oficial)**
3. Preencha Phone number ID, Token e Destinatários
4. **Aplicar nesta sessão e diagnosticar**
5. **Verificar credenciais** (não envia mensagem)
6. **Enviar mensagem de teste**
7. Na aba **.env (pipeline local)**, baixe o bloco e cole na máquina do pipeline

> O painel **não grava** credenciais em disco. O `.env` da máquina do pipeline é a fonte de verdade
> para envio automático.

**Checkpoint Fase 8:**

- [ ] Diagnóstico verde no painel
- [ ] Teste de envio OK no painel
- [ ] Bloco `.env` copiado para a máquina do pipeline

---

## Fase 9 — Produção: alertas automáticos no pipeline

Quando o nível de alerta do estado **muda**, o pipeline dispara notificações:

```
sisclima/pipeline.py  →  change_detector.py  →  dispatch_alert()  →  WhatsApp
```

### 9.1 Disparo manual (teste de integração)

Na máquina local, com o `.env` configurado:

```bash
python -c "
from sisclima.alerts.notifier import dispatch_alert
r = dispatch_alert(
    '[SIS Clima-Saude] Mudanca de nivel: verde -> laranja',
    'Data: 2026-08-02\nNivel anterior: verde\nNovo nivel: laranja\n\nMotivos:\n- UTCI elevado em Cuiaba',
    {'nivel_anterior': 'verde', 'nivel_novo': 'laranja'}
)
print(r)
"
```

Esperado:

```python
{'email': False, 'telegram': False, 'whatsapp': True, 'webhook': False}
```

(Outros canais `True` se e-mail/Telegram também estiverem configurados.)

### 9.2 Disparo pelo app integrado

No `app.py` local, use o botão **▶ Rodar pipeline agora** com envio de alertas ativo.

### 9.3 Agendamento

Configure o agendador Windows (ou cron) apontando para o script de produção, conforme
[`OPERACAO.md`](OPERACAO.md).

### 9.4 Auditoria

Cada envio fica registrado na tabela `alertas_enviados` do SQLite (`data/output/sis_integrado.db`),
coluna `canais`, com o resultado por canal.

**Checkpoint Fase 9:**

- [ ] `dispatch_alert` retorna `whatsapp: True`
- [ ] Mensagem chega no celular configurado em `WHATSAPP_TO`
- [ ] Agendador do pipeline configurado
- [ ] Registro em `alertas_enviados` conferido

---

## Checklist final (imprima ou salve)

```
FASE 0  [ ] Decisão coexistência vs migração tomada
FASE 1  [ ] App Meta criado + produto WhatsApp
FASE 2  [ ] Teste com número de teste OK no celular
FASE 3  [ ] Número 99219-0039 vinculado na Meta
FASE 4  [ ] Número registrado na Cloud API
FASE 5  [ ] Token permanente gerado
FASE 6  [ ] .env de produção na máquina do pipeline
FASE 7  [ ] Template alerta_vigia aprovado
FASE 8  [ ] Painel validado (opcional)
FASE 9  [ ] Pipeline enviando alertas automaticamente
```

---

## Solução de problemas

### `Recipient phone number not in allowed list`

**Causa:** destinatário não está na lista **To** (número de teste) ou número de produção não
verificado.

**Correção:** cadastre o celular em **API Setup → To** (teste) ou use o número de produção já
registrado (Fase 3).

---

### `(#100) Invalid parameter` ou template não encontrado

**Causa:** `WHATSAPP_TEMPLATE_NAME` preenchido com nome que não existe ou ainda não foi aprovado.

**Correção:** remova `WHATSAPP_TEMPLATE_NAME` do `.env` para testar com texto livre (janela 24h),
ou aguarde aprovação do template.

---

### Mensagem aceita pela API mas não chega no celular

**Causa:** envio de texto livre fora da janela de 24h.

**Correção:**

1. Mande "oi" do celular para o número remetente (abre janela), **ou**
2. Configure template aprovado (Fase 7)

---

### `HTTP 401` ou token inválido

**Causa:** token expirado (temporário) ou revogado.

**Correção:** gere token permanente (Fase 5) e atualize `WHATSAPP_TOKEN`.

---

### `HTTP 400` no register

**Causa:** número já registrado ou PIN incorreto.

**Correção:** verifique status do número no WhatsApp Manager. Se já registrado, pule a Fase 4.

---

### App WhatsApp Business parou de sincronizar (coexistência)

**Causa:** app fechado por muito tempo ou desinstalado.

**Correção:** abra o app no celular; **não desinstale**. Abra pelo menos 1 vez a cada ~13 dias.

---

### `diagnostico` aponta variável ausente

**Correção:** compare com a tabela da Fase 6. Rode:

```bash
python -m sisclima.alerts.whatsapp_agent env --provedor meta_cloud
```

para gerar o bloco completo com todos os campos.

---

## Referência rápida — variáveis finais

```bash
# Produção completa (após todas as fases)
ALERT_WHATSAPP_ENABLED=true
WHATSAPP_PROVIDER=meta_cloud
WHATSAPP_PHONE_NUMBER_ID=<ID do +55 65 99219-0039>
WHATSAPP_TOKEN=<token permanente EAA...>
WHATSAPP_TO=65992190039
WHATSAPP_TEMPLATE_NAME=alerta_vigia
WHATSAPP_TEMPLATE_LANG=pt_BR
```

## Links oficiais

- [Meta for Developers — WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started)
- [Números de telefone comerciais](https://developers.facebook.com/docs/whatsapp/cloud-api/phone-numbers)
- [Registro de número](https://developers.facebook.com/docs/whatsapp/cloud-api/reference/registration/)
- [Preços por mensagem (Meta)](https://developers.facebook.com/docs/whatsapp/pricing/)
- [WhatsApp Manager (templates)](https://business.facebook.com/wa/manage/message-templates/)

---

## Próximo passo sugerido

Se você está na **Fase 1**, abra [developers.facebook.com](https://developers.facebook.com) e
crie o app. Quando terminar a Fase 2, volte aqui e continue na **Fase 3** para vincular o
**99219-0039**.

Para ajuda interativa a qualquer momento:

```bash
python -m sisclima.alerts.whatsapp_agent plano --provedor meta_cloud
python -m sisclima.alerts.whatsapp_agent diagnostico
```
