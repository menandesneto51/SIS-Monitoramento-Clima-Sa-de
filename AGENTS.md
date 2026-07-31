# SIS-MT Clima-Saúde

Python/Streamlit dashboard for real-time climate-health risk monitoring across the state of Mato Grosso, Brazil (CIEVS/SES-MT). See `README.md` for the product overview and `docs/` for deep dives.

## Cursor Cloud specific instructions

### Layout / services
- Single Streamlit app. Entry point is `streamlit_app.py`, which `runpy`-executes the first of `app_v9.py`, `app_v8.py`, `app_v6.py` that exists (currently `app_v9.py`). Shared logic lives in the `sisclima/` package.
- The Docker Postgres stack in `docker-compose.yml` (`db`, `pipeline`, `app`, `alerts-scheduler`) is the production path and is optional for local development.

### Python env
- Dependencies are installed into a virtualenv at `.venv` (git-ignored). Run tools via `.venv/bin/<tool>` (e.g. `.venv/bin/streamlit`, `.venv/bin/python`). The startup update script recreates/refreshes `.venv`.
- Requires the `python3.12-venv` system package (already present in the environment).

### Run the app (dev mode)
- `.venv/bin/streamlit run streamlit_app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false`
- Health check: `curl http://localhost:8501/_stcore/health` returns `ok`. The app script only executes when a browser/websocket client connects.

### Database — important, non-obvious
- With no `DATABASE_URL` set, the app auto-falls back to the bundled read-only SQLite snapshot `data/cloud/sis_cloud_seed.db` (wired up in `streamlit_app.py`). This is the intended local-dev mode and is enough to render the full dashboard with real-looking data.
- Expect a yellow banner: "o painel está em sqlite, não em PostgreSQL". This is normal in dev, not an error.
- Do NOT copy `.env.example` to `.env` for local dev: it sets `DATABASE_URL` to a Postgres at `localhost:5432` that isn't running, which overrides the SQLite fallback and breaks data loading. Only create a `.env` if you actually bring up the Docker Postgres stack.
- Live SES data sources (DW/SQL Server, IndicaSUS/BdSES, SISREG) require SES VPN/network and credentials, so they cannot be exercised in this environment; the SQLite snapshot stands in for them.

### Lint / test / build
- There is no automated test suite and no linter config. The `validar_*.py` scripts are operational data-source validators that require live SES connectivity, not unit tests.
- "Lint"/build validation is byte-compilation: `.venv/bin/python -m compileall streamlit_app.py app_v9.py sisclima`.
- Verify end to end by loading the dashboard in a browser and exercising a tab + the município filter.
