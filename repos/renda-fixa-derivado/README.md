# Repositório de Engenharia de Dados: RENDA_FIXA_DERIVADO

Este repositório simula o ambiente de engenharia de dados do produto de dados **RENDA_FIXA_DERIVADO** (Consumer-Aligned / Derived).

## Visão Geral
- **Domínio**: Investimentos
- **Subdomínio**: Renda Fixa
- **Time / Squad**: Squad Renda Fixa Consolidada (`squad-renda-fixa-core`)
- **Padrão de Produto de Dados**: Open Data Product Specification (ODPS v1.0.0) em `data-product.odps.yaml`
- **Padrão de Contratos de Dados**: Open Data Contract Standard (ODCS v3.0.0) em `contracts/`
- **Upstreams**: Consome os produtos Source-Aligned `SIST_CDB` e `SIST_CRA`.

## Estrutura
- `data-product.odps.yaml`: Definição ODPS completa, mapeamento upstream/downstream, portas de saída analíticas e operacionais.
- `contracts/rf-posicao-consolidada.odcs.yaml`: Contrato para `investments.renda_fixa.silver_posicao` e `investments.renda_fixa.gold_saldo_investido`.
- `contracts/rf-movimentacao-consolidada.odcs.yaml`: Contrato para `investments.renda_fixa.silver_movimentacao` e `investments.renda_fixa.gold_movimentacao_sumarizada`.
- `contracts/rf-mongo-canal.odcs.yaml`: Contrato para a porta de saída operacional MongoDB `investments_serving.rf_customer_positions`.
- `src/transform_silver_consolidated.py`: Pipeline PySpark de consolidação e harmonização de CDB e CRA na camada Silver.
- `src/transform_gold_metrics.py`: Pipeline PySpark de agregação executiva e cálculo de saldos/movimentações Gold.
- `src/export_mongodb_serving.py`: Pipeline PySpark de exportação para a coleção documental no MongoDB Atlas para consumo por canais/APIs.
