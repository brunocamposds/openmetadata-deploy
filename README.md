# OpenMetadata on Kubernetes (K3s / WSL Ubuntu)

Projeto completo de implantação, automação e governança de dados utilizando **OpenMetadata** em cluster Kubernetes local (**k3s**) no ambiente WSL 2 (Ubuntu) / Windows 11.

Inclui infraestrutura como código (Terraform), catálogo de metadados, busca distribuída com OpenSearch, banco relacional PostgreSQL, e pipeline CI/CD DataOps para cadastro automatizado de **Produtos de Dados** e **Contratos de Dados** aderentes aos padrões **ODPS** (*Open Data Product Standard*) e **ODCS** (*Open Data Contract Standard*).

---

## 🏗️ Arquitetura

O ambiente é provisionado via Terraform em namespace isolado no Kubernetes (`openmetadata`):

* **OpenMetadata Server (v2.0.2)**: Aplicação web e REST API.
* **PostgreSQL (18.x)**: Armazenamento relacional de metadados estruturados, usuários, roles e entidades.
* **OpenSearch (2.x)**: Mecanismo de busca e indexação textual/vetorial dos metadados.
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
> O provisionamento executa a criação do PostgreSQL, OpenSearch e do OpenMetadata Server. O cold-start inicial do OpenMetadata realiza a migração do banco e a criação de todos os índices no OpenSearch (processo monitorado pelo probe ajustado).

### 2. Verificar o status dos componentes
```bash
make status
```

### 3. Acessar a interface Web
Abra o túnel executando:
```bash
make port-forward
```
Acesse no seu navegador: [http://localhost:8585](http://localhost:8585)

#### Credenciais de Acesso Inicial:
* **E-mail:** `admin@open-metadata.org`
* **Senha:** `admin`

---

## 📦 Produtos e Contratos de Dados (DataOps)

O projeto contém contratos e rotinas de automação interativa:

* **Contratos:**
  * `contracts/odps/renda_fixa.odps.yaml`: Especificação do Produto de Dados (*ODPS*).
  * `contracts/odcs/posicao_renda_fixa.odcs.yaml`: Contrato de Dados (*ODCS*) com schema, SLAs e governança.

* **Executar o cadastro automatizado do Data Product:**
  ```bash
  make seed-renda-fixa
  ```

---

## 🧹 Limpeza do Ambiente

Para remover todos os recursos gerenciados pelo Terraform:
```bash
make destroy
```

---

## 📄 Licença e Propósito

Ambiente voltado para desenvolvimento, experimentação avançada em Engenharia de Dados e Engenharia de IA.
