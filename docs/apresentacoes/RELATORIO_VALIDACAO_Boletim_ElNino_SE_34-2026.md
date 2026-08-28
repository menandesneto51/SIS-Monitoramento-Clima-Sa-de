# Relatório de análise e validação

**Produto:** Boletim semanal El Niño — ARARAS MT / CIEVS-MT  
**Semana epidemiológica:** 34/2026 (23 a 29 de agosto de 2026) — calendário SINAN  
**Rodada:** 24/08/2026 às 15h31  
**Finalidade:** análise técnica e validação para uso na Sala de Situação

---

## 1. Objeto da validação


| Item                 | Arquivo                                                         |
| -------------------- | --------------------------------------------------------------- |
| Texto-fonte          | `docs/apresentacoes/Boletim_ElNino_SE_34-2026.md`               |
| PDF apresentável     | `docs/apresentacoes/Boletim_ElNino_SE_34-2026_apresentavel.pdf` |
| Log de QA automático | `docs/apresentacoes/Boletim_ElNino_SE_34-2026.qa.log`           |
| Mapas                | `docs/apresentacoes/_assets_SE_34-2026/`                        |


Extensão do PDF nesta emissão: **22 páginas** (meta editorial 22–26; versão anterior ~31).

---



## 2. Parecer resumido


| Bloco                              | Resultado                 | Observação                                                                                                    |
| ---------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Calendário SINAN                   | **Aprovado**              | SE 34 = 23–29/08/2026. SE 35 só em 30/08.                                                                     |
| Números do resumo × Tabela 1       | **Aprovado**              | 72/142 vermelho ou roxo; 37 roxa + 35 vermelha.                                                               |
| Projeção ~7 dias                   | **Aprovado com leitura**  | 141/142 vermelho ou roxo (roxa 131; vermelha 10; laranja 1).                                                  |
| Mapa 1                             | **Aprovado**              | Atual vs ~7 dias na mesma escala.                                                                             |
| Mapa 2                             | **Aprovado**              | Deixou de ficar cinza. 141 comparáveis + 1 sem pareamento = 142.                                              |
| Populações indígenas / quilombolas | **Aprovado**              | Presentes no corpo; listas completas no painel.                                                               |
| Distâncias da rede                 | **Aprovado**              | Tabela operacional retirada do corpo; síntese no texto.                                                       |
| Marca SES no cabeçalho             | **Aprovado com ressalva** | Painel SES em branco sobre azul-marinho (legível). “Governo de Mato Grosso” permanece maior na marca oficial. |
| Cálculos                           | **Não alterados**         | Revisão foi editorial/visual e de join do Mapa 2.                                                             |


**Recomendação:** o boletim pode seguir para leitura na Sala de Situação. Pendências abaixo não impedem a leitura, mas devem ser registradas.

---



## 3. Consistência dos números da rodada

Conferência interna do Markdown (cards, Tabela 1 e Mapa 2).


| Indicador                    | Valor publicado                | Checagem                    |
| ---------------------------- | ------------------------------ | --------------------------- |
| Risco atual vermelho ou roxo | 72/142 (50,7%)                 | 37 + 35 = 72                |
| Laranja / amarela            | 49 / 21                        | 72+49+21 = 142              |
| Projeção vermelho ou roxo    | 141/142 (99,3%)                | 131 + 10 = 141; 1 laranja   |
| Tmáx                         | mediana 34,3 °C; máx. 39,1 °C  | 16/142 (11,3%) ≥ 37 °C      |
| Umidade                      | mediana 48%; mín. 24%          | 15/142 (10,6%) ≤ 30%        |
| PM2,5                        | mediana 10,4; máx. 126,2 µg/m³ | 8/142 (5,6%) ≥ 25 µg/m³     |
| UTCI proxy                   | mediana 33,1 °C                | 109/142 (76,8%) ≥ 32 °C     |
| Cobertura dos 4 indicadores  | 142/142                        | OK                          |
| Focos 7 dias                 | 51.810                         | 118 municípios com detecção |
| Mapa 2 — comparáveis         | 141/142 (99,3%)                | 1 + 37 + 38 + 65 = 141      |
| Mapa 2 — sem pareamento      | 1                              | 141 + 1 = 142               |
| Agravamento (↑1 + ↑2+)       | 103/141 (73,0%)                | 38 + 65 = 103               |


El Niño: confirmado em 11/06/2026; Niño 3.4 = 1,4 °C nas semanas anteriores ao boletim.

---



## 4. Mapa 2 — o que foi corrigido

**Falha anterior:** mapa cinza e legenda com melhora = 0, estabilidade = 0, aumento = 0, em contradição com a projeção.

**Causa:** (1) chave IBGE 6 vs 7 dígitos no join com a malha; (2) classe cinza tratada como “sem dado” no cálculo de delta.

**Validação desta rodada**


| Critério                               | Valor                      | Status                   |
| -------------------------------------- | -------------------------- | ------------------------ |
| Soma melhora + estabilidade + ↑1 + ↑2+ | 141                        | ≠ 0                      |
| Comparáveis + sem pareamento           | 141 + 1 = 142              | OK                       |
| Situação atual ≠ projeção              | 72 vs 141 em vermelho/roxo | Delta não nulo, coerente |


---



## 5. Revisão editorial (o que mudou no documento)

Mantido: Calibri no PDF, identidade azul, mapas, referências, Portaria n.º 0590/2026/GBSES, povos indígenas, quilombolas, Saúde do Trabalhador, recomendações SES-MT/municípios.


| Pedido da rodada de revisão                      | Situação                    |
| ------------------------------------------------ | --------------------------- |
| Resumo em 6 cards                                | Atendido                    |
| Tabela 1 só com situação + municípios em atenção | Atendido                    |
| INMET por fenômeno, lista no painel              | Atendido (síntese no corpo) |
| Top 8 regionais / Top 10 municípios              | Atendido                    |
| Índice Top 10, sem nomes internos de score       | Atendido                    |
| Indígenas/quilombolas em bullets                 | Atendido                    |
| Tabela de km/minutos fora do corpo               | Atendido                    |
| Populações em 4 blocos                           | Atendido                    |
| Cenários em cards                                | Atendido                    |
| Redução de páginas 31 → 22–26                    | **22 páginas**              |


---



## 6. QA automático e inspeção visual

Do `Boletim_ElNino_SE_34-2026.qa.log`: cabeçalho, tabelas, figuras, índice de preparação, alertas, aldeias, quilombos, Saúde do Trabalhador, matriz SES-MT, conclusão, referências — **OK**.

**Issue automático (1):** `sigla_revisar_expansao: UNIEVS` — expandir na próxima emissão (Unidade de Inteligência Epidemiológica e Vigilância em Saúde, se for essa a forma institucional vigente).

Inspeção visual do PDF:

- Página 1: capa enxuta; referências climáticas/operacionais/normativas no formato pedido.
- Página 2: cards + leitura + 3 prioridades; El Niño em texto, sem tabelinha Indicador/Observado.
- Página 4: Mapa 1 colorido (atual × ~7 dias).
- Página 5: **Mapa 2 colorido**, com as quatro classes de variação e o município sem pareamento.

---



## 7. Limitações e pendências (não bloqueiam a Sala)

1. **Marca SES.** A composição oficial continua com “Governo de Mato Grosso” visualmente maior que “Secretaria de Estado de Saúde”. O erro grave (branco no branco) foi corrigido. Ampliar a SES além disso exige arquivo oficial da SECOM/SES, não recorte improvisado.
2. **DW epidemiológico.** Timeout de rede para o SQL Server na geração; agravos de internamento/intoxicação podem estar incompletos nesta rodada.
3. **Tempos de deslocamento (minutos).** Não validados; por isso não entram no corpo. Os km estimados seguem no painel.
4. **1 município sem pareamento** no Mapa 2 — registrar na ata; não zera o mapa.
5. **UNIEVS** sem expansão no texto.

---



## 8. Encaminhamento para validação humana

- [ ] CIEVS: conferir se os 72 municípios em vermelho/roxo batem com o painel da mesma rodada (24/08, 15h31).
- [ ] Sala de Situação: aceitar a leitura de agravamento (141/142 na projeção) como insumo de preparação, não como previsão sazonal.
- [ ] Comunicação/identidade: confirmar se o lockup SES+Governo no cabeçalho atende ao Manual vigente.
- [ ] Próxima emissão (SE 35, a partir de 30/08): atualizar dados, expandir UNIEVS e, se houver arquivo SECOM com SES em maior peso óptico, substituir só o PNG do cabeçalho.

**Conclusão da análise técnica:** documento apto para análise e validação na Sala. Cálculos da rodada consistentes entre si; Mapa 2 validado; redução editorial aplicada sem retirada do conteúdo crítico (indígenas, quilombolas, trabalhador, Portaria, recomendações).