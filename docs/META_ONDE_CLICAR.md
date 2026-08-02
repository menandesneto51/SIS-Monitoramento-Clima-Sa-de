# Onde clicar na Meta (interface 2026) — caminho alternativo

Se você **não encontra** `WhatsApp → API Setup` no menu lateral, a Meta mudou o fluxo.
Este guia usa a **interface atual por casos de uso** (como no app `SIS Clima-Saude MT - Test1`).

Documento principal: [`TUTORIAL_WHATSAPP_META_CLOUD.md`](TUTORIAL_WHATSAPP_META_CLOUD.md)

---

## Caminho A — Botão “Começar a usar a API” (preferido)

A Meta redireciona apps novos para **Quickstart**, não para API Setup direto.

### Passos

1. Abra [developers.facebook.com/apps](https://developers.facebook.com/apps)
2. Selecione o app **SIS Clima-Saude MT** (ou `- Test1`)
3. Menu esquerdo → **Painel** (não **Teste**)
4. Na página, localize o card:

   ```
   Conectar-se com clientes pelo WhatsApp
   ```

5. Clique em **Personalizar** ou no próprio card
6. Você entra em:

   ```
   Personalizar caso de uso → WhatsApp → Início rápido (Quickstart)
   ```

7. Clique no botão azul:

   ```
   Começar a usar a API
   ```
   
   (em inglês: **Start using the API**)

8. **Só então** aparece a tela com:
   - Token de acesso
   - Phone number ID
   - Número de teste (From)
   - Lista **To** (destinatários)

> Se você parou na aba **Teste** com “0 chamadas de API”, volte ao **Painel** e siga os passos 4–7.

---

## Caminho B — Pelo Meta Business Suite

1. Abra [business.facebook.com](https://business.facebook.com)
2. **Configurações do negócio** (engrenagem)
3. **Contas → Aplicativos**
4. Localize **SIS Clima-Saude MT** → **Abrir no Painel do app**
5. Repita o **Caminho A** a partir do passo 4

---

## Caminho C — Explorador da Graph API (sem achar API Setup)

Use quando a interface do app não mostra Phone number ID.

### C1. Gerar token

1. Abra [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer)
2. **App da Meta:** selecione `SIS Clima-Saude MT`
3. **Permissões** → adicione:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
   - `business_management`
4. **Gerar token de acesso** → copie o `EAA...`

### C2. Descobrir IDs automaticamente (SIS)

Na máquina com o repositório:

```bash
export WHATSAPP_TOKEN=EAA...cole_aqui...
python -m sisclima.alerts.whatsapp_agent descobrir
```

O comando lista contas WhatsApp Business e Phone number IDs encontrados e gera um bloco `.env`.

### C3. Consulta manual (opcional)

No Explorador da Graph API, com o token gerado:

```
GET /me/businesses?fields=id,name,owned_whatsapp_business_accounts{id,name}
```

Anote o `id` da conta WhatsApp (WABA). Depois:

```
GET /<WABA_ID>/phone_numbers
```

O campo `id` de cada número é o **Phone number ID**.

---

## Caminho D — WhatsApp Manager (número real depois)

Para vincular o **+55 65 99219-0039** (produção):

1. [business.facebook.com/latest/whatsapp_manager](https://business.facebook.com/latest/whatsapp_manager)
2. **Ferramentas da conta → Números de telefone**
3. **Adicionar número de telefone**
4. Escolha **Conectar WhatsApp Business App** (coexistência), se disponível
5. Verifique por SMS/ligação

O Phone number ID desse número aparece no **Caminho A** (API Setup) ou no **Caminho C** (`descobrir`).

---

## Mapa visual — onde você está vs onde precisa ir

```
Onde você está (print)          Onde precisa chegar
─────────────────────          ────────────────────
Painel → Teste                   Painel → Personalizar WhatsApp
  └─ Graph API Explorer            └─ Quickstart
  └─ 0 chamadas API                  └─ [Começar a usar a API]
                                         └─ Token + Phone number ID + To
```

---

## Depois de obter token e Phone number ID

1. Crie o `.env` na raiz do projeto (veja abaixo)
2. Cadastre **+55 65 99219-0039** em **To** (se usar número de teste)
3. Mande **"oi"** do celular para o número de teste (janela 24h)
4. Rode:

```bash
python -m sisclima.alerts.whatsapp_agent diagnostico
python -m sisclima.alerts.whatsapp_agent testar
```

Bloco mínimo:

```bash
ALERT_WHATSAPP_ENABLED=true
WHATSAPP_PROVIDER=meta_cloud
WHATSAPP_PHONE_NUMBER_ID=<do comando descobrir ou da tela>
WHATSAPP_TOKEN=<EAA...>
WHATSAPP_TO=65992190039
```

---

## Ainda travado?

Envie **uma** destas informações:

1. Print da tela **Painel** (não Teste) após clicar no card WhatsApp, **ou**
2. Saída do comando:

```bash
python -m sisclima.alerts.whatsapp_agent descobrir --token EAA...primeiros_chars...
```

(com token parcialmente mascarado)

Com isso montamos o `.env` exato sem depender da API Setup.
