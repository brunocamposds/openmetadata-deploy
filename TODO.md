# Plano de Adequações e Tarefas Pendentes (TODO)

Este documento registra as adequações de Governança, Contratos de Dados (ODCS/ODPS), Observabilidade e Pipelines identificadas durante a implantação do `sist-cdb`, detalhando os próximos passos para replicação nos demais repositórios do projeto.

---

## 1. Adequações Globais Concluídas (Script Central de CI/CD)

As seguintes melhorias foram incorporadas no script central [`scripts/deploy_data_product_ci.py`](scripts/deploy_data_product_ci.py) e aplicam-se a todos os repositórios:

- [x] **Detecção Dinâmica do Endpoint do OpenMetadata**:
  - Teste automático e resolução de porta (Porta `80` via Traefik Ingress local ou `:8585` via túnel/pod).
- [x] **Ajuste de Timeouts de Indexação do OpenSearch**:
  - Aumento do timeout das chamadas de API para 120s para garantir sincronização do OpenSearch local.
- [x] **Adoção e Migração do Padrão Oficial ODPS v4.1 (Linux Foundation / Bitol)**:
  - Arquivos `data-product.odps.yaml` dos 3 repositórios atualizados para a especificação v4.1.
  - Publicação e atualização nativa direta via endpoint: `PUT /api/v1/dataProducts/odps/yaml?domain={domain}&strategy=merge`.
- [x] **Mapeamento Explícito de Portas no Marketplace (Data Product)**:
  - Registro de Portas de Saída via API dedicada: `PUT /api/v1/dataProducts/{name}/outputPorts/add`.
  - Registro de Portas de Entrada via API dedicada: `PUT /api/v1/dataProducts/{name}/inputPorts/add`.
- [x] **Publicação e Vínculo de Contratos ODCS Nativos nas Tabelas**:
  - Conversão e submissão da especificação ODCS YAML diretamente via API nativa: `PUT /api/v1/dataContracts/odcs/yaml`.
  - Mapeamento estrito de tipos de regras de qualidade para os enums aceitos pelo OpenMetadata (`custom`, `sql`, `library`, `text`).
  - Tratamento de unidades válidas de SLA (`year`, `day`, `month`).
- [x] **Amostra de Dados Automática (Sample Data)**:
  - Ingestão transparente via `PUT /api/v1/tables/{id}/sampleData` a partir dos arquivos de seeds (`seeds/*.csv`) ou gerador sintético tipado, garantindo conformidade estrita com as colunas do contrato.
- [x] **Metadados e Governança Orientados a Contratos**:
  - **Proprietário**: Associação da Squad/Time (`owners`) tanto na Tabela física quanto no Data Product.
  - **Camada**: Classificação por Tags nativas (`Tier.Tier1` para Gold, `Tier.Tier2` para Silver, `Tier.Tier3` para Bronze/Inbound).
  - **Certificação**: Registro da tag e metadado de certificação (`Certification.Silver` / `Certification.Gold`).
  - **Período de Retenção**: Formatação padronizada ISO-8601 (`retentionPeriod: P5Y`) extraída de `servicelevels.retention` e `governance.retentionYears`.
- [x] **Ciclo de Vida com Estado Inicial 'Draft'**:
  - Todas as tabelas, contratos ODCS e Data Product nascem no estado `Draft` e fase `DEVELOPMENT`.
- [x] **Esteira de Aprovação / Promoção para Produção (CI/CD)**:
  - Criação do script de aprovação [`scripts/approve_data_product_ci.py`](scripts/approve_data_product_ci.py) e wrapper [`scripts/approve_repo_product.sh`](scripts/approve_repo_product.sh).
  - Comandos no `Makefile`: `make approve-cdb`, `make approve-cra`, `make approve-derivado`, `make approve-all`.
  - Transição de estado: `Draft` ➔ `Approved`, `DEVELOPMENT` ➔ `PRODUCTION` e ativação oficial do contrato ODCS (`status: active`).

- [x] **Identidade Visual e Tipagem Correta de Serviços de Banco**:
  - **Origens Transacionais**: Identificação e registro com `serviceType: "Oracle"` (ícone vermelho nativo da Oracle) ou `serviceType: "Db2"` (ícone IBM Db2), em vez do padrão genérico Postgres.
  - **DuckDB Server**: Migração do serviço de `Postgres` para `CustomDatabase` nativo (`metadata.ingestion.source.database.customdatabase.metadata.CustomDatabaseSource`), com `displayName: "DuckDB Server"` e customização visual via `style: {"iconURL": "https://duckdb.org/images/favicon/apple-touch-icon.png", "color": "#FFF100"}` para exibir o logotipo oficial do DuckDB no OpenMetadata.

## 2. Status por Repositório

### 2.1 Repositório `repos/sist-cdb`
- [x] Contratos ODPS (`data-product.odps.yaml`) e ODCS (`cdb-posicao.odcs.yaml`, `cdb-movimentacao.odcs.yaml`) migrados para DuckDB / Iceberg e ODPS v4.1.
- [x] Deploy de governança executado e validado no OpenMetadata (`make deploy-cdb`).
- [x] Portas de entrada (`tb_sist_cdb_oracle_core_inbound`) e saída (`silver_posicao`, `silver_movimentacao`) ativas na UI.
- [x] Contratos ODCS vinculados às tabelas físicas no DuckDB Server.
- [x] Ingestão automática de amostra de dados (`sampleData`) com 6 linhas tipadas nas tabelas Silver.
- [x] Metadados de governança enriquecidos: `owners` (Squad Renda Fixa Emissões), `tags` (`Tier.Tier2`), `certification` (`Certification.Silver`) e `retentionPeriod` (`P5Y`).
- [x] Esteira de promoção para Produção testada e homologada via `make approve-cdb` (Status: `Approved`, Fase: `PRODUCTION`, Contratos: `active`).
- [x] **Execução da Carga**: Pipeline disparado no cluster K3s com sucesso (`make job-cdb`). Tabelas `investments.cdb.silver_posicao` (6 linhas) e `investments.cdb.silver_movimentacao` (6 linhas) gravadas no DuckDB Server.
- [x] **Validação de Observabilidade**: Testes ODCS reportados com sucesso para a API do OpenMetadata (`POST /v1/dataQuality/testCases/testCaseResults`). Cobertura ativa na UI com 100% de sucesso (3 testes em `silver_posicao` e 2 testes em `silver_movimentacao`).

---

### 2.2 Repositório `repos/sist-cra` (Deploy e Aprovação Concluídos)
- [x] Contratos ODPS (v4.1) e ODCS convertidos para DuckDB / Iceberg (preservando origem transacional IBM DB2).
- [x] Seeds CSV criadas e pipeline Python (`pipeline_cra.py`) preparado com manifesto de Job K8s.
- [x] **Deploy de Governança (Draft)**: Executado com sucesso via `make deploy-cra`.
  - [x] Publicação do Data Product `SIST_CRA` no subdomínio `Investimentos.Securitizacao`.
  - [x] Portas de entrada (`tb_sist_cra_securitizadora_gateway_inbound` sob conector IBM Db2) e saída (`silver_posicao`, `silver_movimentacao` sob DuckDB Server).
  - [x] Contratos ODCS vinculados às tabelas físicas e amostra de dados (`sampleData`) injetada via seed CSV (5 linhas tipadas).
  - [x] Governança aplicada: `owners` (Squad Securitização e Agro), `Tier.Tier2`, `Certification.Silver`, `retentionPeriod: P7Y`.
- [x] **Aprovação / Promoção para Produção**: Executado com sucesso via `make approve-cra`.
  - [x] Transição de estado: `Draft` ➔ `Approved`, fase `DEVELOPMENT` ➔ `PRODUCTION`.
  - [x] Contratos ODCS ativados oficialmente (`status: active`).
- [x] **Execução da Carga**: Rodado com sucesso via `make job-cra`. Tabelas `investments.cra.silver_posicao` (5 linhas) e `investments.cra.silver_movimentacao` (5 linhas) persistidas no DuckDB Server.
- [x] **Validação de Observabilidade**: 3 testes ODCS reportados com sucesso no OpenMetadata (`POST /v1/dataQuality/testCases/testCaseResults`). Cobertura 100% verde na UI.

---

### 2.3 Repositório `repos/renda-fixa-derivado` (Deploy, Aprovação e Carga Concluídos)
- [x] Contratos ODPS (v4.1) e ODCS convertidos com portas de saída apontando para DuckDB Server e MongoDB Local (`mongodb_k3s`).
- [x] Pipeline Python (`pipeline_renda_fixa.py`) preparado para consolidar a Gold e alimentar o MongoDB + Testes OM.
- [x] **Deploy de Governança (Draft)**: Executado com sucesso via `make deploy-derivado`.
- [x] **Validação na UI do OpenMetadata**:
  - [x] Confirmar Data Product `RENDA_FIXA_DERIVADO` no subdomínio `Investimentos.RendaFixa`.
  - [x] Validar portas de entrada conectadas aos upstreams `SIST_CDB` e `SIST_CRA` (4 portas associadas).
  - [x] Validar portas de saída analítica (Silver & Gold DuckDB) e operacional (`mongodb_k3s.investments_serving.collections.rf_customer_positions`).
  - [x] Validar a linhagem de ponta a ponta (Origens ➔ Silver CDB/CRA ➔ Silver RF ➔ Gold RF ➔ MongoDB).
  - [x] Confirmar geração de dados sintéticos para **Sample Data** nas 5 tabelas (Silver, Gold e MongoDB).
  - [x] Confirmar status inicial `Draft` e fase `DEVELOPMENT`.
- [x] **Aprovação / Promoção para Produção**: Executado com sucesso via `make approve-derivado` (Status: `Approved`, Fase: `PRODUCTION`, 5 Contratos ODCS: `active`).
- [x] **Execução da Carga**: Pipeline disparado no cluster K3s com sucesso (`make job-derivado`). 11 posições consolidadas na Silver, 5 posições agregadas na Gold e 5 documentos sincronizados no MongoDB Serving Store.
- [x] **Validação no MongoDB Compass**: Conexão validada em `mongodb://localhost:27017` com collection `investments_serving.rf_customer_positions` (5 documentos BSON completos e válidos).
- [x] **Validação de Alertas e Observabilidade**: 3 testes ODCS (`check_saldo_gold_consistente`, `check_qt_titulos_positiva` e `check_balances_valid`) reportados com 100% de sucesso (`status=Success`) no OpenMetadata.

---

### 2.4 Interface Web DuckDB (CloudBeaver)
- [x] **Configuração e Homologação do CloudBeaver para DuckDB**:
  - Configuração do ConfigMap `cloudbeaver-config` com permissões pré-definidas (`data-sources-permissions.json`), `initial-data.conf` e `initial-data-sources.conf`.
  - Habilitação de acesso anônimo compartilhado via `CLOUDBEAVER_APP_GRANT_CONNECTIONS_ACCESS_TO_ANONYMOUS_TEAM="true"` e `anonymousAccessEnabled: true`.
  - Provisionamento determinístico via `init_container` (`init-cloudbeaver-config`) para garantir persistência no PVC.
  - Conexão pré-configurada ao `DuckDB Server (pg_duckdb)` via protocolo PostgreSQL (`jdbc:postgresql://duckdb-server:5433/investments`).
  - Validação end-to-end: navegação completa nas árvores de metadados dos schemas `cdb`, `cra` e `renda_fixa`, e execução de consultas SQL analíticas em `http://localhost:8978`.

---


## 3. Próximas Ações e Guia Operacional

1. **Deploy e Governança**:
   * O script [`scripts/deploy_data_product_ci.py`](scripts/deploy_data_product_ci.py) e o aprovador [`scripts/approve_data_product_ci.py`](scripts/approve_data_product_ci.py) estão prontos para todos os repositórios (`make deploy-*` e `make approve-*`).
2. **Esteira CI/CD Completa**:
   * Deploy inicial: `make deploy-all` (implanta `sist-cdb`, `sist-cra` e `renda-fixa-derivado` em estado `Draft`).
   * Promoção / Aprovação: `make approve-all` (promove todos os 3 produtos para `Approved` e `PRODUCTION`).
3. **Execução Controlada dos Pipelines de Dados**:
   * Cada carga de pipeline permanece sob comando manual através de `make job-cdb`, `make job-cra` e `make job-derivado`, respeitando o isolamento do cluster local.
