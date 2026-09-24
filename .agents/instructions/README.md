# Instruções e Arquitetura do Projeto

Este diretório contém a documentação técnica, padrões arquiteturais e procedimentos operacionais voltados para orientar os agentes de IA e desenvolvedores que operam neste repositório.

## Índice de Documentos

1. [Configuração do Cluster K3s e WSL](k8s-cluster.md)
   - Arquitetura de execução Windows Host + WSL Ubuntu.
   - Detalhes de StorageClass (`local-path`), nós e namespaces.
   - Regras de roteamento de comandos.
2. [Padrões de Implantação do OpenMetadata](openmetadata-standards.md)
   - Dependências (MySQL/PostgreSQL, OpenSearch/Elasticsearch).
   - Servidor OpenMetadata e Ingestion / Airflow.
   - Padrão de manifests Kubernetes e Helm Charts.

## Comportamento Esperado do Agente

- **Auto-verificação**: Ao receber uma tarefa relacionada a infraestrutura ou Kubernetes, o agente deve sempre consultar este diretório para validar se a ação proposta respeita o ambiente K3s/WSL Ubuntu.
- **Rigor de Comandos**: Qualquer comando DEVE ser disparado exclusivamente via `wsl -d Ubuntu -- <comando>`.
- **Prevenção de Danos**: Nunca sobrescrever ou alterar configurações do Rancher Desktop no host Windows sem solicitação explícita.
