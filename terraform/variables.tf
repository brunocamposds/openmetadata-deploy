variable "kubeconfig_path" {
  description = "Caminho do arquivo kubeconfig no WSL Ubuntu"
  type        = string
  default     = "~/.kube/config"
}

variable "namespace" {
  description = "Namespace do Kubernetes para o deploy do OpenMetadata e dependências"
  type        = string
  default     = "openmetadata"
}

variable "storage_class_name" {
  description = "StorageClass do cluster K3s para persistência"
  type        = string
  default     = "local-path"
}

# Configurações do PostgreSQL
variable "postgresql_chart_version" {
  description = "Versão do Helm chart do Bitnami PostgreSQL"
  type        = string
  default     = "18.11.6"
}

variable "postgresql_database" {
  description = "Nome do banco de dados para o OpenMetadata"
  type        = string
  default     = "openmetadata_db"
}

variable "postgresql_username" {
  description = "Usuário do banco de dados"
  type        = string
  default     = "openmetadata_user"
}

variable "postgresql_password" {
  description = "Senha do banco de dados PostgreSQL"
  type        = string
  default     = "openmetadata_password"
  sensitive   = true
}

# Configurações do OpenSearch
variable "opensearch_chart_version" {
  description = "Versão do Helm chart do OpenSearch"
  type        = string
  default     = "3.8.0"
}

variable "opensearch_heap_size" {
  description = "Memória alocada para a JVM do OpenSearch"
  type        = string
  default     = "1024m"
}

# Configurações do OpenMetadata
variable "openmetadata_chart_version" {
  description = "Versão do Helm chart do OpenMetadata"
  type        = string
  default     = "2.0.2"
}
