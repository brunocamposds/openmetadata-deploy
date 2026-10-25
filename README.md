# OpenMetadata on Kubernetes (K3s / WSL Ubuntu)

Projeto completo de implantação, automação e governança de dados utilizando **OpenMetadata** em cluster Kubernetes local (**k3s**) no ambiente WSL 2 (Ubuntu) / Windows 11.

Inclui infraestrutura como código (Terraform), catálogo de metadados, busca distribuída com OpenSearch, banco relacional PostgreSQL, e pipeline CI/CD DataOps para cadastro automatizado de **Produtos de Dados** e **Contratos de Dados** aderentes aos padrões **ODPS** (*Open Data Product Standard*) e **ODCS** (*Open Data Contract Standard*).

---

## 🏗️ Arquitetura

O ambiente é provisionado via Terraform em namespace isolado no Kubernetes (`openmetadata`):

* **OpenMetadata Server (v2.0.6)**: Aplicação web e REST API.
* **PostgreSQL (18.x)**: Armazenamento relacional de metadados estruturados, usuários, roles e entidades.
* **OpenSearch (2.x)**: Mecanismo de busca e indexação textual/vetorial dos metadados.
* **ClickHouse Server (24.x)**: Banco colunar analítico de alta performance nativamente integrado ao OpenMetadata (`serviceType: Clickhouse`), acessível via DBeaver/JDBC e Ingress (`http://clickhouse.local`).
* **MongoDB (7.x)**: Serving Store operacional para canais digitais, acessível via MongoDB Compass e Ingress (`http://mongodb.local`).
* **DataOps Pipeline**: Scripts de seed e automação de Data Products, contratos e linhagem ponta a ponta.

---

## 🚀 Pré-requisitos

1. **Windows 11 / WSL 2** com distribuição **Ubuntu** instalada e configurada.
2. **K3s** rodando no WSL Ubuntu (v1.30+).
3. **Terraform** instalado no ambiente WSL Ubuntu.
4. **kubectl** configurado e apontando para o cluster K3s local.

---

## 🛠️ Como Utilizar

Todos os comandos de automação estão consolidados no `Makefile`:

### 1. Inicializar e aplicar a infraestrutura
```bash
make init
make apply
```
> O provisionamento executa a criação do PostgreSQL, OpenSearch, ClickHouse Server, MongoDB e do OpenMetadata Server.

### 2. Verificar o status dos componentes
```bash
make status
```

### 3. Acessar os Serviços (Web & Ferramentas Locais via Traefik)

> **Sem Port-Forwarding**: Todos os serviços são roteados e expostos diretamente pelo **Traefik** (Ingress / Proxy L4-L7) nas portas locais do host. Você não precisa executar comandos de `kubectl port-forward`.

#### Acesso Direto (localhost):
* **OpenMetadata UI & API**: [http://localhost/](http://localhost/) (Porta 80 padrão Traefik) ou [http://localhost:8585](http://localhost:8585)
* **ClickHouse HTTP (DBeaver / REST)**: `http://localhost:8123`
* **ClickHouse Native TCP (DBeaver / Clients)**: `localhost:9000`
* **MongoDB Compass / Drivers**: `mongodb://localhost:27017`
* **PostgreSQL (Catálogo OM)**: `localhost:5432`

#### Acesso via Hostnames Traefik (Porta 80):
Adicione os domínios locais no arquivo `C:\Windows\System32\drivers\etc\hosts`:
```text
127.0.0.1 openmetadata.local clickhouse.local mongodb.local
```
* **OpenMetadata UI**: [http://openmetadata.local](http://openmetadata.local)
* **ClickHouse Server**: [http://clickhouse.local](http://clickhouse.local)
* **MongoDB Serving**: `mongodb.local:27017`

#### Credenciais de Acesso:
* **OpenMetadata:** `admin@open-metadata.org` / `admin`
* **ClickHouse:** `clickhouse_user` / `clickhouse_password` (Database: `investments`)

---

## 📦 Produtos e Contratos de Dados (DataOps & Governance as Code)

O projeto contém três repositórios simulados em arquitetura Data Mesh (`repos/`):
* **`repos/sist-cdb`** (*Source-Aligned*): Emissão e posições diárias de CDBs no ClickHouse Server (`investments.cdb.*`), regidos pelos contratos ODCS `cdb-posicao.odcs.yaml` e `cdb-movimentacao.odcs.yaml`.
* **`repos/sist-cra`** (*Source-Aligned*): Securitização de Agronegócio no ClickHouse Server (`investments.cra.*`), regidos pelos contratos ODCS `cra-posicao.odcs.yaml` e `cra-movimentacao.odcs.yaml`.
* **`repos/renda-fixa-derivado`** (*Consumer-Aligned*): Visão consolidada de Renda Fixa unificando CDB e CRA, disponibilizando tabelas analíticas Silver/Gold no ClickHouse (`investments.renda_fixa.*`) e Serving Store em MongoDB Local (`investments_serving.rf_customer_positions`), regidos pelos contratos `rf-posicao-consolidada.odcs.yaml`, `rf-movimentacao-consolidada.odcs.yaml` e `rf-mongo-canal.odcs.yaml`.

* **Executar a esteira de governança CI/CD por repositório:**
  ```bash
  wsl -d Ubuntu -- ./scripts/deploy_repo_product.sh repos/sist-cdb
  wsl -d Ubuntu -- ./scripts/deploy_repo_product.sh repos/sist-cra
  wsl -d Ubuntu -- ./scripts/deploy_repo_product.sh repos/renda-fixa-derivado
  ```

---

## ⏸️ Ciclo de Vida: Pausar e Retomar (Sem Perder Dados)

Para liberar 100% da CPU e Memória RAM sem perder o estado do banco e dos índices (evitando ter que rodar o cold-start de novo):

* **Pausar o ambiente (0% CPU/RAM):**
  ```bash
  make stop
  ```

* **Retomar o ambiente (~30 segundos):**
  ```bash
  make start
  ```

---

## 🧹 Destruição Completa do Ambiente

Para remover **todos** os recursos gerenciados pelo Terraform (incluindo volumes de dados):
```bash
make destroy
```

---

## 📄 Licença e Propósito

Ambiente voltado para desenvolvimento, experimentação avançada em Engenharia de Dados e Engenharia de IA.
