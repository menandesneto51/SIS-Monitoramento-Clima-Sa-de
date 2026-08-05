# Onde clicar na Meta — verificado na documentação oficial (2026)

Fonte oficial consultada em agosto/2026:

- [Get Started — WhatsApp Cloud API](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started) (atualizado 16/jun/2026)
- [Customize WhatsApp Use Case](https://developers.facebook.com/documentation/development/create-an-app/whatsapp-use-case) (atualizado 16/abr/2026)
- [Business phone numbers](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers) (atualizado 21/mai/2026)

Tutorial completo: [`TUTORIAL_WHATSAPP_META_CLOUD.md`](TUTORIAL_WHATSAPP_META_CLOUD.md)

---

## Por que você não achava “WhatsApp → API Setup”

Na interface **nova por casos de uso**, o menu lateral **não** traz um item `WhatsApp` solto.

A navegação correta é:

```
App (SIS Clima-Saude MT)
  └─ Casos de uso  ✏️  (ícone de lápis / "Use cases")
       └─ Conectar-se com clientes pelo WhatsApp  →  Personalizar
            └─ menu interno do caso de uso (Quickstart, API Setup, etc.)
```

A aba **Teste** que você viu **não** é a configuração da API — é só para validar permissões antes de publicar o app.

---

## Mapa oficial do menu (dentro do caso de uso WhatsApp)

Depois de clicar **Personalizar** no caso de uso WhatsApp, a Meta lista estas opções:

| Opção no menu | Para que serve | Você precisa? |
|---|---|---|
| **Permissions and features** | Permissões do app (`whatsapp_business_messaging`, etc.) | Conferir — já vêm 3 obrigatórias |
| **Quickstart** | Início rápido + botão **Começar a usar a API** | **SIM — comece aqui** |
| **API Setup** | Token, Phone number ID, enviar/receber mensagens | **SIM — tela principal** |
| **Configuration** | Webhooks, token permanente (link doc) | Depois (opcional para alertas simples) |
| **Resources** | Links de documentação | Consulta |
| **Tech Provider onboarding** | Virar provedor para terceiros | **NÃO** — ignore |
| **Partner Solutions** | Soluções de parceiro | **NÃO** — ignore |
| **Embedded Signup Builder** | Cadastro embutido em site | **NÃO** — ignore |

---

## Passo a passo verificado (clique a clique)

### 1. Abrir o app

[developers.facebook.com/apps](https://developers.facebook.com/apps) → selecione **SIS Clima-Saude MT** (ou `- Test1`).

### 2. Entrar no caso de uso WhatsApp

**Opção A (documentação oficial):**

1. Menu esquerdo → **Casos de uso** (ícone de **lápis** / “Use cases”)
2. Card **Conectar-se com clientes pelo WhatsApp**
3. Botão **Personalizar** / **Customize**

**Opção B (se já estiver no Painel):**

1. Menu esquerdo → **Painel**
2. Card WhatsApp → **Personalizar**

### 3. Abrir Quickstart

No menu **interno** do caso de uso (não o menu geral do app):

```
Quickstart  →  Início rápido
```

### 4. Clicar no botão oficial

Na página Quickstart, clique:

```
Começar a usar a API
```

(em inglês: **Start using the API**)

> A documentação da Meta diz explicitamente: este botão **redireciona para a página API Setup**.

### 5. Na API Setup — o que fazer

| Bloco na tela | Ação |
|---|---|
| **Conectar conta WhatsApp Business** | Selecione conta existente ou **Criar conta WhatsApp Business** |
| **WhatsApp Business Account ID** | Anote (WABA ID) |
| **Access Token** | **Gerar token de acesso** → copie `EAA...` (24h) |
| **From** | Número de **teste** gratuito (Meta cria automaticamente) |
| **Phone number ID** | Anote — vai em `WHATSAPP_PHONE_NUMBER_ID` |
| **To** | Adicione **+55 65 99219-0039** e confirme código |
| **Send message** | Envie primeira mensagem de teste |

### 6. Permissões obrigatórias (já devem estar no app)

Conferir em **Permissions and features**:

| Permissão | Obrigatória |
|---|---|
| `public_profile` | Sim |
| `whatsapp_business_management` | Sim |
| `whatsapp_business_messaging` | Sim |
| `business_management` | Opcional (útil para script `descobrir`) |

---

## O que IGNORAR (não é para o VIGIA)

| Tela / botão | Motivo |
|---|---|
| **Teste** (aba geral do app) | Só valida permissões; não configura WhatsApp |
| **Torne-se um Provedor de Tecnologia** | Para empresas que vendem API a clientes |
| **Tech Provider onboarding** | Idem |
| **Partner Solutions** | Parceiros BSP |
| **Embedded Signup Builder** | Integração em site de terceiros |
| **Publicar o app** | Não necessário para testes iniciais |
| **Verificação do negócio** | Necessária depois, para produção em escala |

---

## Vincular o número real +55 65 99219-0039 (já no WhatsApp Business)

### Caminho 1 — Pela API Setup (dentro do caso de uso)

Na **API Setup**, item 5 da documentação:

> *Add and verify a phone number people will see when they chat with you*

1. **Add phone number** / **Adicionar número**
2. País Brasil (+55) → **65 99219-0039**
3. Se aparecer: **Conectar WhatsApp Business App** (coexistência — mantém app no celular)
4. Verifique por SMS/ligação
5. Anote o **novo Phone number ID** (diferente do teste)

### Caminho 2 — Pelo WhatsApp Manager

1. [business.facebook.com/latest/whatsapp_manager](https://business.facebook.com/latest/whatsapp_manager)
2. **Ferramentas da conta → Números de telefone**
3. **Adicionar número de telefone**
4. Siga verificação

### Registrar na Cloud API (obrigatório)

Adicionar o número **não basta**. Depois de verificado, registre:

```bash
curl -X POST "https://graph.facebook.com/v23.0/<PHONE_NUMBER_ID>/register" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"messaging_product": "whatsapp", "pin": "123456"}'
```

O `pin` de 6 dígitos é **definido por você** na hora do registro.

---

## Token permanente (produção)

Documentação oficial — Passo 5 do Get Started:

1. [business.facebook.com](https://business.facebook.com) → **Configurações do negócio**
2. **Usuários do sistema** → **Adicionar**
3. **Atribuir ativos** → app + conta WhatsApp (controle total)
4. **Gerar token** com permissões:
   - `business_management`
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`

---

## Se ainda não achar o menu — alternativa oficial

### Explorador da Graph API

[developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer)

1. App: **SIS Clima-Saude MT**
2. Permissões: `whatsapp_business_messaging`, `whatsapp_business_management`, `business_management`
3. **Gerar token**

Depois, no SIS:

```bash
python -m sisclima.alerts.whatsapp_agent descobrir --token EAA...
```

---

## Checklist visual — onde você está

```
[ ] App criado (SIS Clima-Saude MT)                    ← você já fez
[ ] Casos de uso → WhatsApp → Personalizar             ← PRÓXIMO PASSO
[ ] Quickstart → "Começar a usar a API"                ← abre API Setup
[ ] API Setup → token + Phone number ID + To           ← anotar credenciais
[ ] .env no SIS + comando testar                       ← integração
[ ] Adicionar 99219-0039 + registrar                   ← produção
[ ] Template alerta_vigia aprovado                     ← alertas automáticos
```

---

## `.env` mínimo após API Setup

```bash
ALERT_WHATSAPP_ENABLED=true
WHATSAPP_PROVIDER=meta_cloud
WHATSAPP_PHONE_NUMBER_ID=<da tela API Setup>
WHATSAPP_TOKEN=<EAA... token permanente ou temporário para teste>
WHATSAPP_TO=65992190039
```

Teste:

```bash
python -m sisclima.alerts.whatsapp_agent diagnostico
python -m sisclima.alerts.whatsapp_agent testar
```

Antes do teste com número de teste: mande **"oi"** do celular para o número **From** (janela 24h).
