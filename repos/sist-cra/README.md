# Repositório de Engenharia de Dados: SIST_CRA

Este repositório simula o ambiente de engenharia de dados do produto de dados **SIST_CRA** (Source-Aligned).

## Visão Geral
- **Domínio**: Investimentos
- **Subdomínio**: Securitização
- **Time / Squad**: Squad Securitização e Agro (`squad-cra`)
- **Padrão de Produto de Dados**: Open Data Product Specification (ODPS v1.0.0) em `data-product.odps.yaml`
- **Padrão de Contratos de Dados**: Open Data Contract Standard (ODCS v3.0.0) em `contracts/`

## Estrutura
- `data-product.odps.yaml`: Definição ODPS completa, portos de saída, SLAs e metadados de governança.
- `contracts/cra-posicao.odcs.yaml`: Contrato de dados da tabela `investments.cra.silver_posicao`.
- `contracts/cra-movimentacao.odcs.yaml`: Contrato de dados da tabela `investments.cra.silver_movimentacao`.
- `src/ingestion_bronze.py`: Pipeline PySpark de captura e persistência em Delta Lake Bronze.
- `src/transform_silver.py`: Pipeline PySpark de validação de regras ODCS e carga na Silver.
