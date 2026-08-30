# Tutorial operacional — Painel restrito, Eventos e Sala de Situação (ARARAS MT)

**Versão:** 1.1 — agosto/2026 (revisão pós-validação CIEVS)  
**Público:** participantes da Sala de Situação (Portaria nº 0590/2026/GBSES), CRS/SMS e CIEVS-MT  
**Produto:** ARARAS MT — Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde  
**Contato CIEVS:** notifica@ses.mt.gov.br · menandesneto@ses.mt.gov.br

Este guia detalha a **logística da Sala**: (1) entrar no painel restrito, (2) notificar e triar eventos de campo e (3) informar, validar e comunicar os indicadores do Plano El Niño.

**Regra de ouro:** o ARARAS MT é o **registro oficial**. E-mail e WhatsApp só avisam e cobram — não substituem o preenchimento no painel. O SEI continua sendo o processo administrativo oficial; o ARARAS guarda o vínculo e o dado operacional.

---

## 1. Visão da logística (quem faz o quê)

### 1.1 Papéis na cadeia

| Etapa | SMS / CRS / área SES | CIEVS / secretaria-executiva |
|-------|----------------------|------------------------------|
| Cadastro | Solicita acesso restrito | Aprova ou eleva nível (ses/admin) |
| Evento de campo | Notifica na aba Eventos | Tria (confirma, encerra ou descarta) |
| Indicador do Plano | Informa numerador / documental + SEI | Valida ou rejeita; atualiza automáticos |
| Comunicação | Lê cobrança da própria área | Emite briefing, cobrança e boletim |

### 1.2 Três ambientes do ARARAS

| Ambiente | Quem acessa | O que encontra |
|----------|-------------|----------------|
| Público | Qualquer pessoa (sem login) | Cenário climático, mapas e indicadores agregados autorizados — sem evidências nem documentos |
| Restrito (painel interno) | Conta municipal, regional, ses ou admin | Eventos em saúde, operações e, se ses/admin, a Sala |
| Sala de Situação | Nível **ses** ou **admin** + vínculo do Plano | Briefing, 88 indicadores ARARA, cobrança, validação CIEVS, acessos Portaria 0590 |

### 1.3 O que NÃO é este tutorial

- Não substitui a Portaria 0590 nem ofícios da SES.
- Não ensina o SINAN, o SEI nem o IndicaSUS — só o ponto de entrada no ARARAS.
- Alertas climáticos multinível (e-mail/Telegram do digest) são um **canal separado** dos indicadores ARARA da Sala.

---

## 2. Acesso ao painel restrito

### 2.1 Abrir o painel

1. Acesse a URL do ARARAS MT informada pelo CIEVS/STI (homologação ou produção).
2. No topo da página, clique em **Acesso restrito**.
3. Escolha a aba **Entrar** (já tem conta) ou **Cadastrar** (primeira vez).

### 2.2 Primeiro cadastro — passo a passo

1. Abra a aba **Cadastrar**.
2. Escolha o **nível solicitado**. Não existe autoatribuição de administrador:
   - **Municipal** — SMS: selecione o município; o sistema associa a Regional de Saúde.
   - **Regional** — CRS / escritório regional: selecione a Regional de Saúde.
   - **SES** — área da Secretaria ou CIEVS (**obrigatório** para abrir a Sala de Situação).
3. Preencha:
   - nome completo;
   - **e-mail institucional** (preferencialmente @ses.mt.gov.br ou domínio da SMS/CRS);
   - instituição (ex.: SAF, COVAM, SMS Cuiabá, CRS Sinop);
   - senha com no mínimo **8 caracteres** (e confirmação).
4. Clique em **Enviar cadastro**.
5. Em muitos casos o status fica **pendente** até o CIEVS ou um admin aprovar. Sem aprovação, o login pode ser recusado.

**Dica:** use o mesmo e-mail da lista da Sala (Portaria 0590). Isso facilita o vínculo de área depois.

### 2.3 Entrar (conta já existente)

1. Aba **Entrar**.
2. **Hoje:** e-mail + senha locais do ARARAS.
3. **Futuro (STI):** botão **Entrar com conta SES / STI** (OpenID), quando a STI publicar o issuer — a conta entra como ses; o `area_id` do Plano continua no vínculo interno até o SSO trazer o setor.
4. Após login interno, clique em **Painel interno** para ver as abas operacionais (Eventos, Sala, etc.).
5. Para voltar à visão agregada, use a opção de painel público (quando disponível na barra de acesso).

### 2.4 Quem vê o quê após o login

| Nível do painel | Eventos em saúde | Sala de Situação / Plano El Niño |
|-----------------|------------------|----------------------------------|
| Sem login (público) | Não | Não |
| Municipal | Sim — só o próprio município | Não |
| Regional | Sim — municípios da CRS | Não |
| **ses** ou **admin** | Sim — visão estadual | **Sim** |

Além do nível do painel, o **perfil do Plano** (tabela de vínculo) define a edição:

| Perfil do Plano | Pode fazer |
|-----------------|------------|
| Secretaria-executiva CIEVS | Validar indicadores, atualizar automáticos, gerar cobrança, gerir acessos |
| Coordenador da área | Informar e encaminhar indicadores da própria `area_id` |
| Técnico da área | Informar dados e evidências da própria `area_id` |
| Gestor / consulta | Ler briefing e filas; não grava evidência de outra área |

**Isolamento entre áreas:** Assistência Farmacêutica não edita indicador da Vigilância Sanitária (e o inverso). Tentativa de gravar outra área é recusada pelo sistema.

### 2.5 Aba Acessos (só CIEVS / admin, dentro da Sala)

Na Sala → aba **Acessos**, o CIEVS confere:

- capacidade da sessão atual (nível, se abre Sala, se valida);
- participantes catalogados da Portaria 0590;
- municípios estratégicos × e-mail SMS (COSEMS);
- vínculos ativos do Plano;
- botões para **aplicar catálogo** e **gravar vínculo** (e-mail + perfil + área).

### 2.6 Problemas comuns de acesso

| Sintoma | Causa provável | O que fazer |
|---------|----------------|-------------|
| Cadastro enviado e não entra | Status pendente | Pedir aprovação ao CIEVS (notifica@ses.mt.gov.br) |
| Entrou mas não vê a Sala | Nível municipal/regional | Solicitar elevação para **ses** (áreas da SES) |
| Vê a Sala mas não edita | Sem `plano_vinculo` / área | CIEVS aplica catálogo ou grava vínculo na aba Acessos |
| Mensagem de área errada | Isolamento por `area_id` | Usar conta da área correta ou pedir vínculo |
| Esqueceu a senha | Conta local | Contatar CIEVS para redefinição |
| Login STI indisponível | OIDC ainda não publicado | Usar e-mail + senha locais |

---

## 3. Notificação de eventos em saúde

**Menu:** Painel interno → **Eventos em saúde**.  
**Finalidade:** rumor, cluster ou impacto climático no território.  
**Limites:** **não substitui o SINAN**; **proibido** informar nome, CPF, prontuário ou qualquer dado identificável de paciente.

### 3.1 Quem pode notificar e quem tria

| Ação | Níveis |
|------|--------|
| Notificar | municipal, regional, ses, admin |
| Triar (mudar situação) | ses, admin |

Recortes automáticos:

- conta **municipal** — só o próprio município;
- conta **regional** — só municípios da própria CRS;
- conta **ses/admin** — estado.

### 3.2 Tipos de evento disponíveis no formulário

| Código interno | Rótulo na tela |
|----------------|----------------|
| calor | Calor extremo / desidratação |
| fumaca_ar | Fumaça / qualidade do ar |
| estiagem_agua | Estiagem / abastecimento de água |
| fogo_queimada | Incêndio / queimada |
| inundacao | Inundação / alagamento |
| surto_agravo | Surto / aumento de agravo |
| rumor | Rumor / sinal precoce |
| outro | Outro evento de saúde pública |

### 3.3 Situações da fila (triagem)

| Situação | Significado operacional |
|----------|-------------------------|
| Rumor | Recém-notificado; aguarda verificação |
| Em verificação | CIEVS/CRS apurando |
| Confirmado | Evento reconhecido; acompanhar |
| Encerrado | Ciclo concluído |
| Descartado | Sem confirmação / fora de escopo |

### 3.4 Passo a passo — notificar (SMS, CRS ou SES)

1. Abra **Eventos em saúde** → aba **Notificar**.
2. Selecione o **município**.
3. Escolha o **tipo** e a **data do evento**.
4. Opcional: número aproximado de afetados; território tradicional/local (aldeia, quilombo, comunidade, bairro); código COBRADE.
5. No campo **O que está acontecendo**, descreva fatos, local, duração e serviços afetados.  
   Mínimo técnico: **20 caracteres**. Sem identificação de paciente.
6. Opcional: link de ofício, foto ou decreto.
7. Clique em **Registrar evento**.
8. Anote o **protocolo** (código curto gerado pelo sistema) para acompanhamento.

**Exemplos do que escrever:** “Posto de saúde X com 12 atendimentos por desidratação em 48 h; Tmáx relatada alta; sem ruptura de estoque de SRO.”  
**Exemplos do que NÃO escrever:** nome de paciente, CPF, leito, prontuário.

### 3.5 Passo a passo — triagem (CIEVS)

1. Aba **Fila de triagem**.
2. Leia os cartões-resumo: rumor · em verificação · confirmados · total no recorte.
3. Selecione o **protocolo**.
4. Escolha a **nova situação** e, se útil, a nota de triagem.
5. Clique em **Atualizar situação**.
6. Use a aba **Mapa** para ver distribuição territorial (quando houver coordenadas no recorte).

Quem não é ses/admin vê a fila do próprio recorte, mas **não** altera a situação.

### 3.6 Como o evento alimenta a logística da Sala

1. Campo (SMS/CRS) notifica o evento.
2. CIEVS tria até confirmado, encerrado ou descartado.
3. Se houver impacto estadual / El Niño:
   - cruzar com o **Briefing** da Sala e o mapa de risco do painel;
   - acionar áreas (SAF, COVAM, COVSAN, imunização, etc.) na reunião ou via cobrança;
   - se existir indicador ARARA correspondente, a **área** atualiza o indicador (seção 4).

**Importante:** o evento de campo **não** altera sozinho o percentual ARARA. Indicador automático só muda quando a fonte do pipeline tem dado; semiautomático/documental exige preenchimento da área.

---

## 4. Indicadores da Sala de Situação (Plano El Niño)

**Menu:** Painel interno → **Sala de Situação / Plano El Niño**.  
**Base normativa:** Portaria nº 0590/2026/GBSES.  
**Catálogo:** ARARA-001 a ARARA-088.  
**Atenção:** indicadores de **risco/gatilho** sinalizam agravamento e **não** entram como meta cumprida no índice de implementação.

### 4.1 Abas da Sala — o que cada uma resolve

| Aba | Para quem | Conteúdo |
|-----|-----------|----------|
| Briefing | Todos com acesso à Sala | % implementação bruta, se o índice oficial está completo, pendentes, vencidas, eixos, papéis (operacional / prontidão / gatilho), botão de automáticos |
| Indicadores | Área + CIEVS | Quadro completo; formulário **Informar dado** |
| Cobrança | CIEVS e coordenadores | PDF/CSV, rascunhos por área, quem falta informar |
| Ações | Área (filtrada) / CIEVS | Lista de ações do catálogo com prazo e responsável |
| Validação CIEVS | Secretaria-executiva / admin | Fila `em_validacao` → validar ou rejeitar |
| Acessos | CIEVS / admin | Catálogo Portaria, vínculos, municípios estratégicos |

### 4.2 Classes e modos (como a área deve agir)

| Modo | Quantidade aproximada no desenho | O que a área faz | O que o ARARAS faz |
|------|----------------------------------|------------------|--------------------|
| Automático | ~43 | Em geral **não digita** | Lê DW/pipeline; CIEVS clica **Atualizar indicadores automáticos** |
| Semiautomático | ~36 | Informa **realizado** (numerador) e confirma **previsto** (denominador) | Calcula o % (ex.: 15/16 = 93,8%; faltam 2) |
| Documental | ~9 | Marca Sim/Não + descrição (SEI, NT, ata) | Envia à validação; 100% só após CIEVS |

A área **nunca calcula o percentual**. Informa o dado bruto; o sistema calcula e o CIEVS valida.

**Exemplos por modo**

- Semiautomático: “planos de contingência em 15 de 16 ERS” → informar 15 e 16.
- Documental: “Nota Técnica publicada?” → Sim + número/link SEI.
- Automático: ocupação/estoque/qualidade do ar vindos das tabelas da rotina — se a fonte estiver vazia, fica **aguardando fonte** (não vira zero inventado).

### 4.3 Status possíveis de uma ação / leitura

| Status | Significado |
|--------|-------------|
| não iniciada | Sem atualização gravada |
| em andamento | Há informação parcial |
| em validação | Área enviou; aguarda CIEVS |
| concluída | Meta atingida e validada (quando aplicável) |
| impedida / suspensa / não aplicável | Situações excepcionais registradas no Plano |

Cadeia de validação da leitura:

**não informado → informado → em validação → validado** ou **rejeitado**.

Histórico é **append-only**: rejeição não apaga o passado; a área reenvia nova linha.

### 4.4 Passo a passo — área atualiza um indicador

1. Entre com conta **ses** e confirme o vínculo da sua área (caption no topo da Sala: perfil + área).
2. Abra **Sala de Situação / Plano El Niño**.
3. (Opcional) Aba **Cobrança** — localize o ID ARARA pendente da sua área e o e-mail focal.
4. Aba **Indicadores** → seção **Informar dado (a área não calcula o %)**.
5. Selecione o indicador da lista (só aparecem os **editáveis da sua área**).
6. Se o ARARAS mostrar **sugestão**, leia com atenção: o valor sugerido **ainda não está gravado**.
7. Preencha:
   - semiautomático: **Realizado (numerador)** e **Previsto (denominador)** + texto “o que mudou”;
   - documental: **Sim/Não** + descrição da evidência (SEI, NT, ata…).
8. Clique em **Calcular e enviar à validação CIEVS** (ou **Registrar e enviar à validação CIEVS** no documental).
9. Confirme a mensagem de sucesso. O indicador fica **em validação**.
10. Guarde o protocolo SEI correspondente ao processo oficial.

Se a lista de editáveis estiver vazia: ou não há pendência da sua área, ou o vínculo de área está ausente/errado (seção 2.6).

### 4.5 Passo a passo — CIEVS valida

1. Aba **Validação CIEVS**.
2. Se a fila estiver vazia, não há leituras `em_validacao`.
3. Revise a tabela (id, nome, numerador/denominador, %).
4. Selecione a **atualização** na lista (id interno + código do indicador + valor).
5. Escolha **validado** ou **rejeitado**.
6. Preencha a **nota** (obrigatória na prática: motivo da rejeição ou referência SEI da validação).
7. Clique em **Registrar validação**.

Efeitos:

- **validado** — entra no consolidado / índice oficial quando o indicador participa do índice;
- **rejeitado** — a área corrige e reenvia.

**100% oficial** no Briefing só ocorre quando todos os itens do índice estão concluídos **e** validados. Sem preenchimento das áreas, a implementação bruta permanece **0%**.

### 4.6 Automáticos (CIEVS / admin)

1. Aba **Briefing**.
2. Clique em **Atualizar indicadores automáticos (tabelas do pipeline)**.
3. Leia o retorno: gravados · inalterados · aguardando fonte · erros.
4. Fontes já ligadas à rotina incluem, entre outras: resumo municipal, SINAN/arboviroses, CNES, estoque, qualidade do ar, comunicação, infraestrutura e cadastro Portaria (IND-001). Tabelas ainda vazias (ex.: SISAGUA, entomologia, denúncias) permanecem aguardando depósito da área.

### 4.7 Cobrança, boletim e alertas (comunicação externa)

| Produto | Onde nasce | Como sai | Observação |
|---------|------------|----------|------------|
| PDF/CSV de cobrança | Aba Cobrança + rotina diária | Download / rascunhos por área | E-mail de cobrança **não dispara sozinho** |
| Boletim El Niño apresentável | Geração CIEVS (v10.x) | E-mail à lista da Sala | Nome oficial: **Boletim Informativo Sala de Situação MT El Niño SE XX-AAAA.pdf** |
| Alertas climáticos multinível | Digest ARARAS | ALERT_EMAIL_TO + Telegram | Canal SES; fan-out municipal só com contatos aprovados |

**Lista operacional atual do boletim da Sala:** participantes com e-mail no catálogo + rede-cievs-mt-e-ers@ses.mt.gov.br + COSEMS-MT (cosems@cosemsmt.org). E-mails **individuais** dos 16 escritórios regionais ainda podem estar pendentes — até lá usa-se a lista agregada da Rede CIEVS/ERS.

Script de apoio (equipe CIEVS): `scripts/enviar_boletim_sala.py` com `--dry-run`, `--teste-cievs` ou `--enviar`.

---

## 5. Ritual semanal sugerido da Sala

| Momento | Responsável | Ações concretas |
|---------|-------------|-----------------|
| 24–48 h antes | CIEVS | Atualizar automáticos; gerar cobrança; limpar fila de validação; revisar eventos confirmados |
| 24–48 h antes | Áreas | Preencher semiautomáticos/documentais pendentes; anexar/linkar SEI |
| Na reunião | Sala | Abrir Briefing; confrontar mapa de risco e Eventos; decidir cobranças e prioridades |
| Até 48 h depois | CIEVS | Validar o que couber; enviar boletim SE da semana; registrar encaminhamentos |
| Contínuo | SMS/CRS | Notificar eventos de campo no mesmo dia em que forem conhecidos |

---

## 6. Checklists de prontidão

### 6.1 Participante da área (antes de cada Sala)

- Cadastro aprovado (nível ses, se for área SES)
- Vínculo de área visível no caption da Sala
- Cobrança da própria área lida
- Indicadores editáveis enviados à validação
- Link/número SEI nas evidências documentais
- Nenhum dado sensível de paciente em Eventos ou observações

### 6.2 CIEVS (secretaria-executiva)

- Cadastros e vínculos da Portaria em dia
- Fila de Eventos triada (rumores antigos zerados ou justificados)
- Fila de Validação CIEVS processada
- Automáticos atualizados no Briefing
- Cobrança gerada (PDF/CSV) para as áreas faltantes
- Boletim da SE com nomenclatura oficial, se a Sala autorizar o envio
- Contatos regionais individuais atualizados quando disponíveis

### 6.3 SMS / CRS (campo)

- Conta restrita ativa (municipal ou regional)
- Eventos relevantes registrados com protocolo
- Encaminhamento à CRS/CIEVS quando o evento exigir apoio estadual

---

## 7. Glossário rápido

| Termo | Significado |
|-------|-------------|
| ARARAS MT | Plataforma de inteligência clima–ambiente–saúde da SES-MT / CIEVS |
| ARARA-xxx | Código do indicador no catálogo do Plano El Niño |
| Sala de Situação | Módulo restrito do Plano (Portaria 0590) |
| Índice oficial | Implementação só após validação CIEVS dos itens do índice |
| Aguardando fonte | Automático sem dado na tabela — não é zero |
| SEI | Processo oficial; ARARAS guarda o vínculo |
| Fan-out | Encaminhamento territorial de alertas (SMS/CRS), distinto da Sala |

---

## 8. Documentação técnica e contatos

| Documento | Uso |
|-----------|-----|
| docs/PLANO_EL_NINO_SALA_SITUACAO.md | Regras do módulo, conectores e automáticos |
| docs/SALA_SITUACAO_PLANO_EL_NINO.md | Desenho do Plano e classes ARARA |
| docs/institucional/DESTINATARIOS_ALERTAS.md | Destinatários de alertas territoriais |
| config/plano_el_nino_participantes.yaml | Catálogo operacional da Sala (e-mails) |

**Contato operacional:** CIEVS-MT · notifica@ses.mt.gov.br · menandesneto@ses.mt.gov.br

---

*Documento orientativo para operação da Sala. Versão 1.1 alinhada ao painel ARARAS MT (agosto/2026). Substitui a versão 1.0 usada na primeira validação.*
