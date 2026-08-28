# ARARAS como fonte oficial do Plano El Niño 2026–2027

O ARARAS deixa de ser só painel climático e passa a ser o **repositório operacional** do Plano. A área atualiza a ação, anexa a evidência e o sistema calcula o indicador. E-mail e WhatsApp **não guardam** a informação: só avisam e cobram.

Base imediata: planilha `Controle_Indicacoes_El_Nino_SES_MT_2026.xlsx` (40 ações originais, **88 indicadores** ARARA-001 a ARARA-088).

| Classe | Quantidade |
| --- | --- |
| Automático | 43 |
| Semiautomático | 36 |
| Manual com evidência | 9 |
| Execução | 24 |
| Capacidade/prontidão | 25 |
| Resultado | 23 |
| Risco/gatilho | 16 |

Risco/gatilho **não conta como meta cumprida**. Sinaliza agravamento e dispara análise.

---

## 1. Princípio

```
área atualiza o ARARAS
  → ARARAS calcula
  → CIEVS valida
  → ARARAS consolida
  → ARARAS gera painel
  → ARARAS gera briefing da Sala
  → ARARAS dispara e-mail
```

Hoje: planilha → e-mail → consolidação manual no CIEVS.  
Aqui: a consolidação é o próprio sistema.

Fluxo de uma ação:

**Plano → responsável → notificação → atualização pela área → evidência → validação → cálculo → painel → cobrança/escalonamento.**

Exemplo: “Atualizar planos de contingência das unidades hospitalares”, Gestão Hospitalar, prazo 30/09/2026.

- Área informa 15 de 20.
- ARARAS calcula 75% → 🟡 em andamento, 5 pendentes.
- 20/20 → 🟢 100% meta atingida, após validação do CIEVS.

---

## 2. Dois ambientes

**Público** — o que já existe e pode ser ampliado: cenário climático, classificação territorial, alertas, recomendações, mapas, relatórios e indicadores agregados **autorizados**.

**Restrito — Sala de Situação** — gestão do Plano. Login individual. Cada área só edita o que é dela. Assistência Farmacêutica não altera indicador da Vigilância Sanitária.

Perfis (sobre o cadastro que o ARARAS já tem: público / municipal / regional / SES / admin):

| Perfil | Papel |
| --- | --- |
| Administrador ARARAS | Sistema, usuários, parâmetros |
| Secretaria-executiva / CIEVS | Plano, prazos, validação oficial |
| Coordenador da área | Atualiza e encaminha da própria `area_id` |
| Técnico da área | Insere dados, comentários e documentos da `area_id` |
| Gestor | Lê o Plano inteiro e as decisões |
| Consulta | Somente leitura |

Autenticação: preferir login institucional SES/MT (STI). Enquanto isso: e-mail institucional + senha + 2FA.

A planilha de **indicações** (Portaria 0590, titulares/suplentes) entra no mesmo ambiente como cadastro da Sala — não mistura com o motor de 88 indicadores.

---

## 3. E-mail = comunicação; ARARAS = dado

O e-mail leva a pessoa **para a ação** (`ARARAS-016`), não para uma planilha.

| Evento | Canal |
| --- | --- |
| Nova ação atribuída | E-mail |
| 15 / 7 / 3 dias para vencer | E-mail |
| Prazo vencido | E-mail + destaque no sistema |
| Evidência enviada | Aviso ao CIEVS |
| Evidência rejeitada | Área corrige |
| Meta atingida | Registro automático |
| Indicador crítico | Alerta ao grupo |
| Crítica vencida | Escalonamento à gestão |

WhatsApp, se autorizado depois, só para alerta curto. SEI continua sendo o processo administrativo oficial.

---

## 4. Tela da ação (o que a área preenche)

A área **não calcula** o percentual. Informa situação, numerador/denominador, texto, pendência, previsão e evidências.

Situações: não iniciada, em andamento, em validação, concluída, impedida, suspensa, não aplicável.

Evidências: relatório, planilha, nota técnica, ofício, ata, foto, **link SEI**.

Botão: **Enviar para validação**.

Cada arquivo fica preso a `Plano → Eixo → Meta → Ação → Indicador → Atualização`, com tipo, número, data, área, versão, autor, timestamp, situação e protocolo SEI.

SEI não é substituído: processo e documento oficiais ficam no SEI; o ARARAS guarda o vínculo + PDF opcional.

---

## 5. Três modos de indicador

**Automático** — o ARARAS busca e calcula (estoque ÷ consumo = autonomia; PM2,5 + SRAG + calor + focos). Integrações: DW SES, SINAN, SIH, CNES, SISAGUA, LACEN/GAL, meteorologia, queimadas, qualidade do ar, regulação.

**Semiautomático (maioria no começo)** — o catálogo já sabe o denominador (16 ERS). A área informa 14. O sistema faz 14/16 = 87,5% e “faltam 2 ERS”.

**Manual/documental** — “Nota Técnica publicada?” exige Sim **e** documento + data + responsável. Vai para 🟠 em validação até o CIEVS validar.

---

## 6. Validação e histórico

Ninguém marca 100% e isso cai sozinho no relatório executivo.

`Não informado → Informado → Em validação → Validado` ou `Rejeitado / correção`.

Cada atualização é uma linha nova. 60% não some quando entra 80%. Isso alimenta o gráfico de implementação e a auditoria (quem, quando, o quê).

---

## 7. Quatro módulos restritos + alertas

| Módulo | Função |
| --- | --- |
| Plano de Ação | ações, metas, responsáveis, prazos |
| Indicadores | os 88, cálculo e semáforo |
| Evidências | documentos, SEI, atas, fotos |
| Pendências e decisões | deliberações da Sala (`SS-2026-038`) |
| Alertas | motor que já existe no ARARAS (e-mail agora; WhatsApp depois) |

Painel da Sala (exemplo de leitura, não números desta rodada):

- implementação geral
- concluídas / em andamento / vencidas / sem informação
- cumprimento por eixo
- pendências críticas, riscos ativos, dados faltantes

Antes da reunião, o ARARAS gera o **briefing de 1 página**. Depois, a decisão entra no módulo de decisões e passa a ser cobrada como ação.

---

## 8. Arquitetura técnica (encaixe no que já existe)

```
Usuário da área
  → portal restrito ARARAS (Streamlit + perfis)
  → formulário da ação / evidência
  → PostgreSQL (tabelas plano_*)
  → motor de indicadores (sisclima.engines.plano_el_nino)
  → regras de prazo e semáforo
  → validação CIEVS
  → dashboard Sala
  → e-mail (sisclima.alerts.notifier)
  → briefing

Paralelo: DW + APIs oficiais → ETL → indicadores automáticos
```

Artefatos neste repositório:

| Arquivo | Função |
| --- | --- |
| `config/plano_el_nino_matriz.yaml` | catálogo oficial (importado da planilha) |
| `scripts/importar_matriz_plano_el_nino.py` | republica o catálogo quando a planilha mudar |
| `sql/sala_situacao_plano.sql` | ações, indicadores, evidências, decisões, auditoria |
| `sisclima/engines/plano_el_nino.py` | cálculo de progresso e semáforo |

O que **não** se faz nesta etapa: tela Streamlit completa, SSO da STI, WhatsApp institucional. O cadastro de usuários e o disparo de e-mail já existem; o próximo passo de produto é a tela da ação + validação CIEVS.

---

## 9. Ordem de implantação

1. Importar a matriz e congelar os 88 IDs.
2. Subir as tabelas `plano_*` e o recorte por `area_id`.
3. Semiautomático + evidência + validação CIEVS (o que tira o e-mail do caminho crítico).
4. Painel da Sala e briefing automático.
5. Indicadores automáticos já cobertos pelo ARARAS (clima, ar, focos, água quando SISAGUA/DW estiver estável).
6. SSO SES/MT e, se a gestão autorizar, WhatsApp só como alerta.
