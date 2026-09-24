# OpenMetadata Mock Runner (Data Products, ODCS & Linhagem)

Este módulo fornece um container para geração de dados mockados, registro de **Data Products**, associação com contratos de dados no padrão **Open Data Contract Standard (ODCS)** e construção de grafos de **Linhagem** no OpenMetadata.

## Estrutura

- `Dockerfile`: Imagem Python 3.11 com SDK oficial do OpenMetadata e parsers de contratos.
- `requirements.txt`: Dependências Python.
- `contracts/sample_customer_contract.odcs.yaml`: Exemplo completo de Data Contract ODCS v3.0.
- `scripts/seed_data_products.py`: Script para registrar Domínio, Data Product, Tabelas e vincular o contrato ODCS.
- `scripts/seed_lineage.py`: Script para vincular a linhagem completa (`raw` -> `staging` -> `data product mart` -> `dashboard`).

## Como Construir e Executar

### 1. Build da Imagem Docker
No WSL Ubuntu:
```bash
docker build -t om-mock-runner:latest docker/mock-runner
```

### 2. Executar Conectado ao OpenMetadata Local
Após o OpenMetadata subir no K3s (com port-forward ativo na porta 8585):
```bash
docker run --rm --net=host \
  -e OPENMETADATA_SERVER_URL="http://localhost:8585/api" \
  om-mock-runner:latest python scripts/seed_data_products.py

docker run --rm --net=host \
  -e OPENMETADATA_SERVER_URL="http://localhost:8585/api" \
  om-mock-runner:latest python scripts/seed_lineage.py
```
