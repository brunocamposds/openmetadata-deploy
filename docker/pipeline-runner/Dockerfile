# ==============================================================================
# Pipeline Runner para os Jobs no K3s
# Executa ingestão Bronze, transformações Silver/Gold, MongoDB Export e testes OM
# ==============================================================================
FROM python:3.11-slim

LABEL maintainer="AI Data Engineer Workspace"
LABEL description="Runner de Pipelines para DuckDB, MongoDB e OpenMetadata no K3s"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências Python necessárias para os pipelines
RUN pip install --no-cache-dir \
    duckdb==1.5.6 \
    psycopg2-binary==2.9.13 \
    pymongo==4.18.2 \
    requests==2.31.0 \
    pyyaml==6.0.1 \
    pyiceberg==0.12.0 \
    fastparquet==2026.9.0

# Define variáveis de ambiente padrão internas do cluster K3s
ENV DUCKDB_SERVER_HOST="duckdb-server.openmetadata.svc.cluster.local" \
    DUCKDB_SERVER_PORT="5432" \
    DUCKDB_DB="investments" \
    DUCKDB_USER="duckdb_user" \
    DUCKDB_PASSWORD="duckdb_password" \
    MONGODB_URI="mongodb://mongodb.openmetadata.svc.cluster.local:27017" \
    OPENMETADATA_URL="http://openmetadata.openmetadata.svc.cluster.local:8585/api" \
    PYTHONUNBUFFERED=1

CMD ["python", "--version"]
