# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    DW_DRIVER=FreeTDS

WORKDIR /app

# Dependências leves. Conexão ao DW via pymssql (sem repositório Microsoft).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates freetds-bin freetds-dev gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements-docker.txt \
    && pip install pymssql==2.3.4

COPY . .

RUN mkdir -p data/input data/output data/local/sivep logs exports/relatorios \
    && chmod +x docker/entrypoint.sh

EXPOSE 8501

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["app"]
