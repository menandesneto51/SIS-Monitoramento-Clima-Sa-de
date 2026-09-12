# ADR — RIT Multirisco (Risco Integrado Territorial)

**Status:** Aceito (v1 operacional)  
**Data:** 2026-09-11  
**Contexto:** ARARAS MT / CIEVS-MT — boletim El Niño e painel clima–saúde

## Contexto

A projeção operacional ~7 dias (`nivel_predicao_7d`) é uma dimensão única de **risco térmico projetado**. O card metodológico deixa explícito que EHF, fumaça/PM2,5, hidrologia e pressão assistencial **não** entram nessa classe.

A Sala de Situação precisa, porém, de uma leitura **multirisco observada** no território, sem confundir horizonte de previsão térmica com sinais concomitantes (muitos sem forecast no mesmo horizonte, ou com defasagem).

## Decisão

Introduzir o **RIT — Risco Integrado Territorial** como produto **paralelo**:

| Produto | Horizonte | Escopo | Uso |
| --- | --- | --- | --- |
| Classe ARARAS (`nivel`) | Observado (rodada) | Estágio operacional (candidatos max) | Alerta / painel |
| MODELO ~7 DIAS (`nivel_predicao_7d`) | ~7 dias | Só térmico projetado | Escalada térmica |
| **RIT** (`rit_0_100`) | Observado (rodada) | Multidomínio | Leitura integrada Sala/boletim |
| `indice_prioridade_global` | Observado | Prioridade operacional ponderada | Priorização de gestão |
| Índice de prontidão (boletim) | Observado | Preparação Top-N | Ranking de preparação |

### Composição v1 (+ domínio rede 2026-09-12)

- Domínios: **térmico atual**, **ar/fumaça (PM2,5)**, **hidrologia**, **EHF observado**, **pressão assistencial**, **fragilidade de rede**.
- Cada domínio → escore 0–100 (limiares explícitos no motor).
- **RIT = máximo** entre domínios válidos (anti-redundância; alinhado a `risco_termico_projetado` e ao max de candidatos em `stages.py`).
- Metadados: `rit_dominio_dominante`, `rit_completude_pct`, scores por domínio, `rit_faixa`.
- Faixas (comparáveis à térmica): 0–24 verde; 25–49 amarela; 50–69 laranja; 70–84 vermelha; 85–100 roxa.

### Domínio rede / IRM (capacidade ≠ risco)

- **IRM** (`indice_resiliencia_municipal_0_100`): capacidade municipal CNES (0–100; alto = melhor). Produto Sala/boletim — **não** eleva o RIT.
- **`rit_score_rede`**: fragilidade = `clip(100 − IRM, 0, 100)` quando IRM válido; senão domínio **omitido** (como pressão defasada).
- Alta IRM → baixa fragilidade → **não** aumenta RIT. Rede frágil pode ser o domínio dominante se os demais estiverem baixos.
- Flag: `USE_DW_CNES` (sem flag nova). Sem CNES/IRM, domínio `rede` omitido.

### Defasagem (pressão assistencial)

- Se a idade da carga de pressão/APS exceder o limiar operacional (**14 dias**), o domínio **pressão é omitido** (não zera e não eleva o RIT).
- Completude cai; a narrativa do boletim deve mencionar a omissão.

### O que o RIT **não** é

- Não substitui nem “multiriscifica” `nivel_predicao_7d`.
- Não é o `indice_prioridade_global` nem o índice de prontidão do boletim.
- Vulnerabilidade cadastral (idosos, gestantes, asma, povos tradicionais) **não eleva** o RIT v1 — entra só como narrativa/prioridade.

## Limiares v1 (operacionais)

- **Ar (PM2,5 µg/m³):** ≥25 → 50; ≥50 → 75; ≥75 → 100.
- **EHF:** valor > 0 → 70; intensidade alta / EHF elevado → 85–100.
- **Hidro:** mapeamento de `nivel_alerta_hidro` (ou equivalente) para 0–100 por estágio.
- **Térmico atual:** mapeamento da classe/`nivel` atual (ou UTCI/Tmáx do dia) para 0–100.
- **Pressão:** `indice_pressao_saude` (0–100) se fresco; senão omitido.
- **Rede:** `100 − IRM` (fragilidade); omitido se IRM nulo (completude IRM < 40% ou CNES off).

## Consequências

- Vocabulário obrigatório no boletim: distinguir **RIT (observado multidomínio)** de **projeção ~7d (térmica)**.
- QA deve rejeitar afirmações de que o RIT “projeta 7 dias”.
- Painel/alertas (fase posterior) podem expor RIT como contexto, sem sobrescrever `nivel` / `nivel_predicao_7d`.

## Implementação

- Motor: `sisclima/engines/rit_multirisco.py`
- Persistência: colunas no `resumo_municipal_atual`
- Boletim: card + bloco + glossário; MODELO ~7 DIAS inalterado em significado

## Complemento (2026-09-12) — candidato EHF no nível

- `limiares_calor.ehf.usar_no_nivel` (default **false**): quando true, `stages.py` acrescenta candidato diário por intensidade EHF (baixa→2 / severa→3 / extrema→4), sem alterar a regra de persistência roxa já vigente.
- `onda_geocalor_ativa` é indicador composto de painel/digest (is_hw_day + EHF>0); **não** substitui `nivel` nem RIT.

## Complemento (2026-09-12) — IRM e compostos leves

- Motor IRM: `sisclima/engines/indice_resiliencia_municipal.py` (pesos: estab 25%, leitos 25%, profissionais 20%, eAB 15%, nebulização 15%).
- Ordem enrich: sinais DW → IRM → RIT → compostos (`gap_fumaca_nebulizacao`, `pressao_x_resiliencia`).
- Frescor unificado: `sisclima/engines/resumo_frescor.py` — reaplicado antes de alertas (digest/scheduler), boletim e carga do painel.
- `nivel` e `nivel_predicao_7d` intactos.
