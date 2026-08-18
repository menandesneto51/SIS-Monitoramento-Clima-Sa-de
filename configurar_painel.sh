#!/usr/bin/env bash
# Configura e sobe o painel Streamlit (Linux/macOS) com defaults CIEVS.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Criando .env a partir de .env.example ..."
  cp .env.example .env
fi

mkdir -p .streamlit
if [[ ! -f .streamlit/secrets.toml ]]; then
  echo "Criando .streamlit/secrets.toml a partir do exemplo ..."
  cp .streamlit/secrets.toml.example .streamlit/secrets.toml
fi

ensure_env() {
  local key="$1" val="$2"
  if ! grep -q "^${key}=" .env 2>/dev/null; then
    echo "${key}=${val}" >> .env
  fi
}

ensure_env ALERT_CENTRAL_ONLY_SES true
ensure_env ALERT_FANOUT_ENABLED false
ensure_env SEND_ALERT_ON_LEVEL_CHANGE false
ensure_env ALERT_INTERVAL_HOURS 24
ensure_env ALERT_EMAIL_TO "notifica@ses.mt.gov.br"
ensure_env ALERT_LAYERS "ses,regionais,municipais,cuiaba"

# Snapshot local se não houver DATABASE_URL
if ! grep -q "^DATABASE_URL=" .env 2>/dev/null; then
  if [[ -f data/cloud/sis_cloud_seed.db ]]; then
    abs="$(cd data/cloud && pwd)/sis_cloud_seed.db"
    echo "DATABASE_URL=sqlite:///${abs}" >> .env
  fi
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -U pip
  pip install -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

PORT="${STREAMLIT_PORT:-8501}"
echo
echo "Painel: http://localhost:${PORT}"
echo "Aba Alertas: canal central = somente estadual; fan-out territorial adiado até a planilha."
echo
exec streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port "${PORT}" --browser.gatherUsageStats false
