# ==============================================================================
# DuckDB Server (pg_duckdb) - PostgreSQL Wire Protocol para DuckDB
# Centraliza a concorrência dos Kubernetes Jobs, Web UI e OpenMetadata
# Acessível externamente na porta 5433 e internamente na porta 5432
# ==============================================================================

resource "kubernetes_persistent_volume_claim" "duckdb_server_pvc" {
  metadata {
    name      = "duckdb-server-data-pvc"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
  }

  wait_until_bound = false

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = var.storage_class_name

    resources {
      requests = {
        storage = "5Gi"
      }
    }
  }
}

resource "kubernetes_deployment" "duckdb_server" {
  metadata {
    name      = "duckdb-server"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
    labels = {
      app = "duckdb-server"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "duckdb-server"
      }
    }

    template {
      metadata {
        labels = {
          app = "duckdb-server"
        }
      }

      spec {
        container {
          name  = "duckdb-server"
          image = "pgduckdb/pgduckdb:17-v0.1.0"

          port {
            name           = "postgres"
            container_port = 5432
          }

          env {
            name  = "PGDATA"
            value = "/var/lib/postgresql/data/pgdata"
          }

          env {
            name  = "POSTGRES_DB"
            value = "investments"
          }

          env {
            name  = "POSTGRES_USER"
            value = "duckdb_user"
          }

          env {
            name  = "POSTGRES_PASSWORD"
            value = "duckdb_password"
          }

          volume_mount {
            name       = "duckdb-server-storage"
            mount_path = "/var/lib/postgresql/data"
          }

          resources {
            limits = {
              cpu    = "1"
              memory = "1Gi"
            }
            requests = {
              cpu    = "100m"
              memory = "256Mi"
            }
          }
        }

        volume {
          name = "duckdb-server-storage"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.duckdb_server_pvc.metadata[0].name
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "duckdb_server_service" {
  metadata {
    name      = "duckdb-server"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
    labels = {
      app = "duckdb-server"
    }
  }

  spec {
    type = "LoadBalancer"

    selector = {
      app = "duckdb-server"
    }

    port {
      name        = "postgres"
      port        = 5433
      target_port = 5432
    }
  }
}
