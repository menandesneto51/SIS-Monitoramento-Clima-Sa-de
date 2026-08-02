# Alinhamento SIS Clima-Saúde MT × AdaptaSUS / Guia MS

Documento operacional do CIEVS-MT para conectar o painel SIS às diretrizes federais de adaptação do SUS à mudança do clima.

## Fontes oficiais

| Documento | Uso no SIS |
|-----------|------------|
| [Plano Setorial de Saúde – AdaptaSUS](https://www.gov.br/saude/pt-br/centrais-de-conteudo/publicacoes/svsa/vigilancia-ambiental/plano-setorial-de-saude-adaptasus.pdf) | 4 eixos-chave, 6 riscos prioritários, 27 metas / 93 ações (até 2035) |
| [Guia de Mudanças Climáticas e Saúde](https://guiadoclima.saude.gov.br/) | Orientações práticas (calor, frio, ar, seca, enchentes, doenças transmissíveis, SAN) |
| [Guia de Vigilância Integrada covid-19/influenza](https://www.gov.br/saude/pt-br/centrais-de-conteudo/publicacoes/guias-e-manuais/2024/guia-vigilancia-integrada-da-covid-19-influenza-e-outros-virus-respiratorios-de-importancia-em-saude-publica) (MS/SVSA, 2024) | Indicadores SIVEP/SRAG e sentinela SG |
| Catálogo local | `config/adaptasus_riscos.yaml` |

## Eixos-chave do AdaptaSUS

1. Alterações nos padrões de morbidade e mortalidade de doenças sensíveis ao clima  
2. Ampliação das demandas nos serviços de saúde  
3. Comprometimento ou interrupção da prestação dos serviços de saúde  
4. Emergência em saúde pública  

## Matriz risco → SIS

| Risco prioritário | Cobertura SIS | Indicadores principais | Tabelas / motores |
|-------------------|---------------|------------------------|-------------------|
| Extremos de temperatura (calor/frio) | Forte em calor; frio fraco | `tmax`, `utci_proxy`, `risco_cumulativo_3d`, `risco_calor_vulneravel` | `met_biometeo`, GeoCalor, `panel_indicators` |
| Poluição atmosférica | Parcial | `pm25_ugm3`, `risco_ar_queimadas` | `qualidade_ar_municipal` |
| Vetoriais / zoonoses | Parcial (arboviroses) | `casos_arbovirus_7d`, `risco_vetorial_climatico` | `epi_arboviroses_*` |
| Extremos de precipitação | Parcial | `precipitacao_mm`, Cemaden/ANA | `cemaden_alertas`, `ana_*` |
| WASH | Parcial (Censo IBGE 2022) | `cobertura_rede_agua_pct`, `deficit_esgoto_inadequado_pct`, `indice_deficit_wash`, `risco_wash` | `wash_municipal`, `adaptasus_intelligence` |
| SAN | Ausente | — | Fase 2 (fonte SES/SISVAN) |

## Artefatos gerados pelo SIS

| Artefato | Descrição |
|----------|-----------|
| `adaptasus_risco_municipal` | Scores 0–100 por risco + risco dominante + orientação |
| `adaptasus_risco_estado` | Resumo estadual / cobertura |
| `indice_adaptacao_climatica` | Índice composto no `resumo_municipal_atual` |
| Aba **AdaptaSUS / Guia MS** | Visualização operacional no painel |

## Glossário operacional CIEVS-MT

- **Risco dominante**: risco AdaptaSUS com maior score no município nesta rodada.  
- **Índice de adaptação climática**: síntese 0–100 dos riscos cobertos, penalizada por baixa completude de dados.  
- **Lacuna explícita**: SAN sem fonte SES/SISVAN — o painel declara a ausência; não interpretar como risco zero.  
- **WASH**: déficit estrutural do Censo IBGE 2022 (água/esgoto); amplificado em estiagem no score AdaptaSUS.  
- **Orientação AdaptaSUS**: checklist curto “o que monitorar / o que fazer”, inspirado no Guia MS (não substitui protocolo clínico).

## Limitações honestas

- Este alinhamento **operacionaliza** o AdaptaSUS no CIEVS-MT; não redefine metas federais.  
- WASH é estrutural (Censo), não monitoramento operacional SNIS/SINISA.  
- Indicadores SAN só entram quando houver base estadual confiável.  
- Predição 7 dias do SIS não é forecast climático sazonal.
