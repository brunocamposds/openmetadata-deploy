# Criação do Namespace dedicado para o ecossistema OpenMetadata
resource "kubernetes_namespace" "om_namespace" {
  metadata {
    name = var.namespace
    labels = {
      app       = "openmetadata"
      managed-by = "terraform"
    }
  }
}

# Secret com a senha do banco de dados referenciada pelo OpenMetadata
resource "kubernetes_secret" "db_secret" {
  metadata {
    name      = "openmetadata-postgresql-secret"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
  }

  data = {
    password = var.postgresql_password
  }

  type = "Opaque"
}

# Secret de contingência esperado por helpers do chart Helm do OpenMetadata
resource "kubernetes_secret" "airflow_secrets" {
  metadata {
    name      = "airflow-secrets"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
  }

  data = {
    "openmetadata-airflow-password" = "dummy_password"
  }

  type = "Opaque"
}

# Release Helm: PostgreSQL (Bitnami - pacote local)
resource "helm_release" "postgresql" {
  name      = "postgresql"
  chart     = "${path.module}/charts/postgresql-18.11.6.tgz"
  namespace = kubernetes_namespace.om_namespace.metadata[0].name
  timeout   = 600

  values = [
    file("${path.module}/values/postgresql-values.yaml")
  ]

  set {
    name  = "auth.database"
    value = var.postgresql_database
  }

  set {
    name  = "auth.username"
    value = var.postgresql_username
  }

  set {
    name  = "auth.password"
    value = var.postgresql_password
  }

  set {
    name  = "primary.persistence.storageClass"
    value = var.storage_class_name
  }
}

# Release Helm: OpenSearch (single-node para desenvolvimento local)
resource "helm_release" "opensearch" {
  name       = "opensearch"
  repository = "https://opensearch-project.github.io/helm-charts/"
  chart      = "opensearch"
  version    = var.opensearch_chart_version
  namespace  = kubernetes_namespace.om_namespace.metadata[0].name
  timeout    = 600

  values = [
    file("${path.module}/values/opensearch-values.yaml")
  ]

  set {
    name  = "persistence.storageClass"
    value = var.storage_class_name
  }

  set {
    name  = "opensearchJavaOpts"
    value = "-Xmx${var.opensearch_heap_size} -Xms${var.opensearch_heap_size}"
  }
}

# Release Helm: OpenMetadata Server (pacote local)
resource "helm_release" "openmetadata" {
  name      = "openmetadata"
  chart     = "${path.module}/charts/openmetadata-2.0.2.tgz"
  namespace = kubernetes_namespace.om_namespace.metadata[0].name
  timeout   = 900
  wait      = false

  depends_on = [
    helm_release.postgresql,
    helm_release.opensearch,
    kubernetes_secret.db_secret,
    kubernetes_secret.airflow_secrets
  ]

  values = [
    file("${path.module}/values/openmetadata-values.yaml")
  ]

  set {
    name  = "openmetadata.config.database.databaseName"
    value = var.postgresql_database
  }

  set {
    name  = "openmetadata.config.database.auth.username"
    value = var.postgresql_username
  }
}
