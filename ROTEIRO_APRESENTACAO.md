# Roteiro Prático de Apresentação: Data Mesh & Governança as Code com OpenMetadata

Este documento fornece o guia passo a passo completo dos comandos `make` e pontos de destaque na interface visual (UI) para conduzir uma demonstração de ponta a ponta da arquitetura de Governança, Contratos de Dados (ODPS/ODCS), Data Mesh e Observabilidade implementada no Kubernetes (K3s).

---

## 0. Pré-Requisitos e Acesso aos Painéis

Antes de iniciar, certifique-se de que o cluster local está ativo:
```bash
make status
```

Abra os seguintes painéis no seu navegador:
- **OpenMetadata UI:** [http://localhost](http://localhost) (ou [http://localhost:8585](http://localhost:8585))
  - *Credenciais:* `admin@open-metadata.org` / `admin`
- **CloudBeaver (DuckDB Web UI):** [http://localhost:8978](http://localhost:8978)
- **MongoDB Compass (opcional):** `mongodb://localhost:27017`

---

## 1. Reset para o Estado Inicial (Limpeza "Recém-Instalado")

Para começar a apresentação com o OpenMetadata totalmente limpo (como se tivesse acabado de ser provisionado, sem dados de negócio, tabelas ou alertas):

```bash
make reset
```

> **O que o `make reset` faz:**
> 1. Remove todos os Data Products, Contratos ODCS e Testes de Qualidade da API do OpenMetadata.
> 2. Deleta os serviços de banco (`duckdb_server`, `mongodb_k3s`, origens transacionais).
> 3. Deleta os domínios, subdomínios, glossários e times customizados.
> 4. Limpa todas as notificações e histórico do **Sininho / Activity Feed**.
> 5. Limpa os schemas analíticos no DuckDB Server (`cdb`, `cra`, `renda_fixa`) e a base do MongoDB (`investments_serving`).
> 6. Remove os pods de Jobs finalizados no Kubernetes.
> 
> *Tempo de execução: ~5 a 10 segundos (sem necessidade de reiniciar pods).*

**O que mostrar na UI:**
- Acesse [http://localhost/explore/dataProducts](http://localhost/explore/dataProducts): O Marketplace está completamente limpo.
- O ícone do Sininho no canto superior direito está com zero notificações.

---

## 2. Passo a Passo da Demonstração

Certifique-se de estar na branch principal para iniciar o fluxo básico:
```bash
git checkout main
```

---

### ATO 1: Deploy dos Produtos de Dados (Governança as Code)

Mostre como os contratos declarativos (ODPS v4.1 e ODCS v3.0) versionados no Git provisionam automaticamente o catálogo no OpenMetadata através de esteiras de CI/CD.

```bash
# Opção A: Deploy individual passo a passo
make deploy-cdb
make deploy-cra
make deploy-derivado

# OU Opção B: Deploy de todos os produtos de uma só vez
make deploy-all
```

**O que demonstrar no OpenMetadata:**
1. **Marketplace de Dados:** Acesse [Explore Data Products](http://localhost/explore/dataProducts).
   - Visualize os 3 Data Products: `SIST_CDB`, `SIST_CRA` e `RENDA_FIXA_DERIVADO`.
   - Destaque que todos nascem no estado **`Draft`** e fase **`DEVELOPMENT`** (Governança responsável).
2. **Serviços de Banco Identificados:**
   - Acesse [Settings > Databases](http://localhost/settings/services/databases).
   - O `DuckDB Server` exibe o logotipo oficial do DuckDB.
   - As origens legadas exibem ícones nativos corporativos (Oracle e IBM Db2).
3. **Contratos ODCS e Amostra de Dados (Sample Data):**
   - Acesse a tabela [`silver_posicao`](http://localhost/table/duckdb_server.investments.cdb.silver_posicao).
   - Aba **Data Contract**: Contrato ODCS ativo em modo `Draft`, com schema estrito, SLA e regras de qualidade declaradas.
   - Aba **Sample Data**: Amostra tipada injetada automaticamente a partir dos arquivos de seed.
   - Tags de governança aplicadas: Squad proprietária (`owners`), camada (`Tier.Tier2`), certificação (`Certification.Silver`) e retenção (`P5Y`).
4. **Linhagem de Ponta a Ponta (Lineage):**
   - Acesse a tabela [`gold_posicao_consolidada_cliente`](http://localhost/table/duckdb_server.investments.renda_fixa.gold_posicao_consolidada_cliente) e clique na aba **Lineage**.
   - Mostre o grafo completo:
     `Oracle / Db2 ➔ Silver CDB / CRA ➔ Silver RF ➔ Gold RF ➔ MongoDB Serving`.

---

### ATO 2: Ciclo de Vida e Esteira de Aprovação (Draft ➔ Production)

Mostre a esteira de promoção onde a governança formaliza a ativação dos contratos e coloca os produtos em Produção.

```bash
make approve-all
```
*(Ou individualmente: `make approve-cdb`, `make approve-cra`, `make approve-derivado`)*

**O que demonstrar no OpenMetadata:**
- Atualize a página do Data Product ou das tabelas:
  - O status mudou de **`Draft`** para **`Approved`**.
  - O ciclo de vida foi promovido para **`PRODUCTION`**.
  - Os contratos ODCS passaram para **`active`**.

---

### ATO 3: Execução dos Pipelines de Dados no Kubernetes

Demonstre a execução real dos pipelines conteinerizados rodando como Jobs no K3s, populando as camadas Bronze, Silver e Gold no DuckDB Server e servindo para canais digitais no MongoDB.

```bash
# 1. Executa a carga do CDB (Transacional -> Bronze -> Silver -> Testes ODCS)
make job-cdb

# 2. Executa a carga do CRA
make job-cra

# 3. Executa a consolidação analítica e operacional da Renda Fixa
make job-derivado
```

*Para visualizar os logs em tempo real:*
```bash
make job-logs-cdb
make job-logs-cra
make job-logs-derivado
```

**O que demonstrar nos painéis:**
1. **No CloudBeaver ([http://localhost:8978](http://localhost:8978)):**
   - Abra a conexão `DuckDB Server (pg_duckdb)`.
   - Navegue pelos schemas `cdb`, `cra` e `renda_fixa`.
   - Execute uma query SQL mostrando as posições consolidadas na Gold:
     ```sql
     SELECT * FROM renda_fixa.gold_posicao_consolidada_cliente;
     ```
2. **No MongoDB (Serving Layer de Canais):**
   - No MongoDB Compass em `mongodb://localhost:27017` (ou via terminal):
   - Verifique a base `investments_serving` com a collection `rf_customer_positions` alimentada para consumo das APIs de Internet Banking/Mobile.
3. **No OpenMetadata:**
   - Acesse as tabelas e veja a aba **Profiler & Data Quality**.
   - Todos os testes de contrato foram executados com **100% de Sucesso (Verde)**.

---

### ATO 4: Gran Finale — Nova Release do Contrato & Alerta de Observabilidade

Demonstre como o Git gerencia o versionamento de contratos de dados e como o OpenMetadata reage instantaneamente a uma anomalia de qualidade gerando alertas e incidentes para o time responsável.

1. **Alterne para a branch da nova release:**
   ```bash
   git checkout feature/sist-cdb-observability-alert
   ```

2. **Aplique o deploy da nova release e aprove:**
   ```bash
   make deploy-cdb
   make approve-cdb
   ```
   *Destaque na UI:* O Data Product `SIST_CDB` agora exibe a versão **v1.3.0** e incorpora uma nova tabela isolada: `silver_certificado` (Cadastro de Certificados de CDB).

3. **Dispare o pipeline do CDB contendo a anomalia (registro com ID nulo):**
   ```bash
   make job-cdb
   make job-logs-cdb
   ```

4. **Demonstração do Alerta de Observabilidade no OpenMetadata:**
   - **Sininho de Notificações (Canto Superior Direito):**
     - O ícone do Sininho acende com a notificação crítica:
       > 🚨 **ALERTA CRÍTICO DE OBSERVABILIDADE [SIST_CDB]**: Violação de integridade no contrato ODCS da tabela `silver_certificado`! O teste `check_id_certificado_not_null` falhou.
   - **Incident Manager:**
     - Acesse no menu lateral esquerdo: **Quality > Incident Manager** ([http://localhost/incident-manager](http://localhost/incident-manager)).
     - O incidente foi aberto automaticamente com severidade **Severity 1** e atribuído ao administrador.
   - **Tabela Física:**
     - Acesse [`silver_certificado`](http://localhost/table/duckdb_server.investments.cdb.silver_certificado) > aba **Profiler & Data Quality**.
     - O teste `check_id_certificado_not_null` está destacado em **vermelho (Failed)** com a evidência de violação da regra contratual.

---

## 3. Resumo dos Comandos Make para a Apresentação

| Momento | Comando | Finalidade |
| :--- | :--- | :--- |
| **Antes de começar** | `make reset` | Limpa todo o catálogo do OM, DuckDB e Mongo (estado zerado) |
| **Ato 1: Deploy** | `make deploy-all` | Publica os 3 Data Products, Contratos ODCS, linhagem e amostras em *Draft* |
| **Ato 2: Aprovação**| `make approve-all` | Promove todos os produtos para *Approved* / *PRODUCTION* |
| **Ato 3: Carga K3s** | `make job-cdb` | Roda ingestão e DQ do CDB |
| | `make job-cra` | Roda ingestão e DQ do CRA |
| | `make job-derivado` | Consolida Gold analítica e alimenta o MongoDB |
| **Ato 4: Anomalia** | `git checkout feature/sist-cdb-observability-alert` | Muda para a branch da nova release |
| | `make deploy-cdb && make approve-cdb` | Atualiza o Data Product para v1.3.0 |
| | `make job-cdb` | Dispara o teste que falha e aciona o Sininho/Incidente |
