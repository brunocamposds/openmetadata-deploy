# Dockerfile para Mock Runner, ODCS Data Contracts e Linhagem no OpenMetadata
FROM python:3.11-slim

LABEL maintainer="AI Data Engineer Workspace"
LABEL description="Runner conteinerizado para mock de ativos de dados, contratos ODCS/ODPS e linhagem no OpenMetadata"

# Instalação de dependências do sistema necessárias para compilação e rede
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia contratos ODCS de exemplo e scripts de automação
COPY contracts/ ./contracts/
COPY scripts/ ./scripts/

# Variáveis de ambiente padrão com fallback para o cluster local
ENV OPENMETADATA_SERVER_URL="http://openmetadata:8585/api" \
    OPENMETADATA_JWT_TOKEN="" \
    PYTHONUNBUFFERED=1

# Script padrão executado ao iniciar o container
CMD ["python", "scripts/seed_data_products.py"]
