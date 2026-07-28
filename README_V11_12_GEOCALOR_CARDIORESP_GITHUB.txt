V11.12 - GeoCalor cardiorrespiratório + painel + alerta Cuiabá + GitHub

Implementa:
1. calcular_geocalor_cardioresp_v11_12.py
   Cria:
   - geocalor_cardioresp_rr_municipal_v11_12
   - geocalor_cuiaba_cardioresp_v11_12
   - geocalor_status_modelagem_v11_12

2. pages/10_GeoCalor_Cardiorrespiratorio.py
   Página nova no painel Streamlit.

3. patch_alerta_cuiaba_geocalor_cardioresp_v11_12.py
   Insere no alerta de Cuiabá o bloco de análise cardiorrespiratória.

4. RODAR_GEOCALOR_CARDIORESP_V11_12.cmd
   Roda cálculo e patch do alerta de Cuiabá.

5. RODAR_SISTEMA_COMPLETO_GEOCALOR_V11_12.cmd
   Roda o sistema completo e o módulo GeoCalor.

6. SUBIR_GITHUB_LIMPO_V11_12.cmd
   Sobe para:
   https://github.com/menandesneto51/SIS-Monitoramento-Clima-Sa-de
   usando whitelist segura.

Atenção metodológica:
O RR GeoCalor completo exige tabela diária com:
cod_ibge, data, isHW, internacoes_cardio, internacoes_resp, obitos_cardio, obitos_resp.

Se essa tabela ainda não existir, o sistema registra status de dados insuficientes e não inventa RR.
