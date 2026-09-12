# SQL / adapters candidatos (DW → ARARAS)

Gerado em 2026-09-12 a partir do inventário. **Não ligar em produção** sem validação CIEVS.

## A) Top 10 — já linkados (ampliar agregação / painel)

| Prioridade | Objeto | SQL / loader existentes | Flag | Ação sugerida |
| ---: | --- | --- | --- | --- |
| 1 | `VW_SINAN_INTOXICACAOEXOGENA` | `dw_sinan_agravos_calor.sql`, `dw_sinan_intoxicacao_detalhe.sql`, `sinan_agravos_calor.sql` | USE_DW_SINAN | Ampliar SQL existente — Fumaça/queimada → sinal_fumaca + digest ambiental |
| 2 | `VW_SINAN_ANIMAISPECONHENTOS` | `dw_sinan_agravos_extras_clima.sql` | USE_DW_SINAN | Ampliar SQL existente — Extras clima (estiagem) → boletim / RIT hidro-território |
| 3 | `VW_SINAN_HANTAVIROSE` | `dw_sinan_agravos_extras_clima.sql` | USE_DW_SINAN | Ampliar SQL existente — Extras clima → boletim agravos |
| 4 | `VW_SINAN_FEBREMACULOSA` | `dw_sinan_agravos_extras_clima.sql` | USE_DW_SINAN | Ampliar SQL existente — Extras clima → boletim agravos |
| 5 | `VW_SINAN_LEISHMANIOSEVISCERAL` | `dw_sinan_agravos_extras_clima.sql` | USE_DW_SINAN | Ampliar SQL existente — Extras clima → boletim agravos |
| 6 | `VW_SINAN_SINDROMERESPIRATORIAAGUDAGRAVE` | `dw_sinan_agravos_calor.sql`, `dw_sinan_agravos_extras_clima.sql`, `sinan_agravos_calor.sql`, `sivep_srag_residencia.sql` | USE_DW_SINAN, USE_DW_SIVEP | Ampliar SQL existente — SRAG no DW vs SIVEP local — cruzamento / fallback |
| 7 | `VW_INTERNACAO` | `dw_internacao_cid_clima.sql` | USE_DW_INDICASUS | Ampliar SQL existente — Internações CID clima → pressão assistencial / boletim |
| 8 | `CNES_LEITOS` | `dw_cnes_leitos.sql`, `dw_indicasus_leitos.sql`, `indicasus_leitos.sql` | USE_DW_CNES, USE_DW_INDICASUS | Ampliar SQL existente — Ocupação/capacidade → IndicaSUS/pressão |
| 9 | `CNES_ESTABELECIMENTOS` | `dw_cnes_estabelecimentos.sql` | USE_DW_CNES | Ampliar SQL existente — Rede CNES → mapas / resiliência |
| 10 | `VW_GAL` | `dw_gal_lacen_resultados.sql`, `lacen_gal_resultados.sql` | USE_DW_GAL | Ampliar SQL existente — GAL/LACEN → boletim / vigilância laboratorial |

## B) Novos candidatos altos (SQL/loader ainda não dedicados)

| Prioridade | Objeto | Arquivo SQL proposto | Loader proposto | Flag |
| ---: | --- | --- | --- | --- |
| 1 | `CNES_EQUIPAMENTOS` | `sql/dw_cnes_equipamentos_municipal.sql` | `load_dw_cnes_equipamentos()` | `USE_DW_CNES` |
| 2 | `CNES_EQUIPESATENCAOBASICA` | `sql/dw_cnes_equipesatencaobasica_municipal.sql` | `load_dw_cnes_equipesatencaobasica()` | `USE_DW_CNES` |
| 3 | `CNES_EQUIPESPROFISSIONAISATENCAOBASICA` | `sql/dw_cnes_equipesprofissionaisatencaobasica_municipal.sql` | `load_dw_cnes_equipesprofissionaisatencaobasica()` | `USE_DW_CNES` |
| 4 | `CNES_PROFISSIONAIS` | `sql/dw_cnes_profissionais_municipal.sql` | `load_dw_cnes_profissionais()` | `USE_DW_CNES` |
| 5 | `CNES_SERVICOCLASSIFICACAO` | `sql/dw_cnes_servicoclassificacao_municipal.sql` | `load_dw_cnes_servicoclassificacao()` | `USE_DW_CNES` |
| 6 | `SIVEP_MALARIA` | `sql/dw_sivep_malaria_municipal.sql` | `load_dw_sivep_malaria()` | `USE_DW_SIVEP` |
| 7 | `VW_SINAN_LEISHMANIOSETEGUMENTAR` | `sql/dw_vw_sinan_leishmaniosetegumentar_municipal.sql` | `load_dw_vw_sinan_leishmaniosetegumentar()` | `USE_DW_SINAN` |

## Notas

- Agregar sempre por `cod_ibge` + data; nunca persistir nome/cartão SUS.
- Preferir views `VW_*` já estabilizadas pela STI.
- SIVEP continua preferencialmente local; SRAG no DW é fallback/cruzamento.
- Stubs em `dw_sources.py` só após CIEVS validar ROI; flags default `false` até homologação.
- Esta conta enxerga apenas o banco `Datawarehouse` (sem SISREG/AIH/DDA no dbo listado).

## Roadmap de ondas (integração produto)

### Onda 1 — feita (ampliar já linkados)

- Intoxicação/fumaça → `sinal_fumaca_sem_pm` + cards Visão + boletim.
- Extras clima SINAN → painel + boletim (`sinan_extras_clima`).
- SRAG: SIVEP local preferencial; `fonte_srag` / fallback SINAN DW documentado.
- Internações CID clima + leitos alimentam leitura pressão × RIT (sem mudar `nivel`).

### Onda 2 — feita (novos SQL/loaders)

1. `VW_SINAN_LEISHMANIOSETEGUMENTAR` no UNION de `dw_sinan_agravos_extras_clima.sql` (`USE_DW_SINAN`).
2. `SIVEP_MALARIA` → `sql/dw_sivep_malaria_municipal.sql` + `load_dw_sivep_malaria()` (`USE_DW_SIVEP`).
3. `CNES_EQUIPAMENTOS` → `sql/dw_cnes_equipamentos_municipal.sql` + `load_dw_cnes_equipamentos()` (`USE_DW_CNES`).
4. Persistência: `epi_sivep_malaria`, `epi_cnes_equipamentos_municipal`; cards Visão + boletim.

### Onda 3 — feita (rede CNES detalhada)

- `CNES_PROFISSIONAIS` → `sql/dw_cnes_profissionais_municipal.sql` + `load_dw_cnes_profissionais()` (só contagens; sem nome/CNS/CPF).
- `CNES_EQUIPESATENCAOBASICA` → `sql/dw_cnes_equipes_ab_municipal.sql` + `load_dw_cnes_equipes_ab()`.
- `CNES_SERVICOCLASSIFICACAO` → `sql/dw_cnes_servico_classificacao_municipal.sql` + `load_dw_cnes_servico_classificacao()`.
- Flag: `USE_DW_CNES`. Não entra em `nivel` nem pred 7d.
- **Fora de escopo:** `CNES_EQUIPESPROFISSIONAISATENCAOBASICA` (PII/CPF + tabela vazia no inventário).

### IRM / RIT rede — feito (produto de capacidade)

- Agrega densidades CNES (estab/leitos/profissionais/eAB) + nebulização → IRM 0–100.
- Domínio RIT `rede` = fragilidade (`100 − IRM`); compostos `gap_fumaca_nebulizacao` e `pressao_x_resiliencia`.
- Sem flag nova (`USE_DW_CNES`). Não altera `nivel` / `nivel_predicao_7d`.
- Backlog v1.1: diversidade TipoUnidade (UBS/UPA); serviços SUS como subcomponente.
