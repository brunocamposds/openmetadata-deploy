# Padrões de Implantação: OpenMetadata no Kubernetes (K3s)

## Visão Geral dos Componentes

O OpenMetadata depende tipicamente de quatro pilares de infraestrutura:
1. **Banco de Dados Relacional**: MySQL 8 ou PostgreSQL 12+ (para catálogo e metadados estruturados).
2. **Search Engine**: OpenSearch (2.x) ou Elasticsearch (7.x/8.x) (para indexação de busca de metadados).
3. **OpenMetadata Server**: Aplicação web e REST API.
4. **Ingestion Framework / Airflow**: Orquestrador para workflows de ingestão e profiling.

## Recomendações de Deploy no K3s Local

1. **Namespaces Dedicados**:
   - Manter os recursos isolados em um namespace específico (ex: `openmetadata`).
   ```bash
   wsl -d Ubuntu -- kubectl create namespace openmetadata --dry-run=client -o yaml | wsl -d Ubuntu -- kubectl apply -f -
   ```

2. **Gerenciamento de Recursos (CPU / RAM)**:
   - Ambientes K3s em WSL 2 compartilham memória do host.
   - Definir limites (`resources.limits` e `resources.requests`) sensatos para pods de busca (OpenSearch/Elasticsearch costumam consumir 1Gi a 2Gi no mínimo).

3. **Persistência de Dados**:
   - Utilizar a StorageClass padrão `local-path`.
   - Evitar `hostPath` direto para diretórios do Windows montados em `/mnt/c/` para bancos de dados de alta I/O (MySQL/PostgreSQL/OpenSearch) devido a possíveis problemas de locking de arquivos do NTFS/9P; preferir PVCs gerenciados pelo storage class `local-path` nativo do K3s/WSL.

4. **Helm Charts Oficiais**:
   - Repositório oficial do Helm: `https://helm.openmetadata.org`
   - Realizar validação de dry-run (`helm install ... --dry-run`) antes de aplicar releases finais.
