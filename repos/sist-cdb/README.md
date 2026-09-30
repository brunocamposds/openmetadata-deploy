# Repositório de Engenharia de Dados: SIST_CDB

Este repositório simula o ambiente de engenharia de dados do produto de dados **SIST_CDB** (Source-Aligned).

## Visão Geral
- **Domínio**: Investimentos
- **Subdomínio**: Emissões Bancárias
- **Time / Squad**: Squad Renda Fixa Emissões (`squad-cdb`)
- **Padrão de Produto de Dados**: Open Data Product Specification (ODPS v1.0.0) em `data-product.odps.yaml`
- **Padrão de Contratos de Dados**: Open Data Contract Standard (ODCS v3.0.0) em `contracts/`

## Estrutura
- `data-product.odps.yaml`: Definição ODPS completa, portos de saída, SLAs e metadados de governança.
- `contracts/cdb-posicao.odcs.yaml`: Contrato de dados da tabela `investments.cdb.silver_posicao`.
- `contracts/cdb-movimentacao.odcs.yaml`: Contrato de dados da tabela `investments.cdb.silver_movimentacao`.
- `src/ingestion_bronze.py`: Pipeline PySpark de captura e persistência em Delta Lake Bronze.
- `src/transform_silver.py`: Pipeline PySpark de validação de regras ODCS e carga na Silver.
