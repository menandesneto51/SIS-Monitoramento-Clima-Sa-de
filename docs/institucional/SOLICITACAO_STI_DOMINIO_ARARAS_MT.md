# Solicitação à STI — Reserva de domínio institucional ARARAS MT

**Destinatário:** Superintendência / Coordenação de Tecnologia da Informação (STI) — SES-MT (`sti@ses.mt.gov.br`)  
**Solicitante:** CIEVS-MT / Unidade de Informações Estratégicas de Vigilância em Saúde  
**Assunto:** Reserva e publicação de hostname institucional para a plataforma ARARAS MT  
**Sistema:** ARARAS MT — Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde  
**Data:** 10/08/2026  

---

## 1. Objetivo

Solicitar à STI a **reserva, configuração DNS e publicação** de hostname(s) sob o domínio institucional da SES-MT (`saude.mt.gov.br`) para:

1. o **site institucional** do ARARAS MT (conteúdo público / vitrine); e  
2. o **painel operacional** (sala de situação — acesso restrito à rede SES), quando implantado no servidor homologado.

O ambiente de protótipo atual **não** deve permanecer como URL oficial de produção.

---

## 2. Situação atual

| Ambiente | URL | Status |
|----------|-----|--------|
| Staging / protótipo de conteúdo | https://araras-mt.menandesneto.chatgpt.site/ | Referência visual e textual (não institucional SES) |
| Código estático no repositório | `sites/araras-mt/` | Pronto para servir como raiz estática |
| Painel Streamlit (interno) | porta **8501** no servidor SES | A implantar conforme documento técnico STI |
| Produção SES | **a reservar** | Objeto desta solicitação |

---

## 3. Hostnames solicitados

### 3.1 Preferência (produção)

| Hostname sugerido | Função | Exposição |
|-------------------|--------|-----------|
| **`araras.saude.mt.gov.br`** | Site institucional (estático) + ponto de entrada oficial | Internet e/ou rede SES, conforme política STI |
| **`araras-painel.saude.mt.gov.br`** *(opcional)* | Painel Streamlit / sala de situação | **Somente rede interna SES** (ou VPN), com autenticação institucional |

### 3.2 Alternativas aceitáveis

1. `araras.saude.mt.gov.br`  
2. `araras-mt.saude.mt.gov.br`  
3. `inteligencia.araras.saude.mt.gov.br`  

Pedimos à STI **confirmar o hostname definitivo** e registrá-lo no inventário de serviços da SES.

---

## 4. Arquitetura de publicação sugerida

```text
Internet / rede SES
        │
        ▼
  Reverse proxy STI (HTTPS, certificado institucional)
        │
        ├── araras.saude.mt.gov.br ────────► site estático (sites/araras-mt/)
        │
        └── araras-painel.saude.mt.gov.br ► Streamlit :8501  [rede interna]
                                              │
                                              └── Postgres (somente localhost / rede Docker)
```

### Requisitos técnicos mínimos

| Item | Solicitação |
|------|-------------|
| DNS | Registro A/CNAME para o(s) hostname(s) aprovado(s) |
| TLS | Certificado institucional (HTTPS obrigatório em produção) |
| Proxy | Terminação SSL no proxy STI; encaminhar ao host/serviço interno |
| Painel | Não expor a porta **8501** diretamente à internet |
| Banco | Porta **5432** somente localhost / rede Docker |
| Identidade | Cabeçalhos e título: **ARARAS MT** · assinatura *Clima, ambiente e saúde em uma só visão.* |

---

## 5. Conteúdo a publicar no site (`araras.saude.mt.gov.br`)

Servir a pasta versionada `sites/araras-mt/` como document root (nginx, IIS ou equivalente):

- Página institucional alinhada ao padrão SES (barra governo, logos SES/CIEVS/Rede CIEVS/Vigidesastres)
- Diferenciação **acesso público** × **acesso restrito**
- Módulos: Clima e eventos extremos (CE); Ambiente e qualidade do ar (AR); Agravos e saúde (AS); Resposta territorial (RT)
- CTA institucional para o SIEGES e links oficiais SES-MT

Enquanto o painel não estiver em produção, o CTA “Acessar a plataforma” pode apontar para `#acessos` / mensagem “Em implantação institucional”.

---

## 6. Segurança e governança

- Ambiente externo (ChatGPT Site / staging) **não** trata dados pessoais nem informações classificadas.  
- Produção oficial somente em infraestrutura homologada pela SES-MT.  
- Alertas e fan-out territorial permanecem sob liberação operacional do CIEVS.  
- Acesso restrito ao painel: autenticação institucional, menor privilégio e trilha de auditoria.

---

## 7. Entregáveis solicitados à STI

1. **Hostname(s) aprovado(s)** e data de ativação DNS/TLS  
2. Confirmação do **modo de publicação** do site estático (servidor web / CDN interno)  
3. Confirmação do **proxy HTTPS** para o painel interno (`:8501`)  
4. Contato técnico STI para acompanhamento da implantação  
5. Eventuais padrões de nomenclatura ou restrições de exposição externa

---

## 8. Contatos do solicitante

| Papel | Unidade | Contato |
|-------|---------|--------|
| Solicitante técnico / CIEVS | CIEVS-MT | `notifica@ses.mt.gov.br` · `cievs@ses.mt.gov.br` |
| Sistema / produto | ARARAS MT | Protótipo: https://araras-mt.menandesneto.chatgpt.site/ |

---

*Documento destinado à STI para reserva de domínio e publicação. Ajustes de naming devem seguir o padrão de nomenclatura da SES.*
