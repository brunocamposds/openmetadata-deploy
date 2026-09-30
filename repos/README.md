# Laboratório de Produtos de Dados ODPS, Contratos ODCS e OpenMetadata Governance

Este ecossistema simula repositórios de engenharia de dados em arquitetura **Data Mesh**, contendo produtos de dados **Source-Aligned** e **Consumer-Aligned (Derivado)**, com especificações no padrão **ODPS (Open Data Product Specification v1.0.0)**, contratos de dados no padrão **ODCS (Open Data Contract Standard v3.0.0)** e pipelines em **PySpark (Azure Databricks Unity Catalog + MongoDB Atlas Serving)**.

---

## 📁 Estrutura de Repositórios (`repos/`)

```text
repos/
├── sist-cdb/                               # Produto Source-Aligned: Emissões de CDB
│   ├── data-product.odps.yaml              # Especificação ODPS do Produto
│   ├── contracts/
│   │   ├── cdb-posicao.odcs.yaml           # Contrato ODCS da Posição de Custódia
│   │   └── cdb-movimentacao.odcs.yaml      # Contrato ODCS de Movimentações
│   ├── src/
│   │   ├── ingestion_bronze.py             # PySpark: Captura CDC para Delta Lake Bronze
│   │   └── transform_silver.py             # PySpark: Validação ODCS e Carga na Silver
│   └── README.md
│
├── sist-cra/                               # Produto Source-Aligned: Securitização de CRA
│   ├── data-product.odps.yaml              # Especificação ODPS do Produto
│   ├── contracts/
│   │   ├── cra-posicao.odcs.yaml           # Contrato ODCS da Posição de CRA
│   │   └── cra-movimentacao.odcs.yaml      # Contrato ODCS de Movimentações
│   ├── src/
│   │   ├── ingestion_bronze.py             # PySpark: Ingestão de Retornos para Bronze
│   │   └── transform_silver.py             # PySpark: Validação ODCS e Carga na Silver
│   └── README.md
│
└── renda-fixa-derivado/                    # Produto Consumer-Aligned: Renda Fixa Consolidada
    ├── data-product.odps.yaml              # Especificação ODPS do Produto Derivado
    ├── contracts/
    │   ├── rf-posicao-consolidada.odcs.yaml # Contrato ODCS: Silver e Gold Saldo Investido
    │   ├── rf-movimentacao-consolidada.odcs.yaml # Contrato ODCS: Silver e Gold Aportes/Resgates
    │   └── rf-mongo-canal.odcs.yaml        # Contrato ODCS: Porta de Saída MongoDB Serving
    ├── src/
    │   ├── transform_silver_consolidated.py # PySpark: Unificação CDB + CRA
    │   ├── transform_gold_metrics.py       # PySpark: Agregação Executiva Gold
    │   └── export_mongodb_serving.py       # PySpark: Sincronização MongoDB para Canais
    └── README.md
```

---

## 🎯 Padrões Adotados e Tecnologias Hospedeiras

### 1. Hospedagem dos Dados
- **Camada Analítica (Lakehouse)**: Armazenamento em formato **Delta Lake** no **Azure Data Lake Storage Gen2 (ADLS Gen2)** com catálogo gerenciado via **Databricks Unity Catalog** (namespace de três níveis: `investments.<schema>.<table>`).
- **Camada Operacional (Serving Store)**: Coleção de documentos em **MongoDB Atlas** (`investments_serving.rf_customer_positions`) para atender canais digitais e APIs com baixa latência.

### 2. ODPS (Open Data Product Specification v1.0.0)
- Extração padronizada de **Time/Squad**, **Domínio**, **Subdomínio**, **Owners**, **SLAs/SLOs**, **Tags**, **Portas de Entrada** e **Portas de Saída**.
- Ingestão automatizada em esteiras de CI/CD para catalogação no **OpenMetadata Marketplace**.

### 3. ODCS (Open Data Contract Standard v3.0.0)
- **Modelos de Schema**: Definição rigorosa de campos lógicos e físicos (`three-tier` Unity Catalog), restrições de nulidade, chaves primárias e classificações de governança (ex: `PII`).
- **Regras de Qualidade (Data Quality)**: Verificações de integridade de dados.
- **Níveis de Serviço (SLA)**: Garantias de `freshness`, `availability` e latência para os consumidores.

---

## 🚀 Como Executar a Ingestão no OpenMetadata

O script automatizado roda diretamente no WSL Ubuntu e alimenta o OpenMetadata via API REST oficial:

```bash
# Executar a esteira de governança CI/CD por repositório
wsl -d Ubuntu -- ./scripts/deploy_repo_product.sh repos/sist-cdb
wsl -d Ubuntu -- ./scripts/deploy_repo_product.sh repos/sist-cra
wsl -d Ubuntu -- ./scripts/deploy_repo_product.sh repos/renda-fixa-derivado
```

---

## 🔗 Painéis de Validação no OpenMetadata Frontend

Após a execução e com o túnel ativo (`make port-forward`), acesse a interface web em **[http://localhost:8585](http://localhost:8585)**:

| Entidade / Recurso | Link Direto no Navegador |
| :--- | :--- |
| **Marketplace Global (Explore)** | [http://localhost:8585/explore/dataProducts](http://localhost:8585/explore/dataProducts) |
| **Data Product: SIST_CDB** | [http://localhost:8585/domain/Investimentos.EmissoesBancarias/dataProducts/SIST_CDB](http://localhost:8585/domain/Investimentos.EmissoesBancarias/dataProducts/SIST_CDB) |
| **Data Product: SIST_CRA** | [http://localhost:8585/domain/Investimentos.Securitizacao/dataProducts/SIST_CRA](http://localhost:8585/domain/Investimentos.Securitizacao/dataProducts/SIST_CRA) |
| **Data Product: RENDA_FIXA_DERIVADO** | [http://localhost:8585/domain/Investimentos.RendaFixa/dataProducts/RENDA_FIXA_DERIVADO](http://localhost:8585/domain/Investimentos.RendaFixa/dataProducts/RENDA_FIXA_DERIVADO) |
| **Domínio e Subdomínios** | [http://localhost:8585/domain/Investimentos](http://localhost:8585/domain/Investimentos) |
| **Tabela Silver CDB & Contrato** | [http://localhost:8585/table/azure_databricks_uc.investments.cdb.silver_posicao](http://localhost:8585/table/azure_databricks_uc.investments.cdb.silver_posicao) |
| **Linhagem Gráfica de Ponta a Ponta** | [http://localhost:8585/table/azure_databricks_uc.investments.cdb.silver_posicao/lineage](http://localhost:8585/table/azure_databricks_uc.investments.cdb.silver_posicao/lineage) |
| **Porta de Saída MongoDB (Serving)** | [http://localhost:8585/table/mongodb_atlas.investments_serving.collections.rf_customer_positions](http://localhost:8585/table/mongodb_atlas.investments_serving.collections.rf_customer_positions) |
