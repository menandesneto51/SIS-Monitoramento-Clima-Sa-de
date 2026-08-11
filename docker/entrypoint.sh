#!/bin/sh
set -e

echo "[ARARAS] backend=${DATABASE_URL:-sqlite} | DW=${USE_SQLSERVER:-false}"

python - <<'PY'
from sisclima.core.db import init_db, backend_name
init_db()
print(f"[ARARAS] base operacional pronta: {backend_name()}")
PY

case "${1:-app}" in
  app)
    exec streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501
    ;;
  pipeline)
    exec python -c "from sisclima.pipeline import run_pipeline; r=run_pipeline(send_alerts=False); print(r)"
    ;;
  pipeline-alerts)
    exec python -c "from sisclima.pipeline import run_pipeline; r=run_pipeline(send_alerts=True); print(r)"
    ;;
  alert-once)
    exec python -m sisclima.alerts.scheduler --once --force
    ;;
  alert-scheduler)
    exec python -m sisclima.alerts.scheduler --loop
    ;;
  validate-dw)
    exec python validar_dw_conexao.py
    ;;
  bash|sh)
    exec /bin/bash
    ;;
  *)
    exec "$@"
    ;;
esac
