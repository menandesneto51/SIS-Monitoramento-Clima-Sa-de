# Plano El Niño 2026 — Sala de Situação (ARARAS MT)

**Produto:** ARARAS MT (Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde).  
A planilha-fonte usa o rótulo **ARARA** nos IDs (`ARARA-001` …). Isso é código de origem, não o nome do sistema.

**Princípio:** o ARARAS é o **registro oficial** do Plano. E-mail e WhatsApp são **notificação e cobrança**, não substituem o módulo.

Fonte da primeira carga: `Controle_Indicacoes_El_Nino_SES_MT_2026.xlsx` (40 ações originais, **88 indicadores** ARARA).

Este módulo **não** inclui indicadores novos no boletim semanal.

---

## 1. Fluxo

1. CIEVS/secretaria-executiva publica a ação no catálogo (área, prazo, indicador).
2. Coordenador ou técnico da **própria área** registra andamento (append-only).
3. Anexa evidência: **link SEI** (processo oficial) e, se quiser, PDF no ARARAS.
4. Situação: `informado` → `em_validacao` → `validado` ou `rejeitado`.
5. Rejeição **não apaga** o histórico: gera nova linha; a área reenvia.
6. Sala de Situação lê o briefing: % de implementação, status, eixos, pendentes/vencidas.
7. 100% **oficial** só existe quando todos os itens do índice estão concluídos **e** validados.

Status da ação: `nao_iniciada` · `em_andamento` · `em_validacao` · `concluida` · `impedida` · `suspensa` · `nao_aplicavel`.

---

## 2. Perfis (além do painel climático)

O cadastro do painel permanece: `publico` / `municipal` / `regional` / `ses` / `admin`.

| Perfil do Plano | Papel |
|---|---|
| `admin_araras` | Catálogo, vínculos, auditoria |
| `secretaria_executiva_cievs` | Validação e briefing da Sala |
| `coordenador_area` | Atualiza **somente** a sua `area_id` |
| `tecnico_area` | Envia evidência da própria área |
| `gestor` | Leitura do briefing (sem baixar evidência se for `consulta`) |
| `consulta` | Leitura; sem download de evidência |

A **Sala** só abre com nível de painel `ses` ou `admin`. Municipal/regional/público não entram.

**Isolamento:** Assistência Farmacêutica não edita Vigilância Sanitária (e o inverso). Quem tenta gravar outra área recebe recusa.

---

## 3. Como a área informa o indicador

A área **não calcula percentual**. Informa o dado bruto; o ARARAS calcula e o CIEVS valida.

Exemplo (IND-003, 16 ERS): a área informa **15**. O sistema já conhece o denominador **16**. Resultado: **15/16 = 93,8% 🟡**. Só vira **100% oficial** com 16/16 **e** validação CIEVS.

| Modo | O que a área faz |
|---|---|
| Semiautomático (36) | Informa numerador (e confirma denominador se preciso) |
| Automático (43) | Não digita — valor virá de DW/fonte (conector posterior) |
| Documental (9) | Sim/Não + evidência (SEI/PDF) |

Risco/gatilho (16) **não entra** no índice de implementação.

Na Sala (`ses+`): tabela dos 88, formulário da própria área, fila de validação CIEVS. Sem preenchimento: **0%**.

---

## 3b. Três modos de indicador

| Modo | Uso |
|---|---|
| `automatico` | Lido de sistema/fonte; área não digita o valor |
| `semiautomatico` | Sistema sugere; área confirma |
| `documental` | Área envia evidência (SEI/PDF) |

Risco/Gatilho **não entra** no índice de implementação (não conta como “meta atingida”).

---

## 4. Validação e histórico

- Cadeia: `informado` → `em_validacao` → `validado` \| `rejeitado`.
- Tabela `atualizacao`, `evidencia`, `validacao` e `audit_log` são **somente insert**.
- Percentual bruto 15/20 = **75%**. Esse 75% não vira 100% oficial sem validação CIEVS.

---

## 5. Repositório de evidência

Campos: `tipo`, `documento`, `data`, `area`, `acao_id`, `versao`, `responsavel_envio`, `uploaded_at`, `situacao`, `link_sei`, `arquivo`, `observacao`.

O **SEI** é o processo administrativo oficial. O ARARAS guarda o link e, opcionalmente, uma cópia PDF. Evidência **não** aparece no painel público (`sisclima/ui/painel_publico.py`).

---

## 6. Notificações (config)

Canal inicial: **e-mail**. Eventos: nova ação, prazo 15/7/3 dias, vencido, evidência enviada, rejeitada, meta atingida, indicador crítico, escalonamento.

---

## 7. Como o coordenador atualiza uma ação

1. Entrar no painel interno (ses/admin) → **Sala de Situação / Plano El Niño**.
2. Conferir o vínculo `coordenador_area` + `area_id`.
3. Selecionar ação da própria área.
4. Chamar o registro de atualização (status + observação). O sistema recusa se a área for outra.
5. Informar `link_sei` (obrigatório se não houver arquivo).
6. Aguardar validação da secretaria-executiva CIEVS.

Nesta fatia a UI mostra o briefing e a lista; a gravação já existe em `sisclima.plano.operacao.registrar_atualizacao` (formulário de escrita completo na próxima fatia).

---

## 8. Briefing da Sala

- % de implementação (bruto vs oficial)
- Contagens por status e por eixo
- Pendentes e vencidas
- Sem atualizações gravadas: **0%** e todas as ações `nao_iniciada`

---

## 9. Automáticos (DW/SINAN/CNES) e login STI

Os 43 automáticos estão em `config/plano_el_nino_conectores.yaml`. Sem dado da fonte, o ARARAS **não inventa** valor (`aguardando_fonte`).

Já ligados às tabelas da rotina: `resumo_municipal_atual`, `epi_sinan_agravos` / `epi_arboviroses` (inclui z-score/`alerta_aumento` do pipeline), CNES, `ops_estoque_autonomia`, qualidade do ar, `ops_comunicacao`, cadastro da Portaria 0590 (`IND-001`) e `ops_infraestrutura_unidade` (`IND-023`). Município ignorado SINAN (`510000`) não entra no denominador estadual.

Ainda sem carga contínua até a área depositar a tabela: SISAGUA (`ops_sisagua`), entomologia COVSAM (`ops_entomologia`) e denúncias COVSAN (`ops_denuncias`). Os conectores já leem essas tabelas quando existirem; vazio continua `aguardando_fonte`.

Na Sala: botão **Atualizar indicadores automáticos**. PDF/CSV de **cobrança às áreas** (quem informar, quem integrar fonte, e-mails da Portaria 0590). A rotina diária regenera `docs/apresentacoes/Cobranca_indicadores_Plano_El_Nino.pdf`. E-mail continua rascunho — não dispara sozinho.

### Login institucional

Enquanto a STI não publicar o issuer OIDC, permanece e-mail + senha.

Quando existir:

`STI_OIDC_ENABLED=true` + issuer, client_id, secret, redirect. Domínio: `@saude.mt.gov.br`.

O botão **Entrar com conta SES / STI** aparece. A conta entra como `ses`; o `area_id` do Plano segue em `plano_vinculo` até o SSO trazer o setor.

Arquivos: `config/plano_el_nino_2026.yaml`, `config/plano_el_nino_2026_catalogo.yaml`, `sql/plano_el_nino.sql`, `sisclima/plano/`.
